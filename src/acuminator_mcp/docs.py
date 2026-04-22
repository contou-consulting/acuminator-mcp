"""Fetch Acuminator diagnostic documentation from the Acumatica/Acuminator repo.

Docs live at ``docs/diagnostics/<CODE>.md`` on the master branch. We fetch the
raw markdown on demand and cache it to disk so repeat lookups are free.
"""

from __future__ import annotations

import re

import httpx

from acuminator_mcp.config import DOCS_CACHE, DOCS_RAW_URL

_CODE_PATTERN = re.compile(r"^PX\d{4}$")


class DocsError(RuntimeError):
    """Raised when documentation can't be retrieved for a given diagnostic code."""


def _normalize_code(code: str) -> str:
    code = code.strip().upper()
    if not _CODE_PATTERN.match(code):
        raise DocsError(
            f"Invalid diagnostic code {code!r}. Expected the form PXNNNN, e.g. PX1014."
        )
    return code


async def get_diagnostic_docs(code: str, *, use_cache: bool = True) -> str:
    """Return the markdown documentation for an Acuminator diagnostic code.

    Raises :class:`DocsError` if the code isn't documented upstream.
    """
    normalized = _normalize_code(code)
    DOCS_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = DOCS_CACHE / f"{normalized}.md"

    if use_cache and cache_path.is_file():
        return cache_path.read_text(encoding="utf-8")

    url = DOCS_RAW_URL.format(code=normalized)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url)

    if resp.status_code == 404:
        raise DocsError(
            f"No documentation found for {normalized} at {url}. "
            "The diagnostic may not be publicly documented."
        )
    if resp.status_code != 200:
        raise DocsError(
            f"Failed to fetch docs for {normalized} (HTTP {resp.status_code}) from {url}."
        )

    markdown = resp.text
    cache_path.write_text(markdown, encoding="utf-8")
    return markdown
