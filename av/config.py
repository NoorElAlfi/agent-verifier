"""Run-time configuration shared by every module: the repo root, `.env`, and `AV_DATA_DIR`."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

_env_loaded = False


def load_env() -> None:
    """Load `<repo>/.env` once. Values already set in the environment win."""
    global _env_loaded
    if not _env_loaded:
        load_dotenv(REPO_ROOT / ".env", override=False)
        _env_loaded = True


def data_dir() -> Path:
    """The run-time data folder (ledgers, episode logs, quota counter, `.gpu.lock`).

    `AV_DATA_DIR` from the environment or `.env`, default `~/av-data`. Created if missing.
    Every worktree points at the same folder, so quota and the GPU lock are shared.
    """
    load_env()
    path = Path(os.environ.get("AV_DATA_DIR") or Path.home() / "av-data").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path
