"""SHARED: the per-action pipeline.

    authorize -> checks -> probes (only those the tier's catalog entry lists) -> decide
    -> re-check state (snapshot hashes) -> execute (accept* only, hash must match)
    -> outcome checks -> ledger

Every component is injected. Every stage is wrapped so that an exception becomes an error
result, which decide() turns into defer, and nothing executes (CLAUDE.md rule 5).

Policy, checks and probes see `contract.without_claims()`: agent_claims only reach the ledger.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from av.contracts import (
    ACCEPTED,
    ActionContract,
    AuthzResult,
    CheckResult,
    Decision,
    DecisionRecord,
    ExecResult,
    HumanPrompt,
    ProbeResult,
    TaskDefinition,
    TierFn,
    contract_hash,
)
from av.decide import decide
from av.interfaces import (
    Check,
    CheckContext,
    Executor,
    HumanOracle,
    Ledger,
    PolicyEngine,
    Probe,
    Snapshot,
    TaintStore,
    Workspace,
)

T = TypeVar("T")


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _guard(fn: Callable[[], T], on_error: Callable[[str], T]) -> T:
    try:
        return fn()
    except Exception as exc:  # fail closed: the caller maps this to an error result
        return on_error(_err(exc))


@dataclass
class ScriptedOracle:
    """require_human in replay, demo and tests: denies unless `approve(contract)` says yes.
    Every prompt is counted in `prompts`."""

    approve: Callable[[ActionContract], bool] | None = None
    name: str = "scripted-oracle"
    prompts: int = 0

    def ask(self, contract: ActionContract, reasons: tuple[str, ...]) -> bool:
        self.prompts += 1
        return bool(self.approve and self.approve(contract))


@dataclass
class Pipeline:
    """Wire once per episode; call run() once per proposed action.

    probe_catalog maps risk tier -> probe names to run (Agent B's single table in
    av/verify/tiering.py); `probes` maps those names to Probe objects (Agent C). A tier missing
    from the catalog, or a listed probe missing from `probes`, is an error -> defer.
    """

    policy: PolicyEngine
    checks: Sequence[Check]
    probes: Mapping[str, Probe]
    probe_catalog: Mapping[int, Sequence[str]]
    executor: Executor
    workspace: Workspace
    ledger: Ledger
    taint_store: TaintStore
    outcome_checks: Sequence[Check] = ()
    oracle: HumanOracle = field(default_factory=ScriptedOracle)
    tier_fn: TierFn | None = None
    """If set (the gateway sets it to Agent B's assign_tier), the pipeline recomputes the tier
    from the claims-free view and ignores contract.risk_tier, so a hand-built contract can't
    pick its own tier. An error here -> defer."""
    max_reverify: int = 1
    """How many times to re-verify when the workspace changed between verification and
    execution (a "stale" state). After that the action is deferred."""

    # ------------------------------------------------------------------ stages

    def _authorize(self, view: ActionContract, task: TaskDefinition) -> AuthzResult:
        def call() -> AuthzResult:
            res = self.policy.authorize(view, task)
            if not isinstance(res, AuthzResult):
                raise TypeError(f"policy returned {type(res).__name__}, not AuthzResult")
            return res

        return _guard(call, lambda e: AuthzResult(allow=False, error=e))

    def _run_checks(
        self, checks: Sequence[Check], view: ActionContract, task: TaskDefinition, ctx: CheckContext
    ) -> list[CheckResult]:
        results = []
        for check in checks:
            name = getattr(check, "name", type(check).__name__)

            def call(check: Check = check, name: str = name) -> CheckResult:
                res = check.run(view, task, ctx)
                if not isinstance(res, CheckResult):
                    raise TypeError(f"check {name} returned {type(res).__name__}")
                return res

            results.append(
                _guard(call, lambda e, name=name: CheckResult(name=name, passed=False, severity="block", error=e))
            )
        return results

    def _run_probes(self, view: ActionContract, tier: int) -> list[ProbeResult]:
        names = self.probe_catalog.get(tier)
        if names is None:
            return [ProbeResult(name="catalog", passed=False, error=f"no probe catalog entry for tier {tier}")]
        results = []
        for name in names:
            probe = self.probes.get(name)
            if probe is None:
                results.append(ProbeResult(name=name, passed=False, error="probe not available"))
                continue

            def call(probe: Probe = probe, name: str = name) -> ProbeResult:
                res = probe.run(view, self.workspace)
                if not isinstance(res, ProbeResult):
                    raise TypeError(f"probe {name} returned {type(res).__name__}")
                return res

            results.append(_guard(call, lambda e, name=name: ProbeResult(name=name, passed=False, error=e)))
        return results

    def _snapshot(self) -> Snapshot:
        return self.workspace.snapshot_hashes(None)

    # ------------------------------------------------------------------ run

    def run(self, contract: ActionContract, task: TaskDefinition) -> DecisionRecord:
        """Verify, maybe execute, and ledger one action. Returns the appended record.

        A ledger failure is NOT swallowed: it raises, because an unrecorded action must be loud.
        """
        try:
            record = self._run(contract, task)
        except Exception as exc:  # fail closed: anything unexpected is a ledgered defer
            record = DecisionRecord(
                task_id=task.task_id,
                contract=contract,
                contract_hash=_guard(lambda: contract_hash(contract), lambda e: "unhashable"),
                authorization=AuthzResult(allow=False, error=f"pipeline error: {_err(exc)}"),
                risk_tier=None,
                final_decision=Decision.DEFER,
                reasons=(f"pipeline error: {_err(exc)}",),
            )
        self.ledger.append(record)
        return record

    def _run(self, contract: ActionContract, task: TaskDefinition) -> DecisionRecord:
        approved_hash = contract_hash(contract)
        view = contract.without_claims()
        tier: int | None = contract.risk_tier
        if self.tier_fn is not None:
            tier = _guard(lambda: self.tier_fn(view, task), lambda e: None)  # None -> E2 defer
        stale_notes: list[str] = []

        for _attempt in range(max(0, self.max_reverify) + 1):
            base = {"task_id": task.task_id, "contract": contract, "contract_hash": approved_hash, "risk_tier": tier}
            try:
                snapshot_before = self._snapshot()
            except Exception as exc:
                return DecisionRecord(
                    **base,
                    authorization=AuthzResult(allow=False, error=f"snapshot failed: {_err(exc)}"),
                    final_decision=Decision.DEFER,
                    reasons=(f"state snapshot failed: {_err(exc)}",),
                )

            authz = self._authorize(view, task)
            ctx = CheckContext(workspace=self.workspace, taint_store=self.taint_store, snapshot_before=snapshot_before)
            checks = self._run_checks(self.checks, view, task, ctx)

            probes: list[ProbeResult] = []
            already_blocked = (
                authz.error is not None
                or not authz.allow
                or any(c.error is not None or (not c.passed and c.severity != "info") for c in checks)
            )
            if not already_blocked and type(tier) is int and 0 <= tier <= 4:
                probes = self._run_probes(view, tier)

            decision, reasons = decide(authz, checks, probes, tier)
            reasons = stale_notes + reasons
            base.update(authorization=authz, verification=tuple(checks), probes=tuple(probes))

            human: HumanPrompt | None = None
            go = decision in ACCEPTED
            if decision == Decision.REQUIRE_HUMAN:
                approved = _guard(lambda: bool(self.oracle.ask(view, tuple(reasons))), lambda e: False)
                human = HumanPrompt(responder=getattr(self.oracle, "name", "oracle"), approved=approved)
                go = approved
            if not go:
                return DecisionRecord(**base, final_decision=decision, reasons=tuple(reasons), human=human)

            # Re-check: the contract is still the approved one, and the workspace hasn't moved.
            if contract_hash(contract) != approved_hash:
                return DecisionRecord(
                    **base,
                    final_decision=Decision.DEFER,
                    reasons=(*reasons, "contract changed after approval; not executed"),
                    human=human,
                    execution=ExecResult(status="refused", detail="hash mismatch before execute"),
                )
            try:
                current = self._snapshot()
            except Exception as exc:
                return DecisionRecord(
                    **base,
                    final_decision=Decision.DEFER,
                    reasons=(*reasons, f"state re-check failed: {_err(exc)}"),
                    human=human,
                )
            if dict(current) != dict(snapshot_before):
                stale_notes.append("workspace changed after verification; re-verified")
                continue

            execution = _guard(
                lambda: self.executor.apply(contract, approved_hash, self.workspace, snapshot_before),
                lambda e: ExecResult(status="refused", detail=f"executor error: {e}"),
            )
            if not isinstance(execution, ExecResult):
                execution = ExecResult(status="refused", detail="executor returned a non-ExecResult")
            if execution.status == "stale":
                stale_notes.append(f"executor reported stale state: {execution.detail}")
                continue
            if execution.status != "executed":
                return DecisionRecord(
                    **base,
                    final_decision=Decision.DEFER,
                    reasons=(*reasons, f"executor refused: {execution.detail}"),
                    human=human,
                    execution=execution,
                )

            outcome: list[CheckResult] = []
            if self.outcome_checks:
                after = _guard(lambda: dict(self._snapshot()), lambda e: None)
                octx = CheckContext(
                    workspace=self.workspace,
                    taint_store=self.taint_store,
                    snapshot_before=snapshot_before,
                    snapshot_after=after,
                    execution=execution,
                )
                outcome = self._run_checks(self.outcome_checks, view, task, octx)
                failed = [f"outcome {c.name}: {c.error or c.reason}" for c in outcome if c.error or not c.passed]
                reasons = [*reasons, *failed]
            return DecisionRecord(
                **base,
                final_decision=decision,
                reasons=tuple(reasons),
                human=human,
                execution=execution,
                outcome=tuple(outcome),
            )

        return DecisionRecord(
            **base,
            final_decision=Decision.DEFER,
            reasons=(*stale_notes, f"workspace still changing after {self.max_reverify} re-verification(s)"),
        )
