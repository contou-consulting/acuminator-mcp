"""FastMCP stdio server exposing Acuminator static analysis.

Tools:
  * ``analyze_project`` — run Acuminator against a .csproj / .sln path.
  * ``analyze_snippet`` — analyze a raw C# snippet using a configured reference project.
  * ``get_diagnostic_docs`` — fetch markdown docs for a PXNNNN diagnostic code.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from acuminator_mcp import runner, snippet
from acuminator_mcp.docs import DocsError, get_diagnostic_docs
from acuminator_mcp.report import AnalysisResult, parse_report_file
from acuminator_mcp.runner import RunnerError
from acuminator_mcp.snippet import SnippetError

mcp = FastMCP("acuminator-mcp")


@mcp.tool(
    description=(
        "Run Acuminator static analysis against an Acumatica .csproj or .sln. "
        "Returns the list of diagnostics (code, message, file, line, column, project). "
        "Requires Windows + .NET Framework 4.8. The runner is downloaded and cached "
        "on first use."
    ),
)
async def analyze_project(
    project_path: Annotated[
        str,
        Field(
            description=(
                "Absolute path to a .csproj or .sln file to analyze."
            )
        ),
    ],
    isv_mode: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Enable ISV mode for stricter analysis (promotes some warnings to errors)."
            ),
        ),
    ] = False,
    enable_px1007: Annotated[
        bool,
        Field(
            default=False,
            description="Enable PX1007 (XML documentation presence on DACs / DAC fields).",
        ),
    ] = False,
    disable_px1099: Annotated[
        bool,
        Field(
            default=False,
            description="Disable PX1099 (banned APIs for Acumatica Framework).",
        ),
    ] = False,
    enable_info_diagnostics: Annotated[
        bool,
        Field(
            default=False,
            description="Include informational-severity diagnostics in the report.",
        ),
    ] = False,
) -> AnalysisResult:
    src = Path(project_path)
    if not src.exists():
        raise FileNotFoundError(f"Project path does not exist: {src}")
    if src.suffix.lower() not in {".csproj", ".sln"}:
        raise ValueError(
            f"Unsupported code source: {src}. Acuminator only accepts .csproj or .sln."
        )

    with tempfile.TemporaryDirectory(prefix="acuminator-mcp-") as tmp:
        report_path = Path(tmp) / "report.json"
        try:
            _, stderr = await runner.run_analysis(
                src,
                output_json=report_path,
                isv_mode=isv_mode,
                enable_px1007=enable_px1007,
                disable_px1099=disable_px1099,
                enable_info_diagnostics=enable_info_diagnostics,
            )
        except RunnerError as e:
            raise RuntimeError(str(e)) from e

        if not report_path.exists():
            raise RuntimeError(
                "Acuminator did not produce a JSON report. "
                f"Runner output:\n{stderr}"
            )
        return parse_report_file(report_path)


@mcp.tool(
    description=(
        "Analyze a raw C# snippet using an existing Acumatica reference project for its "
        "type environment. Set ACUMINATOR_MCP_REFERENCE_PROJECT env var, or pass "
        "reference_project_path, to a .csproj whose references resolve the Acumatica "
        "Framework. Returns only diagnostics reported against the snippet."
    ),
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
            description=(
                "Optional absolute path to the reference .csproj. Falls back to the "
                "ACUMINATOR_MCP_REFERENCE_PROJECT env var when omitted."
            ),
        ),
    ] = None,
    isv_mode: Annotated[
        bool,
        Field(default=False, description="Enable Acuminator ISV mode."),
    ] = False,
) -> AnalysisResult:
    try:
        return await snippet.analyze_snippet(
            code,
            reference_project_path=reference_project_path,
            isv_mode=isv_mode,
        )
    except (SnippetError, RunnerError) as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(
    name="get_diagnostic_docs",
    description=(
        "Fetch the official Acuminator documentation (markdown) for a diagnostic code "
        "like PX1014. Use this after analyze_project / analyze_snippet to look up the "
        "rationale and fix for a reported diagnostic."
    ),
)
async def get_diagnostic_docs_tool(
    code: Annotated[
        str,
        Field(description="Diagnostic code in the form PXNNNN, e.g. PX1014."),
    ],
) -> str:
    try:
        return await get_diagnostic_docs(code)
    except DocsError as e:
        raise RuntimeError(str(e)) from e


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
