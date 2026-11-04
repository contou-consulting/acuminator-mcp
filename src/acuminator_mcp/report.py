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

:func:`parse_report` yields one flat :class:`Diagnostic` per hit.
:func:`summarize` then folds them into the compact :class:`AnalysisResult`
the MCP tools return: hits grouped by (code, message) with paths relative to
the analyzed project/solution directory, so the model pays for each message
once and never for a repeated absolute path prefix.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_LOCATION_PATTERN = re.compile(
    r'"(?P<file>[^"]+?):\s*\((?P<line>\d+),(?P<col>\d+)\)(?:-\(\d+,\d+\))?"\s*$'
)
_PX_CODE_PATTERN = re.compile(r"^(PX\d{4})\b")

DEFAULT_MAX_DIAGNOSTICS = 200


class Diagnostic(BaseModel):
    """One raw hit as parsed from the runner output."""

    code: str
    message: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    project: str | None = None


class ParsedReport(BaseModel):
    code_source: str
    total_diagnostics: int
    diagnostics: list[Diagnostic]


class DiagnosticGroup(BaseModel):
    code: str
    message: str | None = None
    locations: list[str]


class AnalysisResult(BaseModel):
    """Compact, model-facing shape. ``locations`` are ``path:line:col`` with
    ``path`` relative to the analyzed project/solution directory.
    ``counts_by_code`` is always complete; ``groups`` is truncated to
    ``max_diagnostics`` locations in total, in which case ``truncated`` is set.
    """

    code_source: str
    total_diagnostics: int
    counts_by_code: dict[str, int]
    groups: list[DiagnosticGroup]
    truncated: bool = False


def _parse_line_string(text: str, inherited_code: str | None) -> Diagnostic | None:
    """Parse one Line string. ``inherited_code`` is the nearest PX#### ancestor
    groupTitle, used when the line itself is 2-span (no inline code). Roslyn
    positions are 0-based; the returned line/column are 1-based.
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
        line_no = int(loc_match.group("line")) + 1
        col_no = int(loc_match.group("col")) + 1
        prefix = stripped[: loc_match.start()].rstrip()
        prefix = prefix.rstrip(":").rstrip()
    else:
        prefix = stripped

    code_match = _PX_CODE_PATTERN.match(prefix)
    if code_match:
        code = code_match.group(1)
        message = prefix[code_match.end() :]
    elif inherited_code is not None:
        code = inherited_code
        message = prefix
    else:
        return None

    message = message.strip().lstrip(":").strip()
    return Diagnostic(code=code, message=message or None, file=file_path, line=line_no, column=col_no)


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
    title_match = _PX_CODE_PATTERN.match(title) if title else None
    if title_match:
        code_here = title_match.group(1)

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
        parsed.project = project_name
        out.append(parsed)
    return out


def parse_report(json_text: str) -> ParsedReport:
    """Parse an Acuminator JSON report into flat :class:`Diagnostic` records."""
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
    return ParsedReport(code_source=code_source, total_diagnostics=total, diagnostics=diagnostics)


def parse_report_file(path: Path) -> ParsedReport:
    return parse_report(path.read_text(encoding="utf-8"))


def _relative_path(file: str, base_dir: Path | None) -> str:
    """``file`` relative to ``base_dir`` with forward slashes, or unchanged when
    it isn't under ``base_dir`` (e.g. another drive). Pure string work so the
    runner's Windows paths parse the same on every OS."""
    path = file.replace("\\", "/")
    if base_dir is None:
        return path
    base = str(base_dir).replace("\\", "/").rstrip("/") + "/"
    if path.lower().startswith(base.lower()):
        return path[len(base) :]
    return path


def _location(d: Diagnostic, base_dir: Path | None) -> str:
    path = _relative_path(d.file, base_dir) if d.file else "?"
    if d.line is None:
        return path
    return f"{path}:{d.line}:{d.column}"


def summarize(
    diagnostics: list[Diagnostic],
    *,
    code_source: str,
    base_dir: Path | None,
    total_diagnostics: int | None = None,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> AnalysisResult:
    """Fold flat diagnostics into the compact :class:`AnalysisResult`."""
    counts: dict[str, int] = {}
    groups: dict[tuple[str, str | None], list[str]] = {}
    for d in diagnostics:
        counts[d.code] = counts.get(d.code, 0) + 1
        groups.setdefault((d.code, d.message), []).append(_location(d, base_dir))

    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0]))
    out: list[DiagnosticGroup] = []
    budget = max(max_diagnostics, 0)
    truncated = False
    for (code, message), locations in ordered:
        if budget <= 0:
            truncated = True
            break
        if len(locations) > budget:
            locations = locations[:budget]
            truncated = True
        budget -= len(locations)
        out.append(DiagnosticGroup(code=code, message=message, locations=locations))

    return AnalysisResult(
        code_source=code_source,
        total_diagnostics=len(diagnostics) if total_diagnostics is None else total_diagnostics,
        counts_by_code=dict(sorted(counts.items())),
        groups=out,
        truncated=truncated,
    )
