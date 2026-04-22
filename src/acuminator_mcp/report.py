"""Parse the Acuminator runner's JSON report into flat diagnostic records.

The runner emits a recursive ``CodeSourceReport → ProjectReport → ReportGroup``
structure. Each leaf ``Line`` is serialized by Acuminator's ``LineConverter`` as
a **plain JSON string** (not an object), in one of two shapes:

* 3-span (the common diagnostic shape):
  ``"<diagnosticId>: <message>: <location>"``
* 2-span (rare, used for some summary/suppression lines):
  ``"<content>: <location>"``

Where ``<location>`` is ``"<file>"(<line>,<column>)`` — quoted when
``--output-absolute-paths-for-errors`` is set (we always pass that).

This module walks the tree and produces flat :class:`Diagnostic` records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_LOCATION_PATTERN = re.compile(r'"?(?P<file>[^"]+?)"?\((?P<line>\d+),(?P<col>\d+)\)\s*$')
_PX_CODE_PATTERN = re.compile(r"^(PX\d{4})\b")


class Diagnostic(BaseModel):
    code: str = Field(description="Acuminator diagnostic ID, e.g. PX1014.")
    message: str = Field(description="Human-readable diagnostic message.")
    file: str | None = Field(default=None, description="Source file path as reported.")
    line: int | None = Field(default=None, description="1-based line number.")
    column: int | None = Field(default=None, description="1-based column number.")
    project: str | None = Field(default=None, description="Project the diagnostic was reported in.")


class AnalysisResult(BaseModel):
    code_source: str = Field(description="The csproj/sln path Acuminator analyzed.")
    total_diagnostics: int
    diagnostics: list[Diagnostic]


def _parse_line_string(text: str) -> tuple[str, str, str | None, int | None, int | None] | None:
    """Parse one ``LineConverter``-formatted string into ``(code, message, file, line, col)``.

    Returns ``None`` if the string isn't a PX diagnostic (e.g. summary rows).
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
            line_no = int(loc_match.group("line"))
            col_no = int(loc_match.group("col"))
        except ValueError:
            line_no = col_no = None
        prefix = stripped[: loc_match.start()].rstrip()
        prefix = prefix.rstrip(":").rstrip()
    else:
        prefix = stripped

    code_match = _PX_CODE_PATTERN.match(prefix)
    if not code_match:
        return None
    code = code_match.group(1)
    remainder = prefix[code_match.end() :].lstrip(":").strip()
    message = remainder or "(no message)"
    return code, message, file_path, line_no, col_no


def _walk_lines(node: dict[str, Any]):
    """Yield every ``Line`` (string) anywhere beneath ``node`` in the ReportGroup tree."""
    yield from node.get("lines") or []
    for child in node.get("childrenGroups") or []:
        yield from _walk_lines(child)


def _extract_diagnostics(project_name: str, report_details: dict[str, Any] | None) -> list[Diagnostic]:
    if not report_details:
        return []
    out: list[Diagnostic] = []
    for raw_line in _walk_lines(report_details):
        if not isinstance(raw_line, str):
            continue
        parsed = _parse_line_string(raw_line)
        if parsed is None:
            continue
        code, message, file_path, line_no, col_no = parsed
        out.append(
            Diagnostic(
                code=code,
                message=message,
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
