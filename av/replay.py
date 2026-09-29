"""Replay scenario fixtures through the SAME gateway code path a live agent uses. No model calls.

    uv run python -m av.replay [scenario_id ...]

Each scenario runs on a fresh private copy of its repo (plus its `overlay/`), so
`examples/sample_repo` is never modified. A hash-chained ledger per scenario is written under
`AV_DATA_DIR/ledgers/<run>/`. Ends by printing "hosted calls: N" (always 0: any attempt to reach
a hosted or Ollama client during replay raises).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from av import clients, quota
from av.config import data_dir
from av.contracts import ACCEPTED
from av.gateway import wiring
from av.gateway.core import Gateway
from av.gateway.workspace import prepare_workspace
from av.scenarios import Scenario, list_scenarios, load_scenario


class _NoModel:
    """Injected for the whole replay: replay makes no model calls, so any call is a bug."""

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("replay must not call a model")


@contextmanager
def no_model_calls():
    with clients.use_clients(hosted=_NoModel(), ollama=_NoModel()):
        yield


@dataclass
class Step:
    n: int
    tool: str
    target: str
    tier: int | None
    decision: str
    executed: bool
    expected: str | None
    note: str = ""

    @property
    def matches(self) -> bool:
        return self.expected is None or self.expected == self.decision


@dataclass
class ScenarioResult:
    id: str
    origin: str
    steps: list[Step] = field(default_factory=list)
    expected_outcome: str | None = None
    ledger_path: Path | None = None
    ledger_ok: bool = False

    @property
    def outcome(self) -> str:
        """"blocked" if any action was not accepted-and-executed, else "accept"."""
        return "blocked" if any(not (s.decision in {d.value for d in ACCEPTED} and s.executed) for s in self.steps) else "accept"

    @property
    def ok(self) -> bool:
        return (
            all(s.matches for s in self.steps)
            and (self.expected_outcome is None or self.expected_outcome == self.outcome)
            and self.ledger_ok
        )


@dataclass
class ReplayReport:
    results: list[ScenarioResult]
    hosted_calls: int
    seconds: float
    components: str

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results) and self.hosted_calls == 0


def episode_workspace(scenario: Scenario, dest: Path) -> Path:
    return prepare_workspace(scenario.workspace, dest, scenario.dir / "overlay")


def replay_scenario(scenario: Scenario, run_dir: Path) -> ScenarioResult:
    ws = episode_workspace(scenario, run_dir / scenario.id / "ws")
    ledger_path = run_dir / f"{scenario.id}.jsonl"
    gw = Gateway(scenario.task, ws, ledger_path)
    res = ScenarioResult(
        id=scenario.id,
        origin=scenario.origin,
        expected_outcome=scenario.header.model_extra.get("scenario_outcome") if scenario.header.model_extra else None,
        ledger_path=ledger_path,
    )
    for i, p in enumerate(scenario.proposals, 1):
        reply = gw.call(p.tool, p.params, p.agent_claims)
        rec = reply.record
        res.steps.append(
            Step(
                n=i,
                tool=p.tool,
                target=(rec.contract.target if rec else "") or "",
                tier=rec.risk_tier if rec else None,
                decision=reply.decision.value if reply.decision else "refused",
                executed=reply.executed,
                expected=p.expect.value if p.expect else None,
                note=p.note,
            )
        )
    res.ledger_ok = gw.ledger.verify()
    return res


def replay(scenario_ids: list[str] | None = None, run_id: str | None = None) -> ReplayReport:
    ids = scenario_ids or list_scenarios()
    run_id = run_id or "replay-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir = data_dir() / "ledgers" / run_id
    before = quota.usage()["total"]
    t0 = time.monotonic()
    with no_model_calls():
        results = [replay_scenario(load_scenario(i), run_dir) for i in ids]
    return ReplayReport(
        results=results,
        hosted_calls=quota.usage()["total"] - before,
        seconds=time.monotonic() - t0,
        components=wiring.describe(),
    )


def format_report(report: ReplayReport) -> str:
    out: list[str] = [f"components: {report.components}", ""]
    for r in report.results:
        out.append(f"scenario {r.id}  [fixtures: {r.origin}]")
        out.append(f"  {'#':>2}  {'tool':<11} {'target':<28} {'tier':>4}  {'decision':<20} {'executed':<8} expected")
        for s in r.steps:
            flag = "" if s.matches else "   <-- MISMATCH"
            out.append(
                f"  {s.n:>2}  {s.tool:<11} {s.target or '-':<28} {s.tier if s.tier is not None else '-':>4}  "
                f"{s.decision:<20} {'yes' if s.executed else 'no':<8} {s.expected or '-'}{flag}"
            )
        verdict = "OK" if r.ok else "FAIL"
        out.append(
            f"  outcome: {r.outcome} (expected {r.expected_outcome or '-'})  ledger chain: "
            f"{'ok' if r.ledger_ok else 'BROKEN'}  -> {verdict}"
        )
        out.append("")
    out.append(f"replay wall time: {report.seconds:.1f}s")
    out.append(f"hosted calls: {report.hosted_calls}")
    return "\n".join(out)


def main(argv: list[str] | None = None, echo: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenarios", nargs="*", help="scenario ids (default: all, excluding _example)")
    args = ap.parse_args(argv)
    report = replay(args.scenarios or None)
    echo(format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
