"""STAND-INS for components Wave 2 Agents A, B and C build in parallel. NOT the real ones.

Every class here is clearly simplified and exists only so the gateway, replay and `make demo`
run end to end before the merge. The merge swaps each one for the real component by editing
ONE table, `av/gateway/wiring.py::COMPONENTS` (see progress/w2-D.md). Nothing outside
`wiring.py` imports this module.

    PolicyEngine  -> StandInPolicy       (real: A, OPA)
    Ledger        -> ChainLedger         (real: A, SQLite hash chain)
    Executor      -> StandInExecutor     (real: A, hash-bound executor)
    Check         -> StandInScopeCheck, StandInProvenanceCheck   (real: B)
    tier + catalog-> stand_in_tier, STAND_IN_CATALOG             (real: B tiering.py)
    TaintStore    -> StandInTaintStore   (real: B taint.py)
    Probe         -> StandInRunTestsProbe (real: C RunTestsProbe, Docker --network none)

Known simplifications: the probe runs pytest in a disposable copy but WITHOUT Docker; the
taint store ignores reads of source-code files (so a benign edit of a file the agent read isn't
flagged as tainted) and matches only whole lines >= 20 chars, URLs and backticked commands.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from av.contracts import (
    ActionContract,
    AuthzResult,
    CheckResult,
    ExecResult,
    ProbeResult,
    TaintHit,
    TaskDefinition,
    canonical_json,
    contract_hash,
    normalize_rel_path,
    sha256_hex,
)
from av.gateway.workspace import apply_to_root
from av.interfaces import CheckContext, Snapshot, Workspace

# --------------------------------------------------------------------------- policy


@dataclass
class StandInPolicy:
    """Static permissions only: tool allowed for the task, safe relative path, not a secret-like
    path, content size limit."""

    max_content_bytes: int = 200_000

    def authorize(self, contract: ActionContract, task: TaskDefinition) -> AuthzResult:
        if contract.tool not in task.allowed_tools:
            return AuthzResult(allow=False, reasons=(f"tool {contract.tool} not allowed for this task",))
        if contract.tool not in ("run_tests", "submit") and normalize_rel_path(contract.target) is None:
            return AuthzResult(allow=False, reasons=(f"unsafe path {contract.target!r}",))
        if contract.is_mutating and _protected_class(contract.target) == "secrets":
            return AuthzResult(allow=False, reasons=(f"{contract.target} looks like a secret file",))
        if len(contract.params.get("content", "").encode()) > self.max_content_bytes:
            return AuthzResult(allow=False, reasons=("content too large",))
        return AuthzResult(allow=True, reasons=("stand-in policy: allowed",))


# --------------------------------------------------------------------------- checks

_PROTECTED: dict[str, tuple[str, ...]] = {
    "ci": (".github/*", ".gitlab-ci.yml", ".circleci/*", "Jenkinsfile", "azure-pipelines.yml"),
    "tests": ("tests/*", "test/*", "test_*.py", "*/test_*.py", "*_test.py", "conftest.py", "*/conftest.py"),
    "dependencies": (
        "pyproject.toml", "requirements*.txt", "uv.lock", "poetry.lock", "Pipfile*", "setup.py",
        "package.json", "package-lock.json", "yarn.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    ),
    "secrets": (".env", ".env.*", "*.pem", "*.key", "*secret*", "id_rsa*", "*credentials*"),
}


def _protected_class(target: str) -> str | None:
    norm = normalize_rel_path(target)
    if norm is None:
        return None
    for cls, globs in _PROTECTED.items():
        if any(fnmatchcase(norm, g) or fnmatchcase(norm.rsplit("/", 1)[-1], g) for g in globs):
            return cls
    return None


class StandInScopeCheck:
    name = "scope_drift"

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        if not contract.is_mutating:
            return CheckResult(name=self.name, passed=True)
        cls = _protected_class(contract.target)
        if cls and cls not in task.declared_protected:
            return CheckResult(
                name=self.name, passed=False, severity="block",
                reason=f"{contract.tool} of {contract.target} is drift into protected class '{cls}'",
            )
        if not contract.derived_scope_ok:
            return CheckResult(
                name=self.name, passed=False, severity="escalate",
                reason=f"{contract.target} is outside the task scope {list(task.scope_globs)}",
            )
        return CheckResult(name=self.name, passed=True)


class StandInProvenanceCheck:
    name = "provenance"

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        if not contract.is_mutating:
            return CheckResult(name=self.name, passed=True)
        bad = [e for e in contract.evidence if e.provenance == "untrusted_content"]
        if bad:
            return CheckResult(
                name=self.name, passed=False, severity="block",
                reason=f"params derive from untrusted content read earlier ({bad[0].source_ref})",
            )
        return CheckResult(name=self.name, passed=True)


# --------------------------------------------------------------------------- tiering


def stand_in_tier(contract: ActionContract, task: TaskDefinition) -> int:
    """0 read/list/submit; 1 run_tests; 2 in-scope write; 3 delete or protected-class change."""
    if contract.tool in ("list_files", "read_file", "submit"):
        return 0
    if contract.tool == "run_tests":
        return 1
    if contract.tool == "delete_file" or _protected_class(contract.target):
        return 3
    return 2


STAND_IN_CATALOG: dict[int, tuple[str, ...]] = {
    0: (),
    1: ("run_tests",),
    2: ("run_tests",),
    3: ("run_tests",),
    4: ("run_tests",),
}


# --------------------------------------------------------------------------- taint

_URL = re.compile(r"https?://[^\s`'\"<>)]+", re.I)
_BACKTICK = re.compile(r"`([^`\n]{6,})`")
_CODE_SUFFIXES = (".py", ".pyi")


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


@dataclass
class StandInTaintStore:
    reads: dict[str, str] = field(default_factory=dict)

    def record_read(self, source_ref: str, text: str) -> None:
        if source_ref.endswith(_CODE_SUFFIXES):
            return  # stand-in simplification, see module docstring
        self.reads[source_ref] = self.reads.get(source_ref, "") + "\n" + text

    def match(self, params: Mapping[str, Any]) -> list[TaintHit]:
        values = [v for v in params.values() if isinstance(v, str)]
        joined = _norm("\n".join(values))
        hits: list[TaintHit] = []
        for ref, text in self.reads.items():
            for line in text.splitlines():
                if len(_norm(line)) >= 20 and _norm(line) in joined:
                    hits.append(TaintHit(source_ref=ref, kind="substring", matched=line.strip()))
            for m in _URL.findall(text):
                if _norm(m) in joined:
                    hits.append(TaintHit(source_ref=ref, kind="url", matched=m))
            for m in _BACKTICK.findall(text):
                if _norm(m) in joined:
                    hits.append(TaintHit(source_ref=ref, kind="command", matched=m))
        return hits


# --------------------------------------------------------------------------- probe


@dataclass
class StandInRunTestsProbe:
    """Apply the contract to a disposable copy and run pytest there (no Docker: stand-in).
    For the run_tests tool the probe passes whenever the run completes and its summary carries
    the output the agent sees; for write/delete it passes only if the tests pass afterwards."""

    name: str = "run_tests"
    timeout_s: int = 60

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        with workspace.disposable_copy() as copy:
            if contract.is_mutating:
                applied = apply_to_root(copy, contract)
                if applied.status != "executed":
                    return ProbeResult(name=self.name, passed=False, error=f"could not apply to copy: {applied.detail}")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(copy)}
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
                    cwd=copy, env=env, capture_output=True, text=True, timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired:
                return ProbeResult(name=self.name, passed=False, error=f"tests timed out after {self.timeout_s}s")
            out = (proc.stdout + proc.stderr).strip()
            tail = out[-2000:]
            ok = proc.returncode in (0, 5)
            if not contract.is_mutating:
                ok = True
            return ProbeResult(
                name=self.name, passed=ok, summary=tail, details={"exit_code": proc.returncode}
            )


# --------------------------------------------------------------------------- ledger


class ChainLedger:
    """Append-only JSONL hash chain: hash = sha256(prev_hash + canonical record JSON)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text().splitlines() if ln.strip()]

    def append(self, record: Any) -> str:
        rows = self._rows()
        prev = rows[-1]["hash"] if rows else ""
        body = canonical_json(record).decode()
        h = sha256_hex(prev.encode() + body.encode())
        with self.path.open("a") as f:
            f.write(json.dumps({"prev": prev, "record": body, "hash": h}) + "\n")
        return h

    def verify(self) -> bool:
        prev = ""
        for row in self._rows():
            if row["prev"] != prev or sha256_hex(prev.encode() + row["record"].encode()) != row["hash"]:
                return False
            prev = row["hash"]
        return True

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(r["record"]) for r in self._rows()]


# --------------------------------------------------------------------------- executor


class StandInExecutor:
    """Same contract as A's executor: hash check, target re-check, then workspace.apply()."""

    def apply(self, contract: ActionContract, approved_hash: str, workspace: Workspace, snapshot: Snapshot) -> ExecResult:
        if contract_hash(contract) != approved_hash:
            return ExecResult(status="refused", detail="params hash differs from approved hash")
        if contract.is_mutating:
            now = workspace.snapshot_hashes([contract.target])
            if now.get(contract.target) != snapshot.get(contract.target):
                return ExecResult(status="stale", detail=f"{contract.target} changed")
        return workspace.apply(contract)
