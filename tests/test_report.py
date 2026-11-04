"""Tests for the Acuminator JSON report parser.

Fixtures mirror the real runner output: ``Line`` strings in Roslyn's
``FileLinePositionSpan.ToString()`` format, and ``groupTitle`` strings that
TitleConverter flattens to a plain string per its Write method.
"""

from __future__ import annotations

import json
from pathlib import Path

from acuminator_mcp.report import Diagnostic, parse_report, summarize


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
    assert d.message == "Event handlers should be protected virtual"
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
    assert d.message == "DAC should have a primary key"
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


def test_message_with_quoted_names_does_not_capture_them_as_file() -> None:
    """PX1069 et al embed quoted DAC/field names in the message. The file
    regex has to anchor on the real location's opening quote, not the first
    quote it sees — otherwise ``file`` ends up containing the whole message.
    """
    line = (
        '"LSJMForecastsFilter" DAC must declare the mandatory "tstamp", '
        '"CreatedByID", "LastModifiedDateTime" DAC fields: '
        '"D:\\Repos\\janMarini\\src\\LSJMForecastsFilter.cs: (12,13)-(12,38)"'
    )
    report = _report("MyProj", {
        "childrenGroups": [{"groupTitle": "PX1069", "lines": [line]}],
    })
    d = parse_report(json.dumps(report)).diagnostics[0]
    assert d.code == "PX1069"
    assert d.message == (
        '"LSJMForecastsFilter" DAC must declare the mandatory "tstamp", '
        '"CreatedByID", "LastModifiedDateTime" DAC fields'
    )
    assert d.file == "D:\\Repos\\janMarini\\src\\LSJMForecastsFilter.cs"
    assert d.line == 13
    assert d.column == 14


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
    assert d.message == "Some unstructured message with no location"
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


# --- summarize ---------------------------------------------------------------


def _diag(code: str, message: str, file: str, line: int) -> Diagnostic:
    return Diagnostic(code=code, message=message, file=file, line=line, column=5, project="P")


def test_summarize_groups_by_code_and_message_with_relative_paths() -> None:
    base = Path(r"D:\src\MyExt")
    diags = [
        _diag("PX1014", "needs nullable", r"D:\src\MyExt\DAC\A.cs", 10),
        _diag("PX1014", "needs nullable", r"D:\src\MyExt\DAC\B.cs", 20),
        _diag("PX1069", '"A" must declare "tstamp"', r"D:\src\MyExt\DAC\A.cs", 1),
        _diag("PX1069", '"B" must declare "tstamp"', r"D:\src\MyExt\DAC\B.cs", 1),
    ]
    result = summarize(diags, code_source="MyExt.csproj", base_dir=base)

    assert result.total_diagnostics == 4
    assert result.counts_by_code == {"PX1014": 2, "PX1069": 2}
    assert result.truncated is False
    # Largest group first; same-size groups ordered by code.
    assert [(g.code, g.message, g.locations) for g in result.groups] == [
        ("PX1014", "needs nullable", ["DAC/A.cs:10:5", "DAC/B.cs:20:5"]),
        ("PX1069", '"A" must declare "tstamp"', ["DAC/A.cs:1:5"]),
        ("PX1069", '"B" must declare "tstamp"', ["DAC/B.cs:1:5"]),
    ]


def test_summarize_caps_locations_but_keeps_full_counts() -> None:
    diags = [_diag("PX1014", "m", rf"D:\src\F{i}.cs", i) for i in range(5)]
    diags.append(_diag("PX1030", "other", r"D:\src\G.cs", 1))
    result = summarize(diags, code_source="x.csproj", base_dir=Path(r"D:\src"), max_diagnostics=3)

    assert result.truncated is True
    assert result.total_diagnostics == 6
    assert result.counts_by_code == {"PX1014": 5, "PX1030": 1}
    assert len(result.groups) == 1
    assert result.groups[0].locations == ["F0.cs:0:5", "F1.cs:1:5", "F2.cs:2:5"]


def test_summarize_keeps_absolute_path_when_not_relative_to_base() -> None:
    diags = [_diag("PX1014", "m", r"E:\elsewhere\F.cs", 3)]
    result = summarize(diags, code_source="x.csproj", base_dir=Path(r"D:\src"))
    assert result.groups[0].locations == ["E:/elsewhere/F.cs:3:5"]


def test_summarize_location_without_line_is_just_the_path() -> None:
    diags = [Diagnostic(code="PX1014", message="m", file=r"D:\src\F.cs")]
    result = summarize(diags, code_source="x.csproj", base_dir=Path(r"D:\src"))
    assert result.groups[0].locations == ["F.cs"]
