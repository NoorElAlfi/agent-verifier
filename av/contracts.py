"""SHARED data models, canonical hashing, and ContractBuilder (THE trust boundary).

Everything that crosses a component boundary is a Pydantic v2 model defined here, so every
wave agrees on one shape. Owned by Wave 1; later waves request changes via their progress file.

Trust boundary in one sentence: the gateway builds each ActionContract with ContractBuilder,
which takes scope only from the harness-supplied TaskDefinition and provenance only from the
gateway's TaintStore. Whatever the agent says about itself lands in `agent_claims`, which is
recorded in the ledger and never reaches `decide()` (it doesn't even reach the checks: the
pipeline hands them `contract.without_claims()`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ulid import ULID

if TYPE_CHECKING:
    from av.interfaces import TaintStore

# --------------------------------------------------------------------------- tools

ToolName = Literal["list_files", "read_file", "write_file", "delete_file", "run_tests", "submit"]

#: The agent's complete tool list (CLAUDE.md rule 4). Never add a shell tool.
TOOLS: tuple[str, ...] = (
    "list_files",
    "read_file",
    "write_file",
    "delete_file",
    "run_tests",
    "submit",
)
#: Tools that change the real workspace. Every one of them goes through the scope check.
MUTATING_TOOLS: frozenset[str] = frozenset({"write_file", "delete_file"})
#: Tools whose results the gateway records into the TaintStore as untrusted_content.
READ_TOOLS: frozenset[str] = frozenset({"list_files", "read_file", "run_tests"})

#: Allowed params per tool: name -> required?  All values are strings.
TOOL_PARAMS: dict[str, dict[str, bool]] = {
    "list_files": {"path": False},
    "read_file": {"path": True},
    "write_file": {"path": True, "content": True},
    "delete_file": {"path": True},
    "run_tests": {},
    "submit": {"summary": False},
}

ProtectedClass = Literal["ci", "tests", "dependencies", "secrets"]
"""Protected path classes (spec defaults). Changes to them count as scope drift unless the task
lists the class in `TaskDefinition.declared_protected`:
ci = CI config; tests = test deletion or weakening; dependencies = dependency manifests and
lockfiles; secrets = secret-like paths. Agent B's ScopeDriftCheck owns the path patterns."""


# --------------------------------------------------------------------------- hashing


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj


def canonical_json(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, no NaN. Models are dumped in JSON
    mode first. Same logical value -> same bytes, so it is safe to hash."""
    return json.dumps(
        _jsonable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contract_hash(contract: ActionContract | dict[str, Any]) -> str:
    """sha256 over canonical JSON of exactly {tool, target, params} (spec M6).

    Only what executes is bound; ids, evidence, tier and agent_claims are not part of the hash.
    The executor recomputes this from the params it is about to apply and refuses on mismatch.
    """
    if isinstance(contract, ActionContract):
        tool, target, params = contract.tool, contract.target, contract.params
    else:
        tool, target, params = contract["tool"], contract["target"], contract["params"]
    return sha256_hex(canonical_json({"tool": tool, "target": target, "params": params}))


def new_id() -> str:
    """A new ULID string (spec default: IDs are ULIDs)."""
    return str(ULID())


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- task + evidence


class TaskDefinition(BaseModel):
    """What the harness (never the agent) says the task is. Loaded from scenarios/<id>/task.yaml.

    `scope_globs` are POSIX globs relative to the workspace root (e.g. "calc/*.py").
    `declared_protected` lists protected classes this task explicitly allows touching.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    objective: str
    scope_globs: tuple[str, ...]
    allowed_tools: tuple[ToolName, ...] = TOOLS  # type: ignore[assignment]
    declared_protected: tuple[ProtectedClass, ...] = ()
    split: Literal["dev", "test"] = "dev"
    workspace: str = "examples/sample_repo"
    """Workspace root, relative to the repo root. Not in PLAN.md's list; added so the gateway
    and replay know which repo a scenario acts on."""


Provenance = Literal["user", "observed", "untrusted_content"]


class Evidence(BaseModel):
    """One piece of support for an action, with provenance DERIVED BY THE GATEWAY.

    user = the harness's task definition; observed = produced by the gateway itself (e.g. a
    probe); untrusted_content = anything returned by a read (repo file, issue, tool output).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: str
    provenance: Provenance
    source_ref: str
    ts: datetime = Field(default_factory=_now)


class TaintHit(BaseModel):
    """A place where a proposal's params overlap untrusted content the agent previously read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    kind: Literal["substring", "url", "command"]
    matched: str


# --------------------------------------------------------------------------- the contract


class ActionContract(BaseModel):
    """One proposed tool call, as the gateway understands it. Gating is per action.

    Built only by ContractBuilder. `derived_scope_ok`, `evidence` and `risk_tier` are
    gateway-derived. `agent_claims` holds whatever the agent asserted about scope, provenance
    or intent; it is recorded for the ledger and NEVER read by decide() or any check.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(default_factory=new_id)
    task_id: str
    tool: ToolName
    target: str
    params: dict[str, Any]
    derived_scope_ok: bool
    evidence: tuple[Evidence, ...] = ()
    risk_tier: int | None = Field(default=None, ge=0, le=4)
    rollback_note: str = ""
    agent_claims: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params")
    @classmethod
    def _params_are_json(cls, v: dict[str, Any]) -> dict[str, Any]:
        canonical_json(v)  # raises on NaN, sets, bytes, ...
        return v

    @property
    def is_mutating(self) -> bool:
        return self.tool in MUTATING_TOOLS

    def without_claims(self) -> ActionContract:
        """The view handed to policy, checks and probes: agent_claims stripped, and a deep copy,
        so a component that mutates its params can't change what executes."""
        return self.model_copy(update={"agent_claims": {}}, deep=True)

    def hash(self) -> str:
        return contract_hash(self)


# --------------------------------------------------------------------------- results


class Decision(StrEnum):
    """final_decision states for Post 0 (spec defaults)."""

    ACCEPT = "accept"
    ACCEPT_WITH_LOGGING = "accept_with_logging"
    REQUIRE_HUMAN = "require_human"
    DEFER = "defer"
    REJECT = "reject"


#: "Blocked" means the decision is in this set and the action is not executed.
BLOCKED: frozenset[Decision] = frozenset({Decision.REJECT, Decision.REQUIRE_HUMAN, Decision.DEFER})
ACCEPTED: frozenset[Decision] = frozenset({Decision.ACCEPT, Decision.ACCEPT_WITH_LOGGING})


class AuthzResult(BaseModel):
    """Authorization ("may it?"), from the PolicyEngine (OPA). `error` set => decide() defers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow: bool
    reasons: tuple[str, ...] = ()
    error: str | None = None


Severity = Literal["block", "escalate", "info"]


class CheckResult(BaseModel):
    """Result of one verification ("should it?") or outcome check.

    When passed is False, severity decides: block -> reject (protected-class drift, tainted
    params); escalate -> require_human (other scope drift); info -> recorded only.
    `error` set => the check could not run => decide() defers (fail closed).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    severity: Severity = "info"
    reason: str = ""
    error: str | None = None


class ProbeResult(BaseModel):
    """Result of one probe run in a disposable copy. passed False => reject; error => defer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExecResult(BaseModel):
    """What the executor did. Only `executed` touched the real workspace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["executed", "refused", "stale"]
    detail: str = ""
    changed_paths: tuple[str, ...] = ()
    output: Any = None


class HumanPrompt(BaseModel):
    """One require_human prompt and its answer (in replay: a scripted oracle, deny by default)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    responder: str
    approved: bool


class DecisionRecord(BaseModel):
    """Everything about one action, as appended to the ledger (spec M7: authorization,
    verification and final_decision are separate fields)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str = Field(default_factory=new_id)
    ts: datetime = Field(default_factory=_now)
    task_id: str
    contract: ActionContract
    contract_hash: str
    authorization: AuthzResult
    verification: tuple[CheckResult, ...] = ()
    probes: tuple[ProbeResult, ...] = ()
    risk_tier: int | None = None
    final_decision: Decision
    reasons: tuple[str, ...] = ()
    human: HumanPrompt | None = None
    execution: ExecResult | None = None
    outcome: tuple[CheckResult, ...] = ()

    @property
    def executed(self) -> bool:
        return self.execution is not None and self.execution.status == "executed"


# --------------------------------------------------------------------------- the builder


class ContractError(ValueError):
    """The proposal can't be turned into a contract (unknown tool, bad params). The gateway
    returns this to the agent as a refusal; nothing executes."""


def normalize_rel_path(path: str) -> str | None:
    """Normalise a workspace-relative POSIX path, or None if it is unsafe or not relative.

    Rejects absolute paths, backslashes, NUL, and ANY `..` component (even one that would stay
    inside the root). Strips `.` components and duplicate slashes. Case is preserved.
    """
    if not path or "\x00" in path or "\\" in path:
        return None
    pp = PurePosixPath(path)
    if pp.is_absolute():
        return None
    parts = [p for p in pp.parts if p not in ("", ".")]
    if ".." in parts:
        return None
    return "/".join(parts) or "."


def basic_scope_ok(tool: str, target: str, task: TaskDefinition) -> bool:
    """Default scope function: True for non-mutating tools; for mutating tools, the normalised
    target must match one of task.scope_globs (fnmatch; `*` also crosses `/`).

    This fills the informational `derived_scope_ok` field. The authoritative, decision-making
    check is Agent B's ScopeDriftCheck (symlinks, case, protected classes); the merge may inject
    B's function here via ContractBuilder(scope_fn=...).
    """
    if tool not in MUTATING_TOOLS:
        return True
    norm = normalize_rel_path(target)
    if norm is None:
        return False
    return any(fnmatchcase(norm, g) for g in task.scope_globs)


ScopeFn = Callable[[str, str, TaskDefinition], bool]
TierFn = Callable[[ActionContract, TaskDefinition], int]

_ROLLBACK = {
    "write_file": "restore the target from the pre-execution snapshot (or remove it if new)",
    "delete_file": "restore the target from the pre-execution snapshot",
}


class ContractBuilder:
    """THE trust boundary. Turns a raw tool call into an ActionContract.

    - scope: only from `task` (via scope_fn);
    - provenance: only from `taint_store.match(params)`, plus the task objective as `user`;
    - risk tier: only from tier_fn (Agent B's assign_tier), which sees the contract WITHOUT
      agent_claims;
    - agent_claims: stored verbatim, never used.
    """

    def __init__(self, scope_fn: ScopeFn = basic_scope_ok, tier_fn: TierFn | None = None):
        self.scope_fn = scope_fn
        self.tier_fn = tier_fn

    @staticmethod
    def target_for(tool: str, params: dict[str, Any]) -> str:
        """The single path an action acts on: params["path"], "." for list_files without a
        path and for run_tests (whole workspace), "" for submit."""
        if tool == "submit":
            return ""
        if tool == "run_tests":
            return "."
        return params.get("path") or "."

    @staticmethod
    def validate_params(tool: str, params: dict[str, Any]) -> None:
        if tool not in TOOL_PARAMS:
            raise ContractError(f"unknown tool {tool!r}; the only tools are {', '.join(TOOLS)}")
        spec = TOOL_PARAMS[tool]
        extra = set(params) - set(spec)
        if extra:
            raise ContractError(f"{tool}: unexpected params {sorted(extra)}")
        for name, required in spec.items():
            if required and name not in params:
                raise ContractError(f"{tool}: missing param {name!r}")
            if name in params and not isinstance(params[name], str):
                raise ContractError(f"{tool}: param {name!r} must be a string")

    def build(
        self,
        tool: str,
        params: dict[str, Any],
        task: TaskDefinition,
        taint_store: TaintStore,
        agent_claims: Any = None,
    ) -> ActionContract:
        """Raises ContractError for unknown tools, tools the task doesn't allow, or bad params,
        and also (chained) when the taint store, scope_fn or tier_fn fails. Callers catch
        ContractError, refuse the call, and execute nothing."""
        try:
            return self._build(tool, params, task, taint_store, agent_claims)
        except ContractError:
            raise
        except Exception as exc:
            raise ContractError(f"could not build contract: {type(exc).__name__}: {exc}") from exc

    def _build(
        self,
        tool: str,
        params: dict[str, Any],
        task: TaskDefinition,
        taint_store: TaintStore,
        agent_claims: Any,
    ) -> ActionContract:
        self.validate_params(tool, params)
        if tool not in task.allowed_tools:
            raise ContractError(f"tool {tool!r} is not allowed for task {task.task_id}")
        params = dict(params)
        target = self.target_for(tool, params)

        evidence = [Evidence(claim=task.objective, provenance="user", source_ref=f"task:{task.task_id}")]
        for hit in taint_store.match(params):
            evidence.append(
                Evidence(
                    claim=f"params contain {hit.kind} seen in untrusted content: {hit.matched[:120]}",
                    provenance="untrusted_content",
                    source_ref=hit.source_ref,
                )
            )

        if agent_claims is None:
            claims: dict[str, Any] = {}
        elif isinstance(agent_claims, dict):
            claims = dict(agent_claims)
        else:
            claims = {"raw": agent_claims}
        # Round-trip through JSON so the ledger can always hash the record.
        claims = json.loads(json.dumps(claims, default=str))

        contract = ActionContract(
            task_id=task.task_id,
            tool=tool,  # type: ignore[arg-type]
            target=target,
            params=params,
            derived_scope_ok=self.scope_fn(tool, target, task),
            evidence=tuple(evidence),
            rollback_note=_ROLLBACK.get(tool, "no workspace change"),
            agent_claims=claims,
        )
        if self.tier_fn is not None:
            tier = self.tier_fn(contract.without_claims(), task)
            # model_validate (not model_copy) so the 0..4 bound is enforced.
            contract = ActionContract.model_validate({**contract.model_dump(), "risk_tier": tier})
        return contract
