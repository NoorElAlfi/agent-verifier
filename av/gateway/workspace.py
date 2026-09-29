"""The gateway's real Workspace: a directory the six tools act on.

Only Executor.apply may call `apply` on the real workspace (av/interfaces.py). Probes use
`disposable_copy()`. `apply_to_root` is shared so a probe can apply a contract to its copy.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from av.contracts import ActionContract, ExecResult, normalize_rel_path

IGNORED_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"})
MAX_READ_BYTES = 200_000


def _ignored(rel_parts: tuple[str, ...]) -> bool:
    return any(p in IGNORED_DIRS for p in rel_parts) or rel_parts[-1].endswith(".pyc")


def iter_files(root: Path) -> Iterator[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and not _ignored(p.relative_to(root).parts):
            yield p


def _resolve(root: Path, rel: str) -> Path:
    """The real path for a workspace-relative path; raises ValueError if it escapes the root or
    passes through a symlink (defence in depth: policy and scope checks come first)."""
    norm = normalize_rel_path(rel)
    if norm is None:
        raise ValueError(f"unsafe path {rel!r}")
    cur = root
    for part in [] if norm == "." else norm.split("/"):
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"{rel!r} passes through a symlink")
    resolved = cur.resolve()
    if resolved != root.resolve() and root.resolve() not in resolved.parents:
        raise ValueError(f"{rel!r} escapes the workspace")
    return cur


def apply_to_root(root: Path, contract: ActionContract) -> ExecResult:
    """Perform the contract's tool under `root`. No policy, scope or hash checks: the caller
    (Executor for the real workspace, a probe for its copy) is responsible for those."""
    tool = contract.tool
    try:
        if tool == "list_files":
            base = _resolve(root, contract.params.get("path") or ".")
            if not base.is_dir():
                return ExecResult(status="refused", detail=f"not a directory: {contract.target}")
            files = [p.relative_to(root).as_posix() for p in iter_files(base)]
            return ExecResult(status="executed", output="\n".join(files))
        if tool == "read_file":
            p = _resolve(root, contract.params["path"])
            if not p.is_file():
                return ExecResult(status="refused", detail=f"no such file: {contract.target}")
            data = p.read_bytes()
            if len(data) > MAX_READ_BYTES:
                return ExecResult(status="refused", detail=f"file larger than {MAX_READ_BYTES} bytes")
            return ExecResult(status="executed", output=data.decode("utf-8", errors="replace"))
        if tool == "write_file":
            p = _resolve(root, contract.params["path"])
            if p.is_dir():
                return ExecResult(status="refused", detail=f"{contract.target} is a directory")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contract.params["content"], encoding="utf-8")
            return ExecResult(status="executed", changed_paths=(contract.target,))
        if tool == "delete_file":
            p = _resolve(root, contract.params["path"])
            if not p.is_file():
                return ExecResult(status="refused", detail=f"no such file: {contract.target}")
            p.unlink()
            return ExecResult(status="executed", changed_paths=(contract.target,))
        if tool == "run_tests":
            # The result the agent sees comes from the run_tests probe (a disposable copy).
            return ExecResult(status="executed", detail="tests are run through the probe path")
        if tool == "submit":
            return ExecResult(status="executed", output=contract.params.get("summary", ""))
    except (ValueError, OSError) as exc:
        return ExecResult(status="refused", detail=f"{type(exc).__name__}: {exc}")
    return ExecResult(status="refused", detail=f"unknown tool {tool!r}")


@dataclass
class SandboxWorkspace:
    """Workspace over a real directory (an episode's private copy of the scenario repo)."""

    root: Path

    def snapshot_hashes(self, paths: Iterable[str] | None = None) -> dict[str, str | None]:
        def h(p: Path) -> str | None:
            return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None

        if paths is None:
            return {p.relative_to(self.root).as_posix(): h(p) for p in iter_files(self.root)}
        out: dict[str, str | None] = {}
        for rel in paths:
            try:
                out[rel] = h(_resolve(self.root, rel))
            except ValueError:
                out[rel] = None
        return out

    @contextmanager
    def disposable_copy(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="av-copy-") as d:
            dst = Path(d) / "ws"
            shutil.copytree(self.root, dst, ignore=shutil.ignore_patterns(*IGNORED_DIRS, "*.pyc"))
            yield dst

    def apply(self, contract: ActionContract) -> ExecResult:
        return apply_to_root(self.root, contract)


def prepare_workspace(source: Path, dest: Path, overlay: Path | None = None) -> Path:
    """Fresh private copy of a scenario's repo (plus its `overlay/` files) at `dest`. Nothing
    ever writes to the source, so `examples/sample_repo` stays pristine."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(*IGNORED_DIRS, "*.pyc"))
    if overlay is not None and overlay.is_dir():
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    return dest
