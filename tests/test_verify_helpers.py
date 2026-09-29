"""Shared helpers for the tests/test_verify_*.py files (not a test module itself)."""

from __future__ import annotations

import subprocess
import sys

from av.contracts import ActionContract, ContractBuilder, ProbeResult, TaskDefinition
from av.interfaces import CheckContext, Workspace
from av.verify import PROBE_CATALOG, TaintStoreImpl, assign_tier, outcome_checks, scope_ok, verification_checks
from av.pipeline import Pipeline, ScriptedOracle
from tests.fakes import FakeExecutor, FakePolicy, FakeProbe, InMemoryLedger

BUILDER = ContractBuilder(scope_fn=scope_ok, tier_fn=assign_tier)


def build(task: TaskDefinition, tool: str, params: dict, store=None, claims=None) -> ActionContract:
    return BUILDER.build(tool, params, task, store or TaintStoreImpl(), agent_claims=claims)


def ctx(workspace: Workspace, store=None) -> CheckContext:
    return CheckContext(workspace=workspace, taint_store=store or TaintStoreImpl())


class LocalPytestProbe:
    """Stand-in for Agent C's RunTestsProbe (not merged yet): applies the contract to a
    disposable copy and runs pytest there in a subprocess. No Docker, so it is NOT the isolation
    M3b needs; it only lets these tests check "tests pass" for real."""

    name = "run_tests"

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        with workspace.disposable_copy() as root:
            target = root / contract.target
            if contract.tool == "write_file":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contract.params["content"])
            elif contract.tool == "delete_file":
                target.unlink()
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
                env={"PYTHONDONTWRITEBYTECODE": "1"},
            )
        last = (proc.stdout.strip().splitlines() or [""])[-1]
        return ProbeResult(name=self.name, passed=proc.returncode == 0, summary=last)


def pipeline(workspace, store=None, oracle=None, tests_probe=None, **kw) -> Pipeline:
    probes = {n: FakeProbe(name=n) for n in ("diff", "secret_scan", "run_tests")}
    parts = dict(
        policy=FakePolicy(),
        checks=verification_checks(),
        probes=probes,
        probe_catalog=PROBE_CATALOG,
        executor=FakeExecutor(),
        workspace=workspace,
        ledger=InMemoryLedger(),
        taint_store=store or TaintStoreImpl(),
        outcome_checks=outcome_checks(tests_probe or FakeProbe(name="run_tests")),
        oracle=oracle or ScriptedOracle(),
        tier_fn=assign_tier,
    )
    parts.update(kw)
    return Pipeline(**parts)
