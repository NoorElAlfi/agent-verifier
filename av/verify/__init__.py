"""Verification ("SHOULD it?"): risk tiering, scope drift, provenance, outcome.

Wiring (see progress/w2-B.md):
    ContractBuilder(scope_fn=scope_ok, tier_fn=assign_tier)
    Pipeline(checks=verification_checks(), probe_catalog=PROBE_CATALOG, tier_fn=assign_tier,
             taint_store=<the gateway's TaintStoreImpl>, outcome_checks=outcome_checks(probe))
"""

from __future__ import annotations

from av.interfaces import Check, Probe
from av.verify.outcome import OutcomeCheck
from av.verify.scope import ScopeDriftCheck, scope_ok
from av.verify.taint import ProvenanceCheck, TaintStoreImpl
from av.verify.tiering import PROBE_CATALOG, assign_tier, tier_for


def verification_checks() -> list[Check]:
    """The pre-execution checks in spec order (scope drift, then provenance)."""
    return [ScopeDriftCheck(), ProvenanceCheck()]


def outcome_checks(tests_probe: Probe | None) -> list[Check]:
    return [OutcomeCheck(tests_probe)]


__all__ = [
    "PROBE_CATALOG",
    "OutcomeCheck",
    "ProvenanceCheck",
    "ScopeDriftCheck",
    "TaintStoreImpl",
    "assign_tier",
    "outcome_checks",
    "scope_ok",
    "tier_for",
    "verification_checks",
]
