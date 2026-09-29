"""One Ollama job at a time on the 8 GB GPU (CLAUDE.md rule 8)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from filelock import FileLock

from av.config import data_dir


@contextmanager
def gpu_lock(timeout: float = -1) -> Iterator[None]:
    """Hold `AV_DATA_DIR/.gpu.lock` for the duration of a batch of Ollama calls.

    Shared across worktrees. timeout=-1 waits forever; otherwise filelock.Timeout is raised.
    """
    with FileLock(str(data_dir() / ".gpu.lock"), timeout=timeout):
        yield
