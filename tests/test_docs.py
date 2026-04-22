from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from acuminator_mcp import docs
from acuminator_mcp.docs import DocsError, get_diagnostic_docs


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
        text = "# PX1014\n\nContent."

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

    md1 = await get_diagnostic_docs("px1014")
    md2 = await get_diagnostic_docs("PX1014")

    assert md1 == md2 == "# PX1014\n\nContent."
    assert len(calls) == 1, "Second call should be served from disk cache"
    assert (cache / "PX1014.md").is_file()


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
