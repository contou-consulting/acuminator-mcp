from __future__ import annotations

from pathlib import Path

from acuminator_mcp.suppression import EMPTY_SUPPRESSION_FILE, ensure_suppression_setup, projects_in

_CSPROJ = '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n  </PropertyGroup>\n</Project>\n'


def test_creates_file_and_adds_additional_files_item(tmp_path: Path) -> None:
    csproj = tmp_path / "My.Ext.csproj"
    csproj.write_text(_CSPROJ, encoding="utf-8")

    files, modified = ensure_suppression_setup(csproj)

    assert files == [tmp_path / "My.Ext.acuminator"]
    assert modified == [csproj]
    assert files[0].read_text(encoding="utf-8") == EMPTY_SUPPRESSION_FILE
    text = csproj.read_text(encoding="utf-8")
    assert '<AdditionalFiles Include="My.Ext.acuminator" />' in text
    assert text.rstrip().endswith("</Project>")
    assert text.index("<AdditionalFiles") < text.index("</Project>")


def test_is_idempotent_and_keeps_existing_file(tmp_path: Path) -> None:
    csproj = tmp_path / "My.Ext.csproj"
    csproj.write_text(_CSPROJ, encoding="utf-8")
    ensure_suppression_setup(csproj)
    (tmp_path / "My.Ext.acuminator").write_text("<suppressions><x/></suppressions>", encoding="utf-8")
    before = csproj.read_text(encoding="utf-8")

    files, modified = ensure_suppression_setup(csproj)

    assert modified == []
    assert csproj.read_text(encoding="utf-8") == before
    assert files[0].read_text(encoding="utf-8") == "<suppressions><x/></suppressions>"


def test_existing_reference_with_relative_path_is_recognized(tmp_path: Path) -> None:
    csproj = tmp_path / "My.Ext.csproj"
    csproj.write_text(
        '<Project>\n  <ItemGroup>\n    <AdditionalFiles Include=".\\My.Ext.acuminator"/>\n  </ItemGroup>\n</Project>',
        encoding="utf-8",
    )
    _, modified = ensure_suppression_setup(csproj)
    assert modified == []


def test_preserves_bom_and_crlf(tmp_path: Path) -> None:
    csproj = tmp_path / "My.Ext.csproj"
    original = b"\xef\xbb\xbf<Project>\r\n  <PropertyGroup>\r\n  </PropertyGroup>\r\n</Project>"
    csproj.write_bytes(original)

    ensure_suppression_setup(csproj)

    out = csproj.read_bytes()
    assert out.startswith(b"\xef\xbb\xbf")
    assert b"\n" not in out.replace(b"\r\n", b"")
    assert out.endswith(b"</Project>"), "no trailing newline added when the original had none"
    assert b'    <AdditionalFiles Include="My.Ext.acuminator" />\r\n' in out


def test_projects_in_solution(tmp_path: Path) -> None:
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    sln = tmp_path / "All.sln"
    sln.write_text(
        "﻿Microsoft Visual Studio Solution File, Format Version 12.00\n"
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "A", "A\\A.csproj", "{1}"\nEndProject\n'
        'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "Solution Items", "Solution Items", "{2}"\nEndProject\n'
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "B", "B\\B.csproj", "{3}"\nEndProject\n',
        encoding="utf-8",
    )
    assert projects_in(sln) == [tmp_path / "A" / "A.csproj", tmp_path / "B" / "B.csproj"]
