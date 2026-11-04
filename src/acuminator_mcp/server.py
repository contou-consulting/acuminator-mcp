"""FastMCP stdio server exposing Acuminator static analysis.

Tools:
  * ``analyze_project`` — run Acuminator against a .csproj / .sln path.
  * ``analyze_snippet`` — analyze a raw C# snippet using a configured reference project.
  * ``generate_suppressions`` — analyze and write ``<Project>.acuminator`` suppression files.
  * ``get_diagnostic_docs`` — fetch markdown docs for a PXNNNN diagnostic code.

All tools are declared with ``structured_output=False``: results go back as a
single JSON text block and no ``outputSchema`` is attached to the tool
definitions, which keeps the per-session schema cost low.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from acuminator_mcp import runner, snippet, suppression
from acuminator_mcp.docs import get_diagnostic_docs
from acuminator_mcp.report import DEFAULT_MAX_DIAGNOSTICS, AnalysisResult, parse_report_file, summarize

mcp = FastMCP("acuminator-mcp")

_STANDARD_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

# generate_suppressions writes into the user's source tree.
_WRITING_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)

_RESULT_SHAPE = (
    "Returns counts_by_code plus groups of {code, message, locations}, where each "
    "location is 'relative/path.cs:line:col'. groups is capped at max_diagnostics "
    "locations (truncated=true when cut); counts_by_code is always complete."
)

_MaxDiagnostics = Annotated[
    int,
    Field(
        default=DEFAULT_MAX_DIAGNOSTICS,
        ge=0,
        description="Maximum number of locations to return across all groups.",
    ),
]
_IsvMode = Annotated[
    bool,
    Field(default=False, description="ISV mode: stricter analysis, some warnings become errors."),
]
_BannedApisPath = Annotated[
    str | None,
    Field(default=None, description="Path to a custom banned-APIs file for PX1099 (see PX1099 docs for the format)."),
]
_AllowedApisPath = Annotated[
    str | None,
    Field(default=None, description="Path to a custom allowed-APIs file for PX1099."),
]


class SuppressionResult(AnalysisResult):
    suppression_files: list[str]
    project_files_modified: list[str]


def _validate_code_source(project_path: str) -> Path:
    src = Path(project_path)
    if not src.exists():
        raise FileNotFoundError(f"Project path does not exist: {src}")
    if src.suffix.lower() not in {".csproj", ".sln"}:
        raise ValueError(
            f"Unsupported code source: {src}. Acuminator only accepts .csproj or .sln."
        )
    return src


def _optional_path(value: str | None, what: str) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"{what} does not exist: {path}")
    return path


async def _analyze(src: Path, *, max_diagnostics: int, **runner_kwargs) -> AnalysisResult:
    with tempfile.TemporaryDirectory(prefix="acuminator-mcp-") as tmp:
        report_path = Path(tmp) / "report.json"
        _, stderr = await runner.run_analysis(src, output_json=report_path, **runner_kwargs)

        if not report_path.exists():
            raise RuntimeError(
                "Acuminator did not produce a JSON report. "
                f"Runner output:\n{stderr}"
            )
        parsed = parse_report_file(report_path)
    return summarize(
        parsed.diagnostics,
        code_source=str(src),
        base_dir=src.parent,
        total_diagnostics=parsed.total_diagnostics,
        max_diagnostics=max_diagnostics,
    )


@mcp.tool(
    description=(
        "Run Acuminator static analysis against an Acumatica .csproj or .sln. "
        + _RESULT_SHAPE
        + " Requires Windows + .NET Framework 4.8; the runner is downloaded on first use."
    ),
    annotations=_STANDARD_ANNOTATIONS,
    structured_output=False,
)
async def analyze_project(
    project_path: Annotated[str, Field(description="Absolute path to a .csproj or .sln file.")],
    isv_mode: _IsvMode = False,
    enable_px1007: Annotated[
        bool,
        Field(default=False, description="Enable PX1007 (XML docs on DACs / DAC fields)."),
    ] = False,
    disable_px1099: Annotated[
        bool,
        Field(default=False, description="Disable PX1099 (banned APIs)."),
    ] = False,
    enable_info_diagnostics: Annotated[
        bool,
        Field(default=False, description="Include informational-severity diagnostics."),
    ] = False,
    disable_suppression: Annotated[
        bool,
        Field(
            default=False,
            description="Also report diagnostics suppressed via <Project>.acuminator files or Acuminator comments.",
        ),
    ] = False,
    banned_apis_path: _BannedApisPath = None,
    allowed_apis_path: _AllowedApisPath = None,
    max_diagnostics: _MaxDiagnostics = DEFAULT_MAX_DIAGNOSTICS,
) -> AnalysisResult:
    return await _analyze(
        _validate_code_source(project_path),
        max_diagnostics=max_diagnostics,
        isv_mode=isv_mode,
        enable_px1007=enable_px1007,
        disable_px1099=disable_px1099,
        enable_info_diagnostics=enable_info_diagnostics,
        disable_suppression=disable_suppression,
        banned_apis_path=_optional_path(banned_apis_path, "banned_apis_path"),
        allowed_apis_path=_optional_path(allowed_apis_path, "allowed_apis_path"),
    )


@mcp.tool(
    description=(
        "WRITES FILES. Run Acuminator and record every diagnostic it finds in "
        "<Project>.acuminator suppression files next to each analyzed project, so later "
        "analyze_project runs report only new issues. Use to baseline a legacy project; "
        "existing suppression files are extended, not replaced. When a project has no "
        "suppression file yet, an empty one is created and an <AdditionalFiles> item is "
        "added to its .csproj (the runner requires both). "
        + _RESULT_SHAPE
        + " suppression_files and project_files_modified list what was written."
    ),
    annotations=_WRITING_ANNOTATIONS,
    structured_output=False,
)
async def generate_suppressions(
    project_path: Annotated[str, Field(description="Absolute path to a .csproj or .sln file.")],
    isv_mode: _IsvMode = False,
    banned_apis_path: _BannedApisPath = None,
    allowed_apis_path: _AllowedApisPath = None,
    max_diagnostics: _MaxDiagnostics = DEFAULT_MAX_DIAGNOSTICS,
) -> SuppressionResult:
    src = _validate_code_source(project_path)
    suppression_files, modified = suppression.ensure_suppression_setup(src)
    result = await _analyze(
        src,
        max_diagnostics=max_diagnostics,
        isv_mode=isv_mode,
        banned_apis_path=_optional_path(banned_apis_path, "banned_apis_path"),
        allowed_apis_path=_optional_path(allowed_apis_path, "allowed_apis_path"),
        work_mode="report-and-generate",
    )
    return SuppressionResult(
        **result.model_dump(),
        suppression_files=[str(p) for p in suppression_files],
        project_files_modified=[str(p) for p in modified],
    )


@mcp.tool(
    description=(
        "Analyze a raw C# snippet using an existing Acumatica reference project for its "
        "type environment. The reference project is auto-discovered from the server's "
        "working directory (first .csproj found walking up, then scanning down); pass "
        "reference_project_path or set ACUMINATOR_MCP_REFERENCE_PROJECT to override. "
        "Only diagnostics reported against the snippet are returned. " + _RESULT_SHAPE
    ),
    annotations=_STANDARD_ANNOTATIONS,
    structured_output=False,
)
async def analyze_snippet(
    code: Annotated[
        str,
        Field(description="The C# code snippet to analyze. May include using/namespace, or just types."),
    ],
    reference_project_path: Annotated[
        str | None,
        Field(
            default=None,
            description="Optional absolute path to the reference .csproj.",
        ),
    ] = None,
    isv_mode: Annotated[
        bool,
        Field(default=False, description="Enable Acuminator ISV mode."),
    ] = False,
    max_diagnostics: _MaxDiagnostics = DEFAULT_MAX_DIAGNOSTICS,
) -> AnalysisResult:
    return await snippet.analyze_snippet(
        code,
        reference_project_path=reference_project_path,
        isv_mode=isv_mode,
        max_diagnostics=max_diagnostics,
    )


@mcp.tool(
    name="get_diagnostic_docs",
    description=(
        "Fetch the official Acuminator documentation (markdown) for a diagnostic code "
        "like PX1014. The analysis results already carry each diagnostic's message; call "
        "this only when the message alone is not enough to understand or fix the issue."
    ),
    annotations=_STANDARD_ANNOTATIONS,
    structured_output=False,
)
async def get_diagnostic_docs_tool(
    code: Annotated[str, Field(description="Diagnostic code in the form PXNNNN, e.g. PX1014.")],
    full: Annotated[
        bool,
        Field(
            default=False,
            description="Return the whole document. By default the incorrect-code example and related-articles sections are omitted.",
        ),
    ] = False,
) -> str:
    return await get_diagnostic_docs(code, full=full)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
