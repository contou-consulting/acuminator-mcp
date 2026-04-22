"""Tests for the Acuminator JSON report parser.

Fixtures here mirror the shape produced by
``Acuminator.Runner.NetFramework --format json``: a recursive
``CodeSourceReport → ProjectReport → ReportGroup`` tree where each leaf Line
carries three spans ``[diagnosticId, message, "<file>(<line>,<col>)"]``.
"""

from __future__ import annotations

import json

from acuminator_mcp.report import parse_report


def _line(*spans: str) -> dict:
    return {"spans": [{"text": s} for s in spans]}


def _span_report(project_name: str, lines: list[dict]) -> dict:
    return {
        "codeSourceName": "Solution.sln",
        "totalDiagnosticsCount": len(lines),
        "projectReports": [
            {
                "projectName": project_name,
                "totalDiagnosticsCount": len(lines),
                "distinctDiagnosticsCount": 1,
                "reportDetails": {
                    "groupTitle": project_name,
                    "totalDiagnosticsCount": len(lines),
                    "distinctDiagnosticsCount": 1,
                    "lines": lines,
                    "childrenGroups": [],
                    "hasContent": True,
                },
            }
        ],
    }


def test_flat_lines_are_parsed() -> None:
    report = _span_report(
        "MyProject",
        [
            _line("PX1014", "DAC should have a primary key", '"C:\\src\\Foo.cs"(12,5)'),
            _line("PX1030", "Use PXDefaultAttribute on the primary key field", '"C:\\src\\Foo.cs"(20,9)'),
        ],
    )
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 2
    assert [d.code for d in result.diagnostics] == ["PX1014", "PX1030"]
    first = result.diagnostics[0]
    assert first.message.startswith("DAC should have a primary key")
    assert first.file == "C:\\src\\Foo.cs"
    assert first.line == 12
    assert first.column == 5
    assert first.project == "MyProject"


def test_nested_report_groups_are_walked() -> None:
    """Lines inside childrenGroups (used when -g fd grouping is applied) are flattened."""
    report = {
        "codeSourceName": "Solution.sln",
        "totalDiagnosticsCount": 1,
        "projectReports": [
            {
                "projectName": "Nested",
                "reportDetails": {
                    "lines": [],
                    "childrenGroups": [
                        {
                            "groupTitle": "Foo.cs",
                            "lines": [],
                            "childrenGroups": [
                                {
                                    "groupTitle": "PX1014",
                                    "lines": [
                                        _line(
                                            "PX1014",
                                            "DAC should have a primary key",
                                            '"Foo.cs"(7,3)',
                                        )
                                    ],
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    }
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 1
    d = result.diagnostics[0]
    assert d.code == "PX1014"
    assert d.file == "Foo.cs"
    assert d.line == 7
    assert d.column == 3


def test_spans_without_a_px_code_are_ignored() -> None:
    """Non-diagnostic lines (e.g. summary rows) must not produce records."""
    report = _span_report("MyProject", [_line("Found 0 errors", "", "")])
    result = parse_report(json.dumps(report))
    assert result.diagnostics == []


def test_missing_location_yields_none_file_and_line() -> None:
    report = _span_report("MyProject", [_line("PX1014", "Boom", "not-a-location")])
    result = parse_report(json.dumps(report))
    d = result.diagnostics[0]
    assert d.code == "PX1014"
    assert d.file is None
    assert d.line is None
    assert d.column is None
    assert d.message == "Boom not-a-location"


def test_empty_report_is_parsed() -> None:
    report = {"codeSourceName": "Empty.sln", "totalDiagnosticsCount": 0, "projectReports": []}
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 0
    assert result.diagnostics == []
