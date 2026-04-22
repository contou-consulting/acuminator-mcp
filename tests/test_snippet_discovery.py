"""Tests for reference-project auto-discovery."""

from __future__ import annotations

from pathlib import Path

from acuminator_mcp.snippet import discover_reference_project


def _touch_csproj(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<Project />", encoding="utf-8")
    return path


def test_walks_up_from_a_nested_subdir(tmp_path: Path) -> None:
    csproj = _touch_csproj(tmp_path / "MyExt" / "MyExt.csproj")
    deep = tmp_path / "MyExt" / "DAC" / "Subfolder"
    deep.mkdir(parents=True)

    found = discover_reference_project(deep)

    assert found == csproj.resolve()


def test_scans_down_when_nothing_above(tmp_path: Path) -> None:
    csproj = _touch_csproj(tmp_path / "src" / "MyExt" / "MyExt.csproj")

    found = discover_reference_project(tmp_path)

    assert found == csproj.resolve()


def test_skips_noise_directories(tmp_path: Path) -> None:
    _touch_csproj(tmp_path / "bin" / "Generated.csproj")
    _touch_csproj(tmp_path / "obj" / "Generated.csproj")
    expected = _touch_csproj(tmp_path / "src" / "Real.csproj")

    found = discover_reference_project(tmp_path)

    assert found == expected.resolve()


def test_returns_none_when_no_csproj_present(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert discover_reference_project(tmp_path) is None


def test_prefers_csproj_in_start_dir_over_siblings(tmp_path: Path) -> None:
    expected = _touch_csproj(tmp_path / "MyExt.csproj")
    _touch_csproj(tmp_path / "sibling" / "Other.csproj")

    found = discover_reference_project(tmp_path)

    assert found == expected.resolve()
