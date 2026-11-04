"""The version is declared in four places; a release with them out of step ships
a wheel whose name doesn't match its tag, or a plugin pinned to the wrong tag."""

from __future__ import annotations

import json
import re
from pathlib import Path

import acuminator_mcp

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_version_sites_agree() -> None:
    pyproject = re.search(r'^version = "([^"]+)"', _read("pyproject.toml"), re.MULTILINE).group(1)
    plugin = json.loads(_read(".claude-plugin/plugin.json"))["version"]
    mcp_args = json.loads(_read(".mcp.json"))["acuminator"]["args"]
    pin = next(re.search(r"@v(\S+)$", a).group(1) for a in mcp_args if "@v" in a)
    readme_pins = set(re.findall(r"acuminator-mcp\.git@v(\d+\.\d+\.\d+)", _read("README.md")))

    assert acuminator_mcp.__version__ == pyproject == plugin == pin
    assert readme_pins == {pyproject}
