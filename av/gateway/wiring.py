"""The ONE place where the gateway's components are chosen.

Wave 2 built policy/ledger/executor (A), checks/tiering/taint (B) and probes (C) in parallel, so
each entry below is a clearly labelled STAND-IN from `av/gateway/standins.py`. The merge step
replaces an entry by changing its factory (and its label) here; nothing else in the gateway,
replay or agent code changes. `describe()` prints the labels so a demo can never silently run
on stand-ins: `make demo` shows "components: policy=standin ...".

To swap in a real component, edit the matching row, for example:

    "policy":  ("real", lambda: OpaPolicyEngine()),
    "ledger":  ("real", lambda path: SqliteLedger(path)),
    "checks":  ("real", lambda: [ScopeDriftCheck(), ProvenanceCheck()]),
    "tier_fn": ("real", lambda: assign_tier),
    "probe_catalog": ("real", lambda: TIER_PROBES),
    "probes":  ("real", lambda: {"run_tests": RunTestsProbe(), "diff": DiffProbe(), ...}),

The run_tests tool result is read from the probe named "run_tests" (its `summary`), so the real
RunTestsProbe must be registered under that name and put its output in `summary`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av.contracts import basic_scope_ok
from av.gateway import standins as s

#: name -> (label, factory). Factories take no arguments, except "ledger" which takes the path.
COMPONENTS: dict[str, tuple[str, Callable[..., Any]]] = {
    "policy": ("standin", lambda: s.StandInPolicy()),
    "checks": ("standin", lambda: [s.StandInScopeCheck(), s.StandInProvenanceCheck()]),
    "outcome_checks": ("none", lambda: []),
    "probes": ("standin", lambda: {"run_tests": s.StandInRunTestsProbe()}),
    "probe_catalog": ("standin", lambda: dict(s.STAND_IN_CATALOG)),
    "tier_fn": ("standin", lambda: s.stand_in_tier),
    "scope_fn": ("core", lambda: basic_scope_ok),
    "taint_store": ("standin", lambda: s.StandInTaintStore()),
    "executor": ("standin", lambda: s.StandInExecutor()),
    "ledger": ("standin", lambda path: s.ChainLedger(path)),
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
