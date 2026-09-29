"""Offline stand-ins for every component, used by all tests (and by Wave 2 agents for anything
not merged yet). They implement the protocols in av/interfaces.py faithfully but simply."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from av.clients import ChatResult, Message
from av.contracts import (
    ActionContract,
    AuthzResult,
    CheckResult,
    DecisionRecord,
    ExecResult,
    ProbeResult,
    TaintHit,
    TaskDefinition,
    canonical_json,
    contract_hash,
    sha256_hex,
)
from av.interfaces import CheckContext, Snapshot, Workspace


@dataclass
class FakePolicy:
    allow: bool = True
    reasons: tuple[str, ...] = ()
    error: str | None = None
    raises: Exception | None = None
    seen: list[ActionContract] = field(default_factory=list)

    def authorize(self, contract: ActionContract, task: TaskDefinition) -> AuthzResult:
        self.seen.append(contract)
        if self.raises:
            raise self.raises
        return AuthzResult(allow=self.allow, reasons=self.reasons, error=self.error)


@dataclass
class FakeCheck:
    """Returns `result` (default: passed), or `fn(contract, task, ctx)` if given, or raises."""

    name: str = "fake_check"
    result: CheckResult | None = None
    fn: Callable[[ActionContract, TaskDefinition, CheckContext], CheckResult] | None = None
    raises: Exception | None = None
    seen: list[ActionContract] = field(default_factory=list)
    contexts: list[CheckContext] = field(default_factory=list)

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        self.seen.append(contract)
        self.contexts.append(ctx)
        if self.raises:
            raise self.raises
        if self.fn:
            return self.fn(contract, task, ctx)
        return self.result or CheckResult(name=self.name, passed=True)


@dataclass
class FakeProbe:
    name: str = "fake_probe"
    passed: bool = True
    error: str | None = None
    raises: Exception | None = None
    seen: list[ActionContract] = field(default_factory=list)

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        self.seen.append(contract)
        if self.raises:
            raise self.raises
        return ProbeResult(name=self.name, passed=self.passed, summary="fake", error=self.error)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


@dataclass
class FakeTaintStore:
    """Hit when a whitespace/case-normalised line (>= 20 chars) of any recorded read appears in a
    string param. Deliberately simpler than Agent B's real TaintStore."""

    reads: dict[str, str] = field(default_factory=dict)

    def record_read(self, source_ref: str, text: str) -> None:
        self.reads[source_ref] = self.reads.get(source_ref, "") + "\n" + text

    def match(self, params: Mapping[str, Any]) -> list[TaintHit]:
        hits = []
        values = [_norm(v) for v in params.values() if isinstance(v, str)]
        for ref, text in self.reads.items():
            for line in text.splitlines():
                ln = _norm(line)
                if len(ln) >= 20 and any(ln in v for v in values):
                    hits.append(TaintHit(source_ref=ref, kind="substring", matched=line.strip()))
        return hits


@dataclass
class InMemoryLedger:
    """Hash-chained like the real one: row_hash = sha256(prev_hash + canonical row JSON)."""

    rows: list[tuple[str, bytes, str]] = field(default_factory=list)  # (prev, row json, hash)

    @property
    def records(self) -> list[DecisionRecord]:
        return [DecisionRecord.model_validate_json(r) for _, r, _ in self.rows]

    def append(self, record: DecisionRecord) -> str:
        prev = self.rows[-1][2] if self.rows else ""
        row = canonical_json(record)
        h = sha256_hex(prev.encode() + row)
        self.rows.append((prev, row, h))
        return h

    def verify(self) -> bool:
        prev = ""
        for p, row, h in self.rows:
            if p != prev or sha256_hex(p.encode() + row) != h:
                return False
            prev = h
        return True


def _file_hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


@dataclass
class TmpWorkspace:
    """A Workspace over a real directory (tests pass tmp_path copies)."""

    root: Path

    def snapshot_hashes(self, paths: Iterable[str] | None = None) -> dict[str, str | None]:
        if paths is None:
            files = [p for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts]
            return {p.relative_to(self.root).as_posix(): _file_hash(p) for p in sorted(files)}
        return {rel: _file_hash(self.root / rel) for rel in paths}

    @contextmanager
    def disposable_copy(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="av-copy-") as d:
            dst = Path(d) / "ws"
            shutil.copytree(self.root, dst)
            yield dst

    def apply(self, contract: ActionContract) -> ExecResult:
        target = self.root / contract.target
        if contract.tool == "write_file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contract.params["content"])
            return ExecResult(status="executed", changed_paths=(contract.target,))
        if contract.tool == "delete_file":
            target.unlink()
            return ExecResult(status="executed", changed_paths=(contract.target,))
        if contract.tool == "read_file":
            return ExecResult(status="executed", output=target.read_text())
        return ExecResult(status="executed")


@dataclass
class FakeExecutor:
    """Same contract as Agent A's executor: re-hash, re-check target snapshot, then apply."""

    calls: int = 0

    def apply(self, contract: ActionContract, approved_hash: str, workspace: Workspace, snapshot: Snapshot) -> ExecResult:
        self.calls += 1
        if contract_hash(contract) != approved_hash:
            return ExecResult(status="refused", detail="params hash differs from approved hash")
        if contract.is_mutating:
            now = workspace.snapshot_hashes([contract.target])
            if now[contract.target] != snapshot.get(contract.target):
                return ExecResult(status="stale", detail=f"{contract.target} changed")
        return workspace.apply(contract)


@dataclass
class FakeHostedClient:
    """Records every call; replies with the next scripted text (or "ok")."""

    replies: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def chat(self, messages: list[Message], model: str | None = None, **kwargs: Any) -> ChatResult:
        self.calls.append({"messages": messages, "model": model, **kwargs})
        text = self.replies.pop(0) if self.replies else "ok"
        return ChatResult(text=text, model=model or "fake-model")


FakeOllamaClient = FakeHostedClient


def fake_tier(tiers: Mapping[str, int] | None = None, default: int = 1) -> Callable[[ActionContract, TaskDefinition], int]:
    """A tier function: reads -> 0, otherwise tiers.get(tool, default)."""
    tiers = dict(tiers or {})

    def fn(contract: ActionContract, task: TaskDefinition) -> int:
        if contract.tool in ("list_files", "read_file"):
            return tiers.get(contract.tool, 0)
        return tiers.get(contract.tool, default)

    return fn
