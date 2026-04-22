"""Tests for the Acuminator JSON report parser.

Acuminator's ``LineConverter`` serializes each ``Line`` as a plain JSON string
shaped like ``"PX1014: <message>: \\"<file>\\"(<line>,<col>)"``. These fixtures
match that real shape.
"""

from __future__ import annotations

import json

from acuminator_mcp.report import parse_report


def _span_report(project_name: str, lines: list[str]) -> dict:
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


def test_three_span_lines_are_parsed() -> None:
    report = _span_report(
        "MyProject",
        [
            'PX1014: DAC should have a primary key: "C:\\src\\Foo.cs"(12,5)',
            'PX1030: Use PXDefaultAttribute on the primary key field: "C:\\src\\Foo.cs"(20,9)',
        ],
    )
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 2
    assert [d.code for d in result.diagnostics] == ["PX1014", "PX1030"]
    first = result.diagnostics[0]
    assert first.message == "DAC should have a primary key"
    assert first.file == "C:\\src\\Foo.cs"
    assert first.line == 12
    assert first.column == 5
    assert first.project == "MyProject"


def test_nested_report_groups_are_walked() -> None:
    """Lines inside childrenGroups (used when ``-g fd`` is applied) are flattened."""
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
                                        'PX1014: DAC should have a primary key: "Foo.cs"(7,3)'
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


def test_messages_containing_colons_and_quotes_are_preserved() -> None:
    """Message can contain ``: `` — we anchor the location match at the end of the string."""
    msg = 'The type \'Foo\': expected "Bar" here'
    report = _span_report(
        "MyProject",
        [f'PX1099: {msg}: "C:\\src\\Foo.cs"(3,11)'],
    )
    result = parse_report(json.dumps(report))
    d = result.diagnostics[0]
    assert d.code == "PX1099"
    assert d.message == msg
    assert d.file == "C:\\src\\Foo.cs"


def test_lines_without_a_px_code_are_ignored() -> None:
    """Summary rows (no PX prefix) must not produce records."""
    report = _span_report("MyProject", ["Found 0 errors in 3 files."])
    result = parse_report(json.dumps(report))
    assert result.diagnostics == []


def test_line_without_location_still_yields_a_record() -> None:
    report = _span_report("MyProject", ["PX1014: DAC should have a primary key"])
    result = parse_report(json.dumps(report))
    d = result.diagnostics[0]
    assert d.code == "PX1014"
    assert d.file is None
    assert d.line is None
    assert d.column is None
    assert d.message == "DAC should have a primary key"


def test_empty_report_is_parsed() -> None:
    report = {"codeSourceName": "Empty.sln", "totalDiagnosticsCount": 0, "projectReports": []}
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 0
    assert result.diagnostics == []


def test_non_string_line_items_are_skipped() -> None:
    """Defensive: if the runner ever emits something other than a string, skip it."""
    report = _span_report("MyProject", [{"unexpected": "shape"}])  # type: ignore[list-item]
    result = parse_report(json.dumps(report))
    assert result.diagnostics == []
