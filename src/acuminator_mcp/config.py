from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RUNNER_VERSION = "4.0.1"

RUNNER_VERSION = os.environ.get("ACUMINATOR_MCP_RUNNER_VERSION", DEFAULT_RUNNER_VERSION)

RUNNER_RELEASE_URL = (
    "https://github.com/Acumatica/Acuminator/releases/download/"
    "v{version}/Acuminator.Runner.NetFramework.zip"
)

RUNNER_EXE_NAME = "Acuminator.Runner.NetFramework.exe"

DOCS_RAW_URL = (
    "https://raw.githubusercontent.com/Acumatica/Acuminator/refs/heads/master/docs/diagnostics/{code}.md"
)


def _default_cache_root() -> Path:
    override = os.environ.get("ACUMINATOR_MCP_CACHE")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "acuminator-mcp"
    return Path.home() / ".cache" / "acuminator-mcp"


CACHE_ROOT = _default_cache_root()
RUNNER_CACHE = CACHE_ROOT / "runner"
DOCS_CACHE = CACHE_ROOT / "docs"


def reference_project_path() -> Path | None:
    """Return the configured Acumatica reference project, if any.

    Used by the snippet tool to supply the Acumatica Framework type environment.
    """
    value = os.environ.get("ACUMINATOR_MCP_REFERENCE_PROJECT")
    return Path(value) if value else None
