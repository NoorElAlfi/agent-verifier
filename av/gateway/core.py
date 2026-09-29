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

    @staticmethod
    def _source_ref(tool: str, target: str) -> str:
        return target if tool == "read_file" else f"{tool}:{target}"

    @staticmethod
    def _output(tool: str, record: DecisionRecord) -> str:
        if tool == "run_tests":
            for p in record.probes:
                if p.name == "run_tests":
                    return p.summary
            return "(no test output: the run_tests probe did not run)"
        out = record.execution.output if record.execution else None
        return "" if out is None else str(out)
