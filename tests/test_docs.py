from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from acuminator_mcp import docs
from acuminator_mcp.docs import DocsError, get_diagnostic_docs, trim_docs

_FULL_DOC = (
    "# PX1069\n\n## Summary\n\n| Code | Short |\n|---|---|\n| PX1069 | x |\n\n"
    "## Diagnostic Description\n\nBody.\n\n### Nested\n\n#### Example of Incorrect Code\n\nkept, nested\n\n"
    "## Example of Incorrect Code\n\n```csharp\nbad\n```\n\n"
    "## Example of Code Fix\n\n```csharp\ngood\n```\n\n"
    "## Related Articles\n\n- link\n"
)


def test_trim_docs_drops_only_top_level_noise_sections() -> None:
    trimmed = trim_docs(_FULL_DOC)
    assert "## Summary" in trimmed
    assert "## Diagnostic Description" in trimmed
    assert "#### Example of Incorrect Code\n\nkept, nested" in trimmed
    assert "## Example of Code Fix" in trimmed and "good" in trimmed
    assert "\n## Example of Incorrect Code" not in trimmed
    assert "bad" not in trimmed
    assert "Related Articles" not in trimmed
    assert trimmed.endswith("```\n")


def test_trim_docs_without_sections_is_identity() -> None:
    assert trim_docs("# PX1014\n\nContent.\n") == "# PX1014\n\nContent.\n"


def test_invalid_code_raises() -> None:
    import asyncio

    async def _run() -> None:
        with pytest.raises(DocsError):
            await get_diagnostic_docs("not-a-code")

    asyncio.run(_run())


async def test_docs_are_fetched_and_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / "docs"
    monkeypatch.setattr(docs, "DOCS_CACHE", cache)

    calls: list[str] = []

    class _StubResponse:
        status_code = 200
        text = _FULL_DOC

    class _StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> _StubClient:
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str) -> _StubResponse:
            calls.append(url)
            return _StubResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    md1 = await get_diagnostic_docs("px1069")
    md2 = await get_diagnostic_docs("PX1069")
    md_full = await get_diagnostic_docs("PX1069", full=True)

    assert md1 == md2 == trim_docs(_FULL_DOC)
    assert md_full == _FULL_DOC, "full=True returns the untrimmed document"
    assert len(calls) == 1, "Later calls should be served from disk cache"
    assert (cache / "PX1069.md").read_text(encoding="utf-8") == _FULL_DOC, "cache holds the full doc"


async def test_404_raises_docs_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(docs, "DOCS_CACHE", tmp_path / "docs")

    class _StubResponse:
        status_code = 404
        text = "Not Found"

    class _StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> _StubClient:
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str) -> _StubResponse:
            return _StubResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    with pytest.raises(DocsError):
        await get_diagnostic_docs("PX9999")
