"""The version is declared in four places; a release with them out of step ships
a wheel whose name doesn't match its tag, or a plugin pinned to the wrong tag."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import acuminator_mcp

ROOT = Path(__file__).resolve().parent.parent


def test_version_sites_agree() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    mcp_args = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["acuminator"]["args"]
    pin = next(re.search(r"@v(\S+)$", a).group(1) for a in mcp_args if "@v" in a)
    readme_pins = set(re.findall(r"acuminator-mcp\.git@v(\d+\.\d+\.\d+)", (ROOT / "README.md").read_text(encoding="utf-8")))

    assert acuminator_mcp.__version__ == pyproject == plugin == pin
    assert readme_pins == {pyproject}
