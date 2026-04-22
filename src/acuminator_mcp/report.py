"""Parse the Acuminator runner's JSON report into flat diagnostic records.

The runner emits a recursive ``CodeSourceReport → ProjectReport → ReportGroup``
structure. Each leaf diagnostic is a ``Line`` with three ``LineSpan`` entries:
``[diagnosticId, message, "<file>(<line>,<column>)"]``.

This module walks that tree and yields flat :class:`Diagnostic` records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_LOCATION_PATTERN = re.compile(r'^"?(.+?)"?\((\d+),(\d+)\)"?$')
_PX_CODE_PATTERN = re.compile(r"^PX\d{4}$")


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


def _parse_location(text: str) -> tuple[str | None, int | None, int | None]:
    m = _LOCATION_PATTERN.match(text.strip())
    if not m:
        return None, None, None
    try:
        return m.group(1), int(m.group(2)), int(m.group(3))
    except ValueError:
        return m.group(1), None, None


def _spans_text(line: dict[str, Any]) -> list[str]:
    spans = line.get("spans") or []
    out: list[str] = []
    for s in spans:
        text = s.get("text") if isinstance(s, dict) else None
        if text:
            out.append(text)
    return out


def _walk_groups(node: dict[str, Any]):
    yield from node.get("lines") or []
    for child in node.get("childrenGroups") or []:
        yield from _walk_groups(child)


def _extract_diagnostics(project_name: str, report_details: dict[str, Any] | None) -> list[Diagnostic]:
    if not report_details:
        return []
    out: list[Diagnostic] = []
    for line in _walk_groups(report_details):
        texts = _spans_text(line)
        if not texts:
            continue
        code = next((t for t in texts if _PX_CODE_PATTERN.match(t)), None)
        if not code:
            continue
        remaining = [t for t in texts if t != code]
        file_path: str | None = None
        line_no: int | None = None
        col_no: int | None = None
        message_parts: list[str] = []
        for t in remaining:
            f, ln, col = _parse_location(t)
            if f and file_path is None:
                file_path, line_no, col_no = f, ln, col
            else:
                message_parts.append(t)
        message = " ".join(message_parts).strip() or "(no message)"
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
