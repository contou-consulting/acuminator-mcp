"""Tests for the Acuminator JSON report parser.

Fixtures mirror the real runner output: ``Line`` strings in Roslyn's
``FileLinePositionSpan.ToString()`` format, and ``groupTitle`` strings that
TitleConverter flattens to a plain string per its Write method.
"""

from __future__ import annotations

import json

from acuminator_mcp.report import parse_report


def _report(project_name: str, tree: dict) -> dict:
    return {
        "codeSourceName": "Solution.sln",
        "totalDiagnosticsCount": 0,
        "projectReports": [
            {
                "projectName": project_name,
                "reportDetails": tree,
            }
        ],
    }


def test_two_span_line_uses_inherited_group_title_as_code() -> None:
    """Grouped-by-ID case: line has no inline PX####; code lives on the parent ReportGroup."""
    report = _report(
        "MyProj",
        {
            "lines": [],
            "childrenGroups": [
                {
                    "groupTitle": "PX1075",
                    "lines": [
                        'Event handlers should be protected virtual: "D:\\src\\Foo.cs: (68,22)-(68,23)"'
                    ],
                }
            ],
        },
    )
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 1
    d = result.diagnostics[0]
    assert d.code == "PX1075"
    assert d.file == "D:\\src\\Foo.cs"
    assert d.line == 69
    assert d.column == 23
    assert d.project == "MyProj"


def test_three_span_line_carries_its_own_code() -> None:
    """Ungrouped case: line starts with PX####, no parent title needed."""
    report = _report(
        "MyProj",
        {
            "lines": [
                'PX1014: DAC should have a primary key: "C:\\src\\Foo.cs: (11,4)-(11,16)"'
            ],
            "childrenGroups": [],
        },
    )
    d = parse_report(json.dumps(report)).diagnostics[0]
    assert d.code == "PX1014"
    assert d.line == 12
    assert d.column == 5


def test_inline_code_beats_inherited_code() -> None:
    """If both are present, the inline PX#### on the line wins."""
    report = _report(
        "MyProj",
        {
            "groupTitle": "PX1030",
            "lines": [
                'PX1014: DAC should have a primary key: "C:\\src\\Foo.cs: (0,0)-(0,5)"'
            ],
            "childrenGroups": [],
        },
    )
    assert parse_report(json.dumps(report)).diagnostics[0].code == "PX1014"


def test_nested_groups_propagate_the_nearest_px_title() -> None:
    report = _report(
        "MyProj",
        {
            "groupTitle": "File-level group (no code here)",
            "lines": [],
            "childrenGroups": [
                {
                    "groupTitle": "Foo.cs",
                    "lines": [],
                    "childrenGroups": [
                        {
                            "groupTitle": "PX1099",
                            "lines": [
                                'Banned API usage: "Foo.cs: (4,8)-(4,20)"'
                            ],
                        }
                    ],
                }
            ],
        },
    )
    d = parse_report(json.dumps(report)).diagnostics[0]
    assert d.code == "PX1099"
    assert d.line == 5
    assert d.column == 9


def test_line_without_a_discoverable_code_is_skipped() -> None:
    """No inline code, no PX#### ancestor title — can't produce a valid diagnostic."""
    report = _report(
        "MyProj",
        {
            "groupTitle": "Summary",
            "lines": ['Found 0 errors: "_: (0,0)-(0,0)"'],
            "childrenGroups": [],
        },
    )
    assert parse_report(json.dumps(report)).diagnostics == []


def test_line_without_a_parseable_location_still_yields_code_only() -> None:
    report = _report(
        "MyProj",
        {
            "groupTitle": "PX1014",
            "lines": ["Some unstructured message with no location"],
            "childrenGroups": [],
        },
    )
    d = parse_report(json.dumps(report)).diagnostics[0]
    assert d.code == "PX1014"
    assert d.file is None
    assert d.line is None
    assert d.column is None


def test_non_string_line_items_are_skipped() -> None:
    report = _report(
        "MyProj",
        {
            "groupTitle": "PX1014",
            "lines": [{"unexpected": "shape"}],
            "childrenGroups": [],
        },
    )
    assert parse_report(json.dumps(report)).diagnostics == []


def test_empty_report_is_parsed() -> None:
    report = {"codeSourceName": "Empty.sln", "totalDiagnosticsCount": 0, "projectReports": []}
    result = parse_report(json.dumps(report))
    assert result.total_diagnostics == 0
    assert result.diagnostics == []
