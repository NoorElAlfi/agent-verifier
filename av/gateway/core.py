"""The gateway's single code path, shared by the MCP server (live agent) and replay.

    tool call -> ContractBuilder (scope from the TaskDefinition, provenance from the TaintStore;
              agent claims only recorded) -> Pipeline.run() -> reply to the agent
              -> (if executed) read results recorded into the TaintStore as untrusted content

All six tools, reads included, go through the pipeline (full mediation, CLAUDE.md rule 4). The
agent only ever gets the reply text; agent-supplied fields never reach decide() (rule 3).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av.contracts import ACCEPTED, ContractBuilder, ContractError, Decision, DecisionRecord, TaskDefinition
from av.gateway import wiring
from av.gateway.workspace import SandboxWorkspace
from av.pipeline import Pipeline, ScriptedOracle


@dataclass(frozen=True)
class GatewayReply:
    tool: str
    text: str
    decision: Decision | None
    executed: bool
    record: DecisionRecord | None = None
    error: str | None = None

    @property
    def blocked(self) -> bool:
        return self.decision is None or self.decision not in ACCEPTED or not self.executed


class Gateway:
    def __init__(
        self,
        task: TaskDefinition,
        workspace_root: Path,
        ledger_path: Path,
        components: dict | None = None,
        oracle: ScriptedOracle | None = None,
    ):
        self.task = task
        self.workspace = SandboxWorkspace(root=Path(workspace_root))
        c = wiring.build_components(ledger_path, components)
        self.components = c
        self.ledger = c.ledger
        self.taint_store = c.taint_store
        self.oracle = oracle or ScriptedOracle()
        self.builder = ContractBuilder(scope_fn=c.scope_fn, tier_fn=c.tier_fn)
        self.pipeline = Pipeline(
            policy=c.policy,
            checks=c.checks,
            probes=c.probes,
            probe_catalog=c.probe_catalog,
            executor=c.executor,
            workspace=self.workspace,
            ledger=c.ledger,
            taint_store=c.taint_store,
            outcome_checks=c.outcome_checks,
            oracle=self.oracle,
            tier_fn=c.tier_fn,
        )
        self.refusals_path = Path(str(ledger_path) + ".refusals.jsonl")
        self.refusals_path.parent.mkdir(parents=True, exist_ok=True)
        # run_tests probe results the gateway runs itself (after the ledger row) are logged here.
        self.probe_log_path = Path(str(ledger_path) + ".run_tests.jsonl")
        self._lock = threading.Lock()

    def call(self, tool: str, params: dict[str, Any] | None = None, agent_claims: Any = None) -> GatewayReply:
        """One tool call. `agent_claims` goes to the ledger only."""
        with self._lock:
            return self._call(tool, dict(params or {}), agent_claims)

    def _call(self, tool: str, params: dict[str, Any], agent_claims: Any) -> GatewayReply:
        try:
            contract = self.builder.build(tool, params, self.task, self.taint_store, agent_claims)
        except ContractError as exc:
            self._log_refusal(tool, params, str(exc))
            return GatewayReply(tool, f"REFUSED (invalid call): {exc}\nNothing was executed.", None, False, error=str(exc))

        record = self.pipeline.run(contract, self.task)
        executed = record.executed
        output = self._output(tool, record) if executed else ""
        if executed and tool == "run_tests" and not any(p.name == "run_tests" for p in record.probes):
            # The tier catalog runs no probe for a read-only tool; the result the agent sees still
            # comes from the sandboxed run_tests probe on a disposable copy, never the host.
            output = self._run_tests_probe(contract)
        if executed and tool in ("list_files", "read_file", "run_tests"):
            self.taint_store.record_read(self._source_ref(tool, contract.target), output)

        lines = [f"decision: {record.final_decision.value}"]
        if record.reasons:
            lines.append("reasons: " + "; ".join(record.reasons))
        lines.append("executed: yes" if executed else "executed: NO (nothing changed)")
        if output:
            lines.append("")
            lines.append(output)
        return GatewayReply(tool, "\n".join(lines), record.final_decision, executed, record)

    def _log_refusal(self, tool: str, params: dict[str, Any], error: str) -> None:
        """A call that could not become a contract has no DecisionRecord, so it is logged here
        (rule 5: errors are logged; nothing executed)."""
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "task_id": self.task.task_id,
            "tool": tool,
            "params": {k: (v[:200] if isinstance(v, str) else repr(v)[:200]) for k, v in params.items()},
            "error": error,
        }
        with self.refusals_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def _run_tests_probe(self, contract) -> str:
        probe = self.components.probes.get("run_tests")
        if probe is None:
            self._log_probe(contract, passed=False, summary="", error="no run_tests probe is wired")
            return "(no test output: no run_tests probe is wired)"
        try:
            r = probe.run(contract, self.workspace)
        except Exception as exc:  # noqa: BLE001 - logged and reported to the agent; nothing executes
            self._log_probe(contract, passed=False, summary="", error=f"{type(exc).__name__}: {exc}")
            return f"(tests could not run: {type(exc).__name__})"
        self._log_probe(contract, passed=r.passed, summary=r.summary, error=r.error)
        return f"(tests could not run: {r.error})" if r.error else self._probe_text(r)

    def _log_probe(self, contract, passed: bool, summary: str, error: str | None) -> None:
        """The pipeline's ledger row for this call is already written, so the probe's own result
        (including any error, rule 5) goes to a side log next to the ledger."""
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "task_id": self.task.task_id,
            "contract_hash": contract.hash(),
            "probe": "run_tests",
            "passed": passed,
            "summary": summary,
            "error": error,
        }
        with self.probe_log_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    @staticmethod
    def _probe_text(result) -> str:
        """pytest's output tail (which tests failed), falling back to the one-line summary."""
        tail = (result.details or {}).get("output_tail")
        return str(tail).strip() if tail else result.summary

    @staticmethod
    def _source_ref(tool: str, target: str) -> str:
        return target if tool == "read_file" else f"{tool}:{target}"

    @staticmethod
    def _output(tool: str, record: DecisionRecord) -> str:
        if tool == "run_tests":
            for p in record.probes:
                if p.name == "run_tests":
                    return Gateway._probe_text(p)
            return "(no test output: the run_tests probe did not run)"
        out = record.execution.output if record.execution else None
        return "" if out is None else str(out)
