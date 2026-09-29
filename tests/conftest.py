"""Every test is offline (CLAUDE.md rule 6): fake model clients are injected, the real hosted
and Ollama clients raise, non-loopback network connections raise, and each test gets its own
AV_DATA_DIR. `.env` is never loaded."""

from __future__ import annotations

import ipaddress
import shutil
import socket
from pathlib import Path

import pytest

import av.clients
import av.config
from av.clients import use_clients
from av.config import REPO_ROOT
from av.contracts import TaskDefinition

from tests.fakes import FakeHostedClient, FakeOllamaClient, TmpWorkspace

_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address, *args, **kwargs):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0]
        try:
            loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise RuntimeError(f"tests are offline: blocked connection to {address!r}")
    return _real_connect(self, address, *args, **kwargs)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(av.config, "_env_loaded", True)
    for var in ("OPENCODE_GO_API_KEY", "OPENCODE_GO_BASE_URL", "AV_APPROVED_CALLS", "AV_RUN_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AV_DATA_DIR", str(tmp_path / "av-data"))
    monkeypatch.setenv("AV_PHASE", "post0")
    monkeypatch.setattr(av.clients, "BLOCK_REAL_CLIENTS", True)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield


@pytest.fixture(autouse=True)
def fake_clients():
    """The injected (hosted, ollama) fakes; inspect `.calls` to count model calls."""
    hosted, local = FakeHostedClient(), FakeOllamaClient()
    with use_clients(hosted=hosted, ollama=local):
        yield hosted, local


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A private copy of examples/sample_repo."""
    dst = tmp_path / "sample_repo"
    shutil.copytree(REPO_ROOT / "examples" / "sample_repo", dst)
    return dst


@pytest.fixture
def workspace(sample_repo: Path) -> TmpWorkspace:
    return TmpWorkspace(root=sample_repo)


@pytest.fixture
def task() -> TaskDefinition:
    return TaskDefinition(
        task_id="t-fix-add",
        objective="Fix the bug in calc/ops.py",
        scope_globs=("calc/*.py",),
    )
