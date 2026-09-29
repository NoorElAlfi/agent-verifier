"""SHARED component protocols. Wave 2 agents implement these; the pipeline only knows these.

Every method on the authorize/verify/probe path may raise: the pipeline catches it and the
action is deferred (fail closed). Implementations should still prefer returning a result with
`error` set, because that keeps the reason precise in the ledger.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from av.contracts import (
    ActionContract,
    AuthzResult,
    CheckResult,
    DecisionRecord,
    ExecResult,
    ProbeResult,
    TaintHit,
    TaskDefinition,
)

#: path (relative, POSIX) -> sha256 of the file's bytes, or None if the file doesn't exist.
Snapshot = Mapping[str, str | None]


@dataclass(frozen=True)
class CheckContext:
    """What a Check may look at besides the contract and task. All gateway-owned state.

    For verification checks `snapshot_after` and `execution` are None; outcome checks (run after
    execution) get both.
    """

    workspace: Workspace
    taint_store: TaintStore
    snapshot_before: Snapshot = field(default_factory=dict)
    snapshot_after: Snapshot | None = None
    execution: ExecResult | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class PolicyEngine(Protocol):
    """Authorization: "MAY the agent do this?" Implemented by Agent A (av/policy/opa.py: OPA via
    `./bin/opa eval` in a subprocess with a timeout, rules in policies/*.rego). It answers static
    permission questions only (tool allowlist per task, path denylist, size limits); whether the
    action is a good idea, e.g. scope drift, is verification's job, not this one's. Errors and
    timeouts return AuthzResult(allow=False, error=...), which decide() turns into defer."""

    def authorize(self, contract: ActionContract, task: TaskDefinition) -> AuthzResult: ...


@runtime_checkable
class Check(Protocol):
    """Verification: "SHOULD it?" One deterministic check. Implemented by Agent B (av/verify/:
    ScopeDriftCheck, ProvenanceCheck; OutcomeCheck is also a Check, run after execution with
    snapshot_after set). A check gets the contract WITHOUT agent_claims and must derive
    everything from the task, the contract's tool/target/params, and ctx. On failure it sets
    severity: block (reject: protected-class drift, tainted params), escalate (require_human:
    other scope drift) or info (logged only)."""

    name: str

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult: ...


@runtime_checkable
class Probe(Protocol):
    """An active test of the proposed action in a disposable copy of the workspace. Implemented by
    Agent C (av/probes/: RunTestsProbe, DiffProbe, SecretScanProbe). A probe applies the contract
    to `workspace.disposable_copy()`, runs inside `docker run --rm --network none` with an empty
    environment, parses the result and discards the copy. It never writes to workspace.root.
    Which probes run for which tier is Agent B's single catalog table (av/verify/tiering.py)."""

    name: str

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult: ...


@runtime_checkable
class TaintStore(Protocol):
    """Gateway-side provenance tracking. Implemented by Agent B (av/verify/taint.py). The gateway
    (Agent D) calls record_read() with EVERY read result (file contents, issue text, tool output)
    as untrusted_content. ContractBuilder calls match(params) on every proposal; a hit becomes
    untrusted_content evidence. Matching covers verbatim substrings >= 20 chars, URLs and
    shell-command tokens, normalised for whitespace and case."""

    def record_read(self, source_ref: str, text: str) -> None: ...

    def match(self, params: Mapping[str, Any]) -> list[TaintHit]: ...


@runtime_checkable
class Ledger(Protocol):
    """Append-only, hash-chained decision log. Implemented by Agent A (av/ledger.py:
    SqliteLedger; row_hash = sha256(prev_hash + canonical row JSON); no UPDATE or DELETE
    anywhere). append() returns the new row hash; verify() re-walks the chain."""

    def append(self, record: DecisionRecord) -> str: ...

    def verify(self) -> bool: ...


@runtime_checkable
class Workspace(Protocol):
    """The real repo the agent works on. Implemented by Agent D for the gateway (tests use
    tests/fakes.py::TmpWorkspace). Only Executor.apply may call `apply` on the real workspace;
    probes use `disposable_copy()`, a context manager yielding a throwaway copy's root that is
    deleted on exit."""

    root: Path

    def snapshot_hashes(self, paths: Iterable[str] | None = None) -> dict[str, str | None]:
        """sha256 per file; all regular files under root (excluding .git) when paths is None."""
        ...

    def disposable_copy(self) -> AbstractContextManager[Path]: ...

    def apply(self, contract: ActionContract) -> ExecResult:
        """Perform the contract's tool on the real workspace. No checks: Executor does those."""
        ...


@runtime_checkable
class Executor(Protocol):
    """Hash-bound execution. Implemented by Agent A (av/executor.py). apply() must, in order:
    (1) recompute contract_hash from the contract it is about to apply and return
    status="refused" if it differs from approved_hash; (2) re-hash the target paths and return
    status="stale" if they differ from `snapshot`; (3) only then call workspace.apply()."""

    def apply(
        self,
        contract: ActionContract,
        approved_hash: str,
        workspace: Workspace,
        snapshot: Snapshot,
    ) -> ExecResult: ...


@runtime_checkable
class HumanOracle(Protocol):
    """Answers require_human. In replay and tests this is a scripted oracle that denies by
    default (av/pipeline.py::ScriptedOracle); every prompt is counted."""

    name: str

    def ask(self, contract: ActionContract, reasons: tuple[str, ...]) -> bool: ...


__all__ = [
    "Check",
    "CheckContext",
    "Executor",
    "HumanOracle",
    "Ledger",
    "PolicyEngine",
    "Probe",
    "Snapshot",
    "TaintStore",
    "Workspace",
]
