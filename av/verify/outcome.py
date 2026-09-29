"""OutcomeCheck: after execution, did only the intended thing happen?

1. Side effects: every path whose hash differs between the pre-execution snapshot and the
   post-execution snapshot must be the contract's target (for write_file / delete_file) and
   nothing at all for the other tools. Anything else -> failed, severity block.
2. Tests: for a mutating action, the suite must still pass. It runs through a Probe (Agent C's
   RunTestsProbe once merged; a stub in tests) on a no-op run_tests contract, so the probe
   just runs the suite on a disposable copy of the workspace as it now is. A failure ->
   failed, severity escalate.

An outcome check never changes the decision (the action already ran); the pipeline records the
result in the ledger and the reasons. It fails loudly (error set) when it can't evaluate:
no after-snapshot, no execution result, or no tests probe wired.
"""

from __future__ import annotations

from av.contracts import ActionContract, CheckResult, TaskDefinition
from av.interfaces import CheckContext, Probe
from av.verify import paths


class OutcomeCheck:
    """Outcome check (Pipeline(outcome_checks=[OutcomeCheck(run_tests_probe)]))."""

    name = "outcome"

    def __init__(self, tests_probe: Probe | None):
        self.tests_probe = tests_probe

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        if ctx.execution is None:
            return self._error("no execution result")
        if ctx.snapshot_after is None:
            return self._error("no post-execution snapshot")

        before, after = dict(ctx.snapshot_before), dict(ctx.snapshot_after)
        changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        allowed: set[str] = set()
        if contract.is_mutating:
            norm = paths.lexical(contract.params.get("path"))
            if norm.path is not None:
                allowed.add(norm.path)
                # A write through an (in-scope, already verified) symlink changes its target.
                resolved = paths.resolve_in_workspace(ctx.workspace.root, contract.params["path"])
                if resolved.path is not None:
                    allowed.add(resolved.path)
        unexpected = [p for p in changed if p not in allowed]
        if unexpected:
            return CheckResult(
                name=self.name,
                passed=False,
                severity="block",
                reason=f"unexpected side effects: changed {unexpected[:10]} beyond the contract's target {sorted(allowed)}",
            )
        if contract.is_mutating and not changed and contract.tool == "delete_file":
            return CheckResult(name=self.name, passed=False, severity="escalate", reason="delete_file changed nothing")

        if not contract.is_mutating:
            return CheckResult(name=self.name, passed=True, reason=f"{contract.tool}: no workspace change, as expected")
        if self.tests_probe is None:
            return self._error("no run_tests probe wired for the outcome check")

        noop = ActionContract(task_id=contract.task_id, tool="run_tests", target=".", params={}, derived_scope_ok=True)
        res = self.tests_probe.run(noop, ctx.workspace)
        if res.error is not None:
            return self._error(f"tests probe error: {res.error}")
        if not res.passed:
            return CheckResult(
                name=self.name,
                passed=False,
                severity="escalate",
                reason=f"tests fail after execution: {res.summary}",
            )
        return CheckResult(name=self.name, passed=True, reason=f"changed {changed}; tests pass: {res.summary}")

    def _error(self, msg: str) -> CheckResult:
        return CheckResult(name=self.name, passed=False, severity="block", error=msg)
