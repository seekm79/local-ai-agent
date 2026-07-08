"""Runner tests: argv normalization, detection, and kill behavior (Phase 7)."""
from __future__ import annotations

import asyncio
import sys

import pytest

from app.services import runner as runner_mod
from app.services.runner import _normalize_argv, detect_runners, runner


def test_detect_dotnet(tmp_path):
    (tmp_path / "app.csproj").write_text("<Project/>", encoding="utf-8")
    kinds = {r["kind"] for r in detect_runners(tmp_path)}
    assert "dotnet" in kinds


def test_detect_node(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    kinds = {r["kind"] for r in detect_runners(tmp_path)}
    assert "node" in kinds


def test_detect_empty(tmp_path):
    assert detect_runners(tmp_path) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows .cmd wrapping")
def test_normalize_wraps_cmd(monkeypatch):
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: r"C:\tools\npm.cmd")
    out = _normalize_argv(["npm", "run", "dev"])
    assert out[:2] == ["cmd", "/c"]
    assert out[2].endswith("npm.cmd")


@pytest.mark.asyncio
async def test_stop_kills_running_process(tmp_path):
    """runner.stop must terminate a long-running process (SIGTERM->SIGKILL)."""
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    info = await runner.start(1, "sleeper", argv, str(tmp_path))
    assert info.status == "running"
    await asyncio.sleep(0.4)  # let it actually start

    ok = await runner.stop(info.id)
    assert ok is True
    assert info.status == "killed"

    # the pump should record the exit shortly after
    for _ in range(40):
        if info.exit_code is not None:
            break
        await asyncio.sleep(0.1)
    assert info.exit_code is not None


@pytest.mark.asyncio
async def test_stop_unknown_process_returns_false():
    assert await runner.stop(999999) is False
