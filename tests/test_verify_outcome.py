"""OutcomeCheck units, and the M4 unit half end to end: a benign in-scope fix goes through the
real checks, is accepted and executed with zero human prompts, and the tests pass after."""

import pytest

from av.contracts import Decision, ExecResult, TaskDefinition
from av.interfaces import CheckContext
from av.pipeline import ScriptedOracle
from av.verify import OutcomeCheck, TaintStoreImpl
from tests.fakes import FakeProbe
from tests.test_verify_helpers import LocalPytestProbe, build, pipeline

# The benign fix for the sample repo's real bug (floor division in average()).
FIX = (
    "def add(a: int, b: int) -> int:\n    return a + b\n\n\n"
    "def average(values: list[float]) -> float:\n    return sum(values) / len(values)\n"
)
BREAK = "def add(a: int, b: int) -> int:\n    return a - b\n"


def octx(workspace, before, after, execution=ExecResult(status="executed")):
    return CheckContext(
        workspace=workspace, taint_store=TaintStoreImpl(), snapshot_before=before, snapshot_after=after, execution=execution
    )


def test_only_target_changed_and_tests_pass(task, workspace):
    before = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text(FIX)
    probe = FakeProbe(name="run_tests")
    c = build(task, "write_file", {"path": "calc/ops.py", "content": FIX})
    res = OutcomeCheck(probe).run(c, task, octx(workspace, before, workspace.snapshot_hashes()))
    assert res.passed, res.reason
    assert probe.seen[0].tool == "run_tests" and probe.seen[0].params == {}


def test_extra_changed_path_is_flagged(task, workspace):
    before = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text(FIX)
    (workspace.root / "calc/extra.py").write_text("x = 1\n")
    c = build(task, "write_file", {"path": "calc/ops.py", "content": FIX})
    res = OutcomeCheck(FakeProbe()).run(c, task, octx(workspace, before, workspace.snapshot_hashes()))
    assert not res.passed and res.severity == "block" and "calc/extra.py" in res.reason


def test_read_that_changed_something_is_flagged(task, workspace):
    before = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text(FIX)
    c = build(task, "read_file", {"path": "calc/ops.py"})
    res = OutcomeCheck(FakeProbe()).run(c, task, octx(workspace, before, workspace.snapshot_hashes()))
    assert not res.passed and res.severity == "block"


def test_failing_tests_after_execution_are_flagged(task, workspace):
    before = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text(BREAK)
    c = build(task, "write_file", {"path": "calc/ops.py", "content": BREAK})
    res = OutcomeCheck(FakeProbe(name="run_tests", passed=False)).run(c, task, octx(workspace, before, workspace.snapshot_hashes()))
    assert not res.passed and res.severity == "escalate"


@pytest.mark.parametrize(
    "probe,after,execution,msg",
    [
        (None, "same", ExecResult(status="executed"), "no run_tests probe"),
        (FakeProbe(error="boom"), "same", ExecResult(status="executed"), "tests probe error"),
        (FakeProbe(), None, ExecResult(status="executed"), "no post-execution snapshot"),
        (FakeProbe(), "same", None, "no execution result"),
    ],
)
def test_cannot_evaluate_is_an_error(task, workspace, probe, after, execution, msg):
    before = workspace.snapshot_hashes()
    c = build(task, "write_file", {"path": "calc/ops.py", "content": FIX})
    res = OutcomeCheck(probe).run(c, task, octx(workspace, before, before if after == "same" else after, execution))
    assert res.error and msg in res.error


# --------------------------------------------------------------------------- M4 (unit half)


def test_m4_benign_fix_accepted_executed_no_prompts_tests_pass(task, workspace):
    store = TaintStoreImpl()
    oracle = ScriptedOracle()
    p = pipeline(workspace, store=store, oracle=oracle, tests_probe=LocalPytestProbe())
    records = []
    for tool, params in [("list_files", {}), ("read_file", {"path": "calc/ops.py"}), ("read_file", {"path": "tests/test_ops.py"})]:
        rec = p.run(build(task, tool, params, store=store), task)
        if tool == "read_file":
            store.record_read(f"read_file:{params['path']}", rec.execution.output)  # the gateway's job
        records.append(rec)
    fix = p.run(build(task, "write_file", {"path": "calc/ops.py", "content": FIX}, store=store, claims={"in_scope": True}), task)
    records.append(fix)

    assert [r.final_decision for r in records[:3]] == [Decision.ACCEPT_WITH_LOGGING] * 3
    assert fix.final_decision == Decision.ACCEPT and fix.executed and fix.risk_tier == 1
    assert oracle.prompts == 0
    assert (workspace.root / "calc/ops.py").read_text() == FIX
    [outcome] = fix.outcome
    assert outcome.passed and "passed" in outcome.reason, outcome
    assert p.ledger.verify()


def test_m4_breaking_tier1_edit_executes_but_outcome_records_failure(task, workspace):
    p = pipeline(workspace, tests_probe=LocalPytestProbe())
    rec = p.run(build(task, "write_file", {"path": "calc/ops.py", "content": BREAK}), task)
    assert rec.final_decision == Decision.ACCEPT and rec.executed
    assert not rec.outcome[0].passed and any("tests fail after execution" in r for r in rec.reasons)


def test_tier2_runs_tests_before_execution_and_rejects_a_breaking_change(workspace):
    t = TaskDefinition(task_id="t2", objective="tidy tests", scope_globs=("calc/*.py", "tests/*.py"))
    p = pipeline(workspace, probes={"diff": FakeProbe("diff"), "secret_scan": FakeProbe("secret_scan"), "run_tests": LocalPytestProbe()})
    bad = "from calc.ops import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n"
    rec = p.run(build(t, "write_file", {"path": "tests/test_ops.py", "content": bad}), t)
    assert rec.risk_tier == 2 and rec.final_decision == Decision.REJECT and not rec.executed
    assert "== 5" in (workspace.root / "tests/test_ops.py").read_text()
