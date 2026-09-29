"""HashBoundExecutor (M6) and an end-to-end pipeline run with the real A-side components."""

import pytest

from av.contracts import ActionContract, ContractBuilder, Decision
from av.executor import HashBoundExecutor
from av.ledger import SqliteLedger
from av.pipeline import Pipeline
from av.policy import OpaPolicyEngine
from tests.fakes import FakeCheck, FakeTaintStore, fake_tier

FIX = "def add(a: int, b: int) -> int:\n    return a + b  # fixed\n"


def write(task, content=FIX, path="calc/ops.py", tier=1):
    return ContractBuilder(tier_fn=fake_tier(default=tier)).build(
        "write_file", {"path": path, "content": content}, task, FakeTaintStore()
    )


def test_applies_when_hash_and_state_match(task, workspace):
    c = write(task)
    snap = workspace.snapshot_hashes()
    res = HashBoundExecutor().apply(c, c.hash(), workspace, snap)
    assert res.status == "executed"
    assert (workspace.root / "calc/ops.py").read_text() == FIX


def test_m6_tampered_params_are_refused(task, workspace):
    approved = write(task)
    snap = workspace.snapshot_hashes()
    evil = ActionContract.model_validate(
        {**approved.model_dump(), "params": {"path": "calc/ops.py", "content": "import os\n"}}
    )
    before = (workspace.root / "calc/ops.py").read_text()
    res = HashBoundExecutor().apply(evil, approved.hash(), workspace, snap)
    assert res.status == "refused"
    assert (workspace.root / "calc/ops.py").read_text() == before


def test_m6_tampered_target_or_tool_is_refused(task, workspace):
    approved = write(task)
    snap = workspace.snapshot_hashes()
    for change in ({"target": "calc/other.py"}, {"tool": "delete_file"}):
        evil = ActionContract.model_validate({**approved.model_dump(), **change})
        assert HashBoundExecutor().apply(evil, approved.hash(), workspace, snap).status == "refused"
    assert (workspace.root / "calc/ops.py").exists()


def test_drift_since_snapshot_is_stale(task, workspace):
    c = write(task)
    snap = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text("changed underneath\n")
    res = HashBoundExecutor().apply(c, c.hash(), workspace, snap)
    assert res.status == "stale"
    assert (workspace.root / "calc/ops.py").read_text() == "changed underneath\n"


def test_drift_in_other_files_is_not_stale(task, workspace):
    """Only the target paths are re-checked by the executor (the pipeline re-checks the rest)."""
    c = write(task)
    snap = workspace.snapshot_hashes()
    (workspace.root / "README.txt").write_text("unrelated\n")
    assert HashBoundExecutor().apply(c, c.hash(), workspace, snap).status == "executed"


def test_new_file_that_appears_is_stale(task, workspace):
    c = write(task, path="calc/new.py")
    snap = workspace.snapshot_hashes(["calc/new.py"])
    assert snap["calc/new.py"] is None
    (workspace.root / "calc/new.py").write_text("raced\n")
    assert HashBoundExecutor().apply(c, c.hash(), workspace, snap).status == "stale"


def test_target_missing_from_snapshot_is_stale(task, workspace):
    c = write(task)
    assert HashBoundExecutor().apply(c, c.hash(), workspace, {}).status == "stale"


def test_delete_is_state_checked(task, workspace):
    c = ContractBuilder().build("delete_file", {"path": "calc/ops.py"}, task, FakeTaintStore())
    snap = workspace.snapshot_hashes()
    (workspace.root / "calc/ops.py").write_text("x\n")
    assert HashBoundExecutor().apply(c, c.hash(), workspace, snap).status == "stale"


def test_read_skips_state_check(task, workspace):
    c = ContractBuilder().build("read_file", {"path": "calc/ops.py"}, task, FakeTaintStore())
    res = HashBoundExecutor().apply(c, c.hash(), workspace, {})
    assert res.status == "executed" and "def add" in res.output


def _pipeline(workspace, tmp_path, tier=1):
    return Pipeline(
        policy=OpaPolicyEngine(),
        checks=[FakeCheck(name="scope")],
        probes={},
        probe_catalog={t: () for t in range(5)},
        executor=HashBoundExecutor(),
        workspace=workspace,
        ledger=SqliteLedger(tmp_path / "e2e.db"),
        taint_store=FakeTaintStore(),
    )


def test_pipeline_end_to_end_with_real_components(task, workspace, tmp_path):
    p = _pipeline(workspace, tmp_path)
    ok = p.run(write(task), task)
    assert ok.final_decision == Decision.ACCEPT and ok.executed
    assert ok.authorization.allow and ok.verification  # M7: separate fields, both populated
    bad = p.run(write(task, path="../escape.py"), task)
    assert bad.final_decision == Decision.REJECT and not bad.executed
    assert not bad.authorization.allow
    assert not (workspace.root.parent / "escape.py").exists()
    assert p.ledger.verify() and len(p.ledger.rows()) == 2


def test_pipeline_defers_when_opa_missing(task, workspace, tmp_path):
    p = _pipeline(workspace, tmp_path)
    p.policy = OpaPolicyEngine(opa_path=tmp_path / "missing")
    rec = p.run(write(task), task)
    assert rec.final_decision == Decision.DEFER and not rec.executed
    assert rec.authorization.error
    assert (workspace.root / "calc/ops.py").read_text() != FIX
    assert p.ledger.verify()


@pytest.mark.parametrize("tier", [1, 2])
def test_pipeline_tamper_between_approval_and_apply_does_not_execute(task, workspace, tmp_path, tier):
    class Tamper(HashBoundExecutor):
        def apply(self, contract, approved_hash, workspace, snapshot):
            evil = ActionContract.model_validate(
                {**contract.model_dump(), "params": {"path": "calc/ops.py", "content": "evil\n"}}
            )
            return super().apply(evil, approved_hash, workspace, snapshot)

    p = _pipeline(workspace, tmp_path, tier)
    p.executor = Tamper()
    rec = p.run(write(task, tier=tier), task)
    assert not rec.executed and rec.final_decision == Decision.DEFER
    assert (workspace.root / "calc/ops.py").read_text() != "evil\n"
