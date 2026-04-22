"""Parse the Acuminator runner's JSON report into flat diagnostic records.

Shape emitted by the runner (recursive):
``CodeSourceReport → projectReports[].reportDetails (ReportGroup)``.

Each ``ReportGroup`` has a ``groupTitle`` (string — ``TitleConverter`` flattens
the Title struct to its text), a list of ``lines`` (each one a string,
``LineConverter`` emits them as plain strings), and ``childrenGroups``.

When diagnostics are grouped by ID, the group's ``groupTitle`` is the ``PX####``
code and each child line is 2-span: ``"<message>: <location>"``. When they're
ungrouped, the line is 3-span: ``"<code>: <message>: <location>"``. We walk the
tree carrying the nearest ``PX####`` ancestor title so 2-span lines still
produce a coded diagnostic.

``<location>`` is Roslyn's ``FileLinePositionSpan.ToString()``:
``"<file>: (<startLine>,<startChar>)-(<endLine>,<endChar>)"`` — quoted, 0-based
positions. We normalize to 1-based to match IDE conventions.

We only surface ``code``, ``file``, ``line``, ``column``, ``project``; callers
look up the diagnostic's meaning and fix via :mod:`acuminator_mcp.docs`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_LOCATION_PATTERN = re.compile(
    r'"(?P<file>[^"]+?):\s*\((?P<line>\d+),(?P<col>\d+)\)(?:-\(\d+,\d+\))?"\s*$'
)
_PX_CODE_PATTERN = re.compile(r"^(PX\d{4})\b")


class Diagnostic(BaseModel):
    code: str = Field(description="Acuminator diagnostic ID, e.g. PX1014.")
    file: str | None = Field(default=None, description="Source file path as reported.")
    line: int | None = Field(default=None, description="1-based line number.")
    column: int | None = Field(default=None, description="1-based column number.")
    project: str | None = Field(default=None, description="Project the diagnostic was reported in.")


class AnalysisResult(BaseModel):
    code_source: str = Field(description="The csproj/sln path Acuminator analyzed.")
    total_diagnostics: int
    diagnostics: list[Diagnostic]


def _parse_line_string(
    text: str, inherited_code: str | None
) -> tuple[str, str | None, int | None, int | None] | None:
    """Parse one Line string into ``(code, file, line, column)``.

    ``inherited_code`` is the nearest PX#### ancestor groupTitle, used when the
    line itself is 2-span (no inline code). Roslyn positions are 0-based; the
    returned line/column are 1-based.
    """
    stripped = text.strip()
    if not stripped:
        return None

    loc_match = _LOCATION_PATTERN.search(stripped)
    file_path: str | None = None
    line_no: int | None = None
    col_no: int | None = None
    if loc_match:
        file_path = loc_match.group("file")
        try:
            line_no = int(loc_match.group("line")) + 1
            col_no = int(loc_match.group("col")) + 1
        except ValueError:
            line_no = col_no = None
        prefix = stripped[: loc_match.start()].rstrip()
        prefix = prefix.rstrip(":").rstrip()
    else:
        prefix = stripped

    code_match = _PX_CODE_PATTERN.match(prefix)
    if code_match:
        code = code_match.group(1)
    elif inherited_code is not None:
        code = inherited_code
    else:
        return None

    return code, file_path, line_no, col_no


def _title_text(node: dict[str, Any]) -> str | None:
    title = node.get("groupTitle") or node.get("GroupTitle")
    if isinstance(title, str):
        return title.strip() or None
    if isinstance(title, dict):
        for key in ("text", "Text", "titleText"):
            val = title.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _walk_lines(node: dict[str, Any], inherited_code: str | None = None):
    """Yield ``(line_string, code_for_line)`` for every leaf line in the tree."""
    title = _title_text(node)
    code_here = inherited_code
    if title and _PX_CODE_PATTERN.match(title):
        code_here = _PX_CODE_PATTERN.match(title).group(1)

    for raw in node.get("lines") or []:
        yield raw, code_here
    for child in node.get("childrenGroups") or []:
        yield from _walk_lines(child, code_here)


def _extract_diagnostics(project_name: str, report_details: dict[str, Any] | None) -> list[Diagnostic]:
    if not report_details:
        return []
    out: list[Diagnostic] = []
    for raw_line, inherited_code in _walk_lines(report_details):
        if not isinstance(raw_line, str):
            continue
        parsed = _parse_line_string(raw_line, inherited_code)
        if parsed is None:
            continue
        code, file_path, line_no, col_no = parsed
        out.append(
            Diagnostic(
                code=code,
                file=file_path,
                line=line_no,
                column=col_no,
                project=project_name,
            )
        )
    return out


def parse_report(json_text: str) -> AnalysisResult:
    """Parse an Acuminator JSON report into a flat :class:`AnalysisResult`."""
    data = json.loads(json_text)
    code_source = data.get("codeSourceName") or data.get("CodeSourceName") or ""
    total = data.get("totalDiagnosticsCount") or data.get("TotalDiagnosticsCount") or 0

    diagnostics: list[Diagnostic] = []
    for project in data.get("projectReports") or data.get("ProjectReports") or []:
        project_name = project.get("projectName") or project.get("ProjectName") or ""
        report_details = project.get("reportDetails") or project.get("ReportDetails")
        diagnostics.extend(_extract_diagnostics(project_name, report_details))

    if total == 0 and diagnostics:
        total = len(diagnostics)
    return AnalysisResult(code_source=code_source, total_diagnostics=total, diagnostics=diagnostics)


def parse_report_file(path: Path) -> AnalysisResult:
    return parse_report(path.read_text(encoding="utf-8"))
