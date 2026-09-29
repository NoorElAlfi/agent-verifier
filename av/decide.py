"""SHARED: decide(), the spec's default decision table as a pure function.

Inputs are gateway-derived only: the authorization result, the verification check results, the
probe results and the risk tier. There is deliberately no contract parameter, so agent_claims
cannot reach a decision (CLAUDE.md rule 3).

Rows are evaluated top to bottom; the first match wins. Stricter outcomes come first, so a
reject is never downgraded to require_human by a later row.

| row | condition                                                  | decision            |
|-----|------------------------------------------------------------|---------------------|
| E1  | authorization errored or timed out                         | defer               |
| R1  | OPA deny                                                   | reject              |
| E2  | any check or probe errored; tier missing or not 0..4       | defer               |
| R2  | a failed check with severity=block (protected-class drift, | reject              |
|     | tainted params)                                            |                     |
| R3  | any probe failed                                           | reject              |
| R4  | a failed check with severity=escalate (other scope drift)  | require_human       |
| R5  | tier 3-4                                                   | require_human       |
| R6  | tier 0, clean checks                                       | accept_with_logging |
| R7  | tier 1-2, clean checks, probes passed (or none required)   | accept              |

Any exception inside decide() itself also gives defer (fail closed).
"""

from __future__ import annotations

from collections.abc import Sequence

from av.contracts import AuthzResult, CheckResult, Decision, ProbeResult

#: (row id, decision) in evaluation order; the docstring above is the human-readable version.
DECISION_TABLE: tuple[tuple[str, Decision], ...] = (
    ("E1", Decision.DEFER),
    ("R1", Decision.REJECT),
    ("E2", Decision.DEFER),
    ("R2", Decision.REJECT),
    ("R3", Decision.REJECT),
    ("R4", Decision.REQUIRE_HUMAN),
    ("R5", Decision.REQUIRE_HUMAN),
    ("R6", Decision.ACCEPT_WITH_LOGGING),
    ("R7", Decision.ACCEPT),
)


def _decide(
    authz: AuthzResult,
    checks: Sequence[CheckResult],
    probes: Sequence[ProbeResult],
    tier: int | None,
) -> tuple[Decision, list[str]]:
    if not isinstance(authz, AuthzResult):
        raise TypeError("authz must be an AuthzResult")
    if authz.error is not None:
        return Decision.DEFER, [f"E1 authorization error: {authz.error}"]
    if not authz.allow:
        return Decision.REJECT, ["R1 authorization denied", *authz.reasons]

    errors = [f"check {c.name} error: {c.error}" for c in checks if c.error is not None]
    errors += [f"probe {p.name} error: {p.error}" for p in probes if p.error is not None]
    if type(tier) is not int or not 0 <= tier <= 4:
        errors.append(f"invalid risk tier: {tier!r}")
    if errors:
        return Decision.DEFER, ["E2 verification could not complete", *errors]

    blocking = [f"{c.name}: {c.reason}" for c in checks if not c.passed and c.severity == "block"]
    if blocking:
        return Decision.REJECT, ["R2 blocking check failed", *blocking]

    failed_probes = [f"{p.name}: {p.summary}" for p in probes if not p.passed]
    if failed_probes:
        return Decision.REJECT, ["R3 probe failed", *failed_probes]

    escalating = [f"{c.name}: {c.reason}" for c in checks if not c.passed and c.severity == "escalate"]
    if escalating:
        return Decision.REQUIRE_HUMAN, ["R4 check requires a human", *escalating]

    notes = [f"{c.name}: {c.reason}" for c in checks if not c.passed]  # severity=info only
    if tier >= 3:
        return Decision.REQUIRE_HUMAN, [f"R5 risk tier {tier} requires a human", *notes]
    if tier == 0:
        return Decision.ACCEPT_WITH_LOGGING, ["R6 tier 0, checks clean", *notes]
    return Decision.ACCEPT, [f"R7 tier {tier}, checks clean, probes passed", *notes]


def decide(
    authz: AuthzResult,
    checks: Sequence[CheckResult],
    probes: Sequence[ProbeResult],
    tier: int | None,
) -> tuple[Decision, list[str]]:
    """Apply the default decision table. Pure; never raises; any internal error -> defer."""
    try:
        return _decide(authz, list(checks), list(probes), tier)
    except Exception as exc:  # fail closed
        return Decision.DEFER, [f"decide() error: {type(exc).__name__}: {exc}"]
