"""Acquire and invoke the Acuminator console runner.

The runner is distributed only as a GitHub release asset (not on NuGet). We
download the pinned version on first use, cache it under
``%LOCALAPPDATA%\\acuminator-mcp\\runner\\v<ver>``, and invoke it as a subprocess.

The runner requires .NET Framework 4.8 (Windows only).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

from acuminator_mcp.config import (
    RUNNER_CACHE,
    RUNNER_EXE_NAME,
    RUNNER_RELEASE_URL,
    RUNNER_VERSION,
)


class RunnerError(RuntimeError):
    """Raised when the Acuminator runner cannot be acquired or invoked."""


def _version_dir(version: str) -> Path:
    return RUNNER_CACHE / f"v{version}"


def _exe_path(version: str) -> Path:
    return _version_dir(version) / RUNNER_EXE_NAME


def is_runner_cached(version: str = RUNNER_VERSION) -> bool:
    return _exe_path(version).is_file()


async def ensure_runner(version: str = RUNNER_VERSION) -> Path:
    """Download and extract the runner if not already cached. Returns the exe path."""
    exe = _exe_path(version)
    if exe.is_file():
        return exe

    if sys.platform != "win32":
        raise RunnerError(
            "Acuminator runner requires Windows + .NET Framework 4.8. "
            f"Current platform: {sys.platform}."
        )

    url = RUNNER_RELEASE_URL.format(version=version)
    dest_dir = _version_dir(version)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        suffix=".zip", delete=False, dir=str(dest_dir)
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client,
            client.stream("GET", url) as resp,
        ):
            if resp.status_code != 200:
                raise RunnerError(
                    f"Failed to download Acuminator runner v{version} from {url} "
                    f"(HTTP {resp.status_code}). Check that the release exists."
                )
            with tmp_path.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                    f.write(chunk)

        with zipfile.ZipFile(tmp_path) as zf:
            zf.extractall(dest_dir)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not exe.is_file():
        raise RunnerError(
            f"Runner exe not found after extraction. Expected at {exe}. "
            "The release zip layout may have changed."
        )
    return exe


async def run_analysis(
    code_source: Path,
    *,
    output_json: Path,
    isv_mode: bool = False,
    enable_px1007: bool = False,
    disable_px1099: bool = False,
    enable_info_diagnostics: bool = False,
    verbosity: str = "Warning",
    extra_args: list[str] | None = None,
    timeout_seconds: float = 600.0,
) -> tuple[int, str]:
    """Run Acuminator on ``code_source`` (csproj/sln), writing JSON to ``output_json``.

    Returns ``(exit_code, stderr_text)``. The runner exits non-zero when diagnostics
    are reported — that's not necessarily an error. Callers should still attempt to
    parse the JSON and surface diagnostics.
    """
    exe = await ensure_runner()

    args: list[str] = [
        str(exe),
        str(code_source),
        "--format",
        "json",
        "-f",
        str(output_json),
        "--non-interactive",
        "--verbosity",
        verbosity,
        "--output-absolute-paths-for-errors",
    ]
    if isv_mode:
        args.append("--isv-mode")
    if enable_px1007:
        args.append("--enable-PX1007")
    if disable_px1099:
        args.append("--disable-PX1099")
    if enable_info_diagnostics:
        args.append("--enable-info-diagnostics")
    if extra_args:
        args.extend(extra_args)

    env = os.environ.copy()

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RunnerError(
            f"Acuminator runner timed out after {timeout_seconds}s on {code_source}"
        ) from e

    stderr_text = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
    stdout_text = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
    combined = (stderr_text + "\n" + stdout_text).strip()
    return proc.returncode or 0, combined


def clear_cache(version: str | None = None) -> None:
    """Remove cached runner(s). Useful for forcing a re-download."""
    target = _version_dir(version) if version else RUNNER_CACHE
    if target.exists():
        shutil.rmtree(target)
