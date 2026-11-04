"""Check the command line ``run_analysis`` builds, without invoking the runner."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from acuminator_mcp import runner


class _FakeProc:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


@pytest.fixture
def captured_args(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def fake_ensure_runner() -> Path:
        return Path(r"C:\cache\Acuminator.Runner.NetFramework.exe")

    async def fake_exec(*args, **kwargs) -> _FakeProc:
        calls.extend(args)
        return _FakeProc()

    monkeypatch.setattr(runner, "ensure_runner", fake_ensure_runner)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


async def test_defaults_pass_no_optional_flags(captured_args: list[str]) -> None:
    await runner.run_analysis(Path(r"D:\p\P.csproj"), output_json=Path(r"D:\t\r.json"))
    assert captured_args[1] == r"D:\p\P.csproj"
    for flag in ("--disable-suppression", "--banned-APIs-path", "--allowed-APIs-path", "--work-mode", "--isv-mode"):
        assert flag not in captured_args


async def test_suppression_and_api_list_flags(captured_args: list[str]) -> None:
    await runner.run_analysis(
        Path(r"D:\p\P.csproj"),
        output_json=Path(r"D:\t\r.json"),
        disable_suppression=True,
        banned_apis_path=Path(r"D:\p\banned.txt"),
        allowed_apis_path=Path(r"D:\p\allowed.txt"),
        work_mode="report-and-generate",
    )
    assert "--disable-suppression" in captured_args
    assert captured_args[captured_args.index("--banned-APIs-path") + 1] == r"D:\p\banned.txt"
    assert captured_args[captured_args.index("--allowed-APIs-path") + 1] == r"D:\p\allowed.txt"
    assert captured_args[captured_args.index("--work-mode") + 1] == "report-and-generate"
