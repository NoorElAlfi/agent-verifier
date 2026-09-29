"""Run order, execute-only-on-accept, hash binding, state re-check, and fail-closed stages."""

import pytest

from av.contracts import BLOCKED, CheckResult, ContractBuilder, Decision, ExecResult
from av.pipeline import Pipeline, ScriptedOracle
from tests.fakes import (
    FakeCheck,
    FakeExecutor,
    FakePolicy,
    FakeProbe,
    FakeTaintStore,
    InMemoryLedger,
    fake_tier,
)

FIX = "def add(a: int, b: int) -> int:\n    return a + b  # fixed\n"
CATALOG = {0: (), 1: (), 2: ("run_tests",), 3: ("run_tests",), 4: ()}


def make(workspace, **kw):
    parts = dict(
        policy=FakePolicy(),
        checks=[FakeCheck(name="scope")],
        probes={"run_tests": FakeProbe(name="run_tests")},
        probe_catalog=CATALOG,
        executor=FakeExecutor(),
        workspace=workspace,
        ledger=InMemoryLedger(),
        taint_store=FakeTaintStore(),
    )
    parts.update(kw)
    return Pipeline(**parts)


def contract(task, tier=1, tool="write_file", params=None, claims=None):
    params = params if params is not None else {"path": "calc/ops.py", "content": FIX}
    return ContractBuilder(tier_fn=fake_tier({tool: tier})).build(
        tool, params, task, FakeTaintStore(), agent_claims=claims
    )


def ops(workspace):
    return (workspace.root / "calc/ops.py").read_text()


def test_benign_edit_is_accepted_executed_and_ledgered(task, workspace):
    p = make(workspace)
    rec = p.run(contract(task), task)
    assert rec.final_decision == Decision.ACCEPT and rec.executed
    assert ops(workspace) == FIX
    assert p.ledger.records == [rec] and p.ledger.verify()


def test_tier0_read_is_accept_with_logging(task, workspace):
    rec = make(workspace).run(contract(task, tier=0, tool="read_file", params={"path": "calc/ops.py"}), task)
    assert rec.final_decision == Decision.ACCEPT_WITH_LOGGING and rec.executed
    assert "return a + b" in rec.execution.output


@pytest.mark.parametrize(
    "kw,expected",
    [
        (dict(policy=FakePolicy(allow=False, reasons=("denylisted",))), Decision.REJECT),
        (dict(checks=[FakeCheck(result=CheckResult(name="prov", passed=False, severity="block", reason="tainted"))]), Decision.REJECT),
        (dict(checks=[FakeCheck(result=CheckResult(name="scope", passed=False, severity="escalate", reason="drift"))]), Decision.REQUIRE_HUMAN),
        (dict(probes={"run_tests": FakeProbe(name="run_tests", passed=False)}), Decision.REJECT),
    ],
    ids=["opa-deny", "block-check", "escalate-denied-by-oracle", "probe-fail"],
)
def test_blocked_actions_do_not_execute(task, workspace, kw, expected):
    before = workspace.snapshot_hashes()
    p = make(workspace, **kw)
    rec = p.run(contract(task, tier=2), task)
    assert rec.final_decision == expected and rec.final_decision in BLOCKED
    assert rec.execution is None and p.executor.calls == 0
    assert workspace.snapshot_hashes() == before
    assert p.ledger.records == [rec]


def test_tier3_asks_oracle_and_denies_by_default(task, workspace):
    oracle = ScriptedOracle()
    rec = make(workspace, oracle=oracle).run(contract(task, tier=3), task)
    assert rec.final_decision == Decision.REQUIRE_HUMAN and not rec.executed
    assert oracle.prompts == 1 and rec.human.approved is False


def test_oracle_approval_executes(task, workspace):
    oracle = ScriptedOracle(approve=lambda c: c.target == "calc/ops.py")
    rec = make(workspace, oracle=oracle).run(contract(task, tier=4), task)
    assert rec.final_decision == Decision.REQUIRE_HUMAN and rec.human.approved and rec.executed
    assert ops(workspace) == FIX


class Boom(Exception):
    pass


def _raising_oracle():
    o = ScriptedOracle()
    o.ask = lambda c, r: (_ for _ in ()).throw(Boom("oracle down"))  # type: ignore[method-assign]
    return o


@pytest.mark.parametrize(
    "kw,tier",
    [
        (dict(policy=FakePolicy(raises=Boom("opa down"))), 1),
        (dict(policy=FakePolicy(allow=True, error="timeout")), 1),
        (dict(checks=[FakeCheck(raises=Boom("check crashed"))]), 1),
        (dict(checks=[FakeCheck(fn=lambda c, t, x: "not a result")]), 1),
        (dict(probes={"run_tests": FakeProbe(raises=Boom("docker gone"))}), 2),
        (dict(probes={"run_tests": FakeProbe(error="timeout")}), 2),
        (dict(probes={}), 2),  # catalog lists a probe that isn't wired
        (dict(probe_catalog={1: ()}), 2),  # tier missing from the catalog
        (dict(), None),  # no tier assigned
        (dict(policy=FakePolicy(raises=Boom("x")), checks=[FakeCheck(raises=Boom("y"))]), 1),
    ],
    ids=["policy-raises", "policy-error", "check-raises", "check-garbage", "probe-raises", "probe-error",
         "probe-missing", "catalog-missing", "tier-none", "everything-raises"],
)
def test_stage_errors_defer_and_nothing_executes(task, workspace, kw, tier):
    before = workspace.snapshot_hashes()
    p = make(workspace, **kw)
    c = contract(task, tier=2 if tier is None else tier)
    if tier is None:
        c = c.model_copy(update={"risk_tier": None})
    rec = p.run(c, task)
    assert rec.final_decision == Decision.DEFER
    assert not rec.executed and p.executor.calls == 0
    assert workspace.snapshot_hashes() == before


def test_oracle_error_counts_as_denial(task, workspace):
    rec = make(workspace, oracle=_raising_oracle()).run(contract(task, tier=3), task)
    assert rec.final_decision == Decision.REQUIRE_HUMAN and not rec.executed


def test_components_never_see_agent_claims(task, workspace):
    policy, check, probe = FakePolicy(), FakeCheck(), FakeProbe(name="run_tests")
    c = contract(task, tier=2, claims={"in_scope": True, "provenance": "user"})
    rec = make(workspace, policy=policy, checks=[check], probes={"run_tests": probe}).run(c, task)
    for seen in (policy.seen, check.seen, probe.seen):
        assert seen and all(x.agent_claims == {} for x in seen)
    assert rec.contract.agent_claims == {"in_scope": True, "provenance": "user"}  # still in the ledger


def test_probes_follow_the_catalog(task, workspace):
    probe = FakeProbe(name="run_tests")
    p = make(workspace, probes={"run_tests": probe})
    p.run(contract(task, tier=1), task)
    assert probe.seen == []
    p.run(contract(task, tier=2), task)
    assert len(probe.seen) == 1


def test_probes_skipped_when_already_blocked(task, workspace):
    probe = FakeProbe(name="run_tests")
    rec = make(workspace, policy=FakePolicy(allow=False), probes={"run_tests": probe}).run(contract(task, tier=2), task)
    assert probe.seen == [] and rec.probes == ()


def test_params_tampered_after_approval_are_not_executed(task, workspace):
    c = contract(task, tier=1)

    def tamper(view, t, ctx):  # a component holding the real contract mutates its params
        c.params["content"] = "import os; os.system('curl evil')\n"
        return CheckResult(name="evil", passed=True)

    p = make(workspace, checks=[FakeCheck(fn=tamper)])
    before = ops(workspace)
    rec = p.run(c, task)
    assert rec.final_decision == Decision.DEFER and not rec.executed
    assert rec.execution.status == "refused" and ops(workspace) == before


def test_mutating_the_view_does_not_change_what_executes(task, workspace):
    def mutate_view(view, t, ctx):
        view.params["content"] = "evil\n"
        return CheckResult(name="c", passed=True)

    rec = make(workspace, checks=[FakeCheck(fn=mutate_view)]).run(contract(task), task)
    assert rec.executed and ops(workspace) == FIX


def test_executor_refusal_defers(task, workspace):
    class Refuser(FakeExecutor):
        def apply(self, *a):
            self.calls += 1
            return super().apply(a[0].model_copy(update={"params": {"path": "calc/ops.py", "content": "other"}}), *a[1:])

    rec = make(workspace, executor=Refuser()).run(contract(task), task)
    assert rec.final_decision == Decision.DEFER and rec.execution.status == "refused"


def test_executor_exception_defers(task, workspace):
    class Crash(FakeExecutor):
        def apply(self, *a):
            raise Boom("disk full")

    rec = make(workspace, executor=Crash()).run(contract(task), task)
    assert rec.final_decision == Decision.DEFER and "disk full" in rec.execution.detail


def test_state_change_during_verification_reverifies(task, workspace):
    calls = []

    def racing(view, t, ctx):
        calls.append(1)
        if len(calls) == 1:  # someone edits the target while we verify
            (workspace.root / "calc/ops.py").write_text("changed underneath\n")
        return CheckResult(name="race", passed=True)

    rec = make(workspace, checks=[FakeCheck(fn=racing)]).run(contract(task), task)
    assert len(calls) == 2 and rec.executed
    assert any("re-verified" in r for r in rec.reasons)


def test_state_that_keeps_changing_defers(task, workspace):
    n = []

    def always(view, t, ctx):
        n.append(1)
        (workspace.root / "calc/ops.py").write_text(f"changed {len(n)}\n")
        return CheckResult(name="race", passed=True)

    p = make(workspace, checks=[FakeCheck(fn=always)])
    rec = p.run(contract(task), task)
    assert rec.final_decision == Decision.DEFER and not rec.executed and p.executor.calls == 0


def test_executor_stale_reverifies(task, workspace):
    class StaleOnce(FakeExecutor):
        def apply(self, *a):
            if self.calls == 0:
                self.calls += 1
                return ExecResult(status="stale", detail="moved")
            return super().apply(*a)

    ex = StaleOnce()
    rec = make(workspace, executor=ex).run(contract(task), task)
    assert rec.executed and ex.calls == 2
    assert any("stale" in r for r in rec.reasons)


def test_outcome_checks_see_after_snapshot(task, workspace):
    outcome = FakeCheck(name="outcome", fn=lambda c, t, ctx: CheckResult(
        name="outcome", passed=set(ctx.snapshot_after) == set(ctx.snapshot_before), reason="new files appeared"))
    rec = make(workspace, outcome_checks=[outcome]).run(contract(task), task)
    assert rec.executed and rec.outcome[0].passed
    ctx = outcome.contexts[0]
    assert ctx.execution.status == "executed"
    assert ctx.snapshot_after["calc/ops.py"] != ctx.snapshot_before["calc/ops.py"]


def test_outcome_failure_is_recorded(task, workspace):
    bad = FakeCheck(name="outcome", result=CheckResult(name="outcome", passed=False, severity="block", reason="tests fail"))
    rec = make(workspace, outcome_checks=[bad]).run(contract(task), task)
    assert rec.executed and any("tests fail" in r for r in rec.reasons)


def test_outcome_not_run_when_blocked(task, workspace):
    outcome = FakeCheck(name="outcome")
    make(workspace, policy=FakePolicy(allow=False), outcome_checks=[outcome]).run(contract(task), task)
    assert outcome.seen == []


def test_snapshot_failure_defers(task, workspace):
    def broken(paths=None):
        raise OSError("io")

    workspace.snapshot_hashes = broken  # type: ignore[method-assign]
    p = make(workspace)
    rec = p.run(contract(task), task)
    assert rec.final_decision == Decision.DEFER and p.executor.calls == 0


def test_ledger_failure_is_loud(task, workspace):
    class BadLedger(InMemoryLedger):
        def append(self, record):
            raise Boom("ledger locked")

    with pytest.raises(Boom):
        make(workspace, ledger=BadLedger()).run(contract(task), task)


def test_record_hash_is_the_contract_hash(task, workspace):
    c = contract(task)
    rec = make(workspace).run(c, task)
    assert rec.contract_hash == c.hash()
