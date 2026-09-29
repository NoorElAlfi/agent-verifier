"""The ONE place where the gateway's components are chosen.

Wave 2 built policy/ledger/executor (A), checks/tiering/taint (B) and probes (C) in parallel;
the Wave 2 merge swapped D's stand-ins for the real components here. `describe()` prints the
labels so a demo shows what it ran on ("components: policy=real ..."), and the live path refuses
to run while any row is labelled `standin` (av/agent/react.py).

The run_tests tool result is read from the probe named "run_tests" (its `summary`); when the
tier's catalog doesn't list that probe, the gateway runs it itself (still sandboxed).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av.executor import HashBoundExecutor
from av.ledger import SqliteLedger
from av.policy import OpaPolicyEngine
from av.probes import DiffProbe, RunTestsProbe, SecretScanProbe
from av.verify import PROBE_CATALOG, TaintStoreImpl, assign_tier, outcome_checks, scope_ok, verification_checks

#: name -> (label, factory). Factories take no arguments, except "ledger" which takes the path.
COMPONENTS: dict[str, tuple[str, Callable[..., Any]]] = {
    "policy": ("real", lambda: OpaPolicyEngine()),
    "checks": ("real", lambda: verification_checks()),
    "outcome_checks": ("real", lambda: outcome_checks(RunTestsProbe())),
    "probes": ("real", lambda: {p.name: p for p in (RunTestsProbe(), DiffProbe(), SecretScanProbe())}),
    "probe_catalog": ("real", lambda: dict(PROBE_CATALOG)),
    "tier_fn": ("real", lambda: assign_tier),
    "scope_fn": ("real", lambda: scope_ok),
    "taint_store": ("real", lambda: TaintStoreImpl()),
    "executor": ("real", lambda: HashBoundExecutor()),
    "ledger": ("real", lambda path: SqliteLedger(path)),
}


@dataclass(frozen=True)
class Built:
    policy: Any
    checks: Any
    outcome_checks: Any
    probes: Any
    probe_catalog: Any
    tier_fn: Any
    scope_fn: Any
    taint_store: Any
    executor: Any
    ledger: Any


def build_components(ledger_path: Path, components: dict[str, tuple[str, Callable[..., Any]]] | None = None) -> Built:
    table = components or COMPONENTS
    made = {name: (factory(ledger_path) if name == "ledger" else factory()) for name, (_, factory) in table.items()}
    return Built(**made)


def describe(components: dict[str, tuple[str, Callable[..., Any]]] | None = None) -> str:
    table = components or COMPONENTS
    return " ".join(f"{name}={label}" for name, (label, _) in table.items())


def standins(components: dict[str, tuple[str, Callable[..., Any]]] | None = None) -> list[str]:
    """Names of components still labelled `standin`."""
    table = components or COMPONENTS
    return [name for name, (label, _) in table.items() if label == "standin"]
