"""Every row of the spec's default decision table, its precedence, and fail-closed behaviour."""

import pytest

from av.contracts import BLOCKED, AuthzResult, CheckResult, Decision, ProbeResult
from av.decide import DECISION_TABLE, decide

ALLOW = AuthzResult(allow=True)
OK = CheckResult(name="scope", passed=True)
BLOCK = CheckResult(name="provenance", passed=False, severity="block", reason="tainted params")
PROTECTED = CheckResult(name="scope", passed=False, severity="block", reason="drift into ci")
ESCALATE = CheckResult(name="scope", passed=False, severity="escalate", reason="out of scope")
INFO = CheckResult(name="note", passed=False, severity="info", reason="fyi")
CHECK_ERR = CheckResult(name="scope", passed=False, severity="block", error="boom")
PROBE_OK = ProbeResult(name="run_tests", passed=True)
PROBE_FAIL = ProbeResult(name="run_tests", passed=False, summary="1 failed")
PROBE_ERR = ProbeResult(name="run_tests", passed=False, error="timeout")


def row(reasons):
    return reasons[0].split()[0]


# (id, authz, checks, probes, tier, expected decision, expected row)
ROWS = [
    ("opa-error", AuthzResult(allow=False, error="timeout"), [OK], [], 1, Decision.DEFER, "E1"),
    ("opa-deny", AuthzResult(allow=False, reasons=("path denied",)), [OK], [], 1, Decision.REJECT, "R1"),
    ("check-error", ALLOW, [CHECK_ERR], [], 1, Decision.DEFER, "E2"),
    ("probe-error", ALLOW, [OK], [PROBE_ERR], 1, Decision.DEFER, "E2"),
    ("tier-none", ALLOW, [OK], [], None, Decision.DEFER, "E2"),
    ("tier-5", ALLOW, [OK], [], 5, Decision.DEFER, "E2"),
    ("tier-neg", ALLOW, [OK], [], -1, Decision.DEFER, "E2"),
    ("tier-bool", ALLOW, [OK], [], True, Decision.DEFER, "E2"),
    ("protected-drift", ALLOW, [PROTECTED], [], 2, Decision.REJECT, "R2"),
    ("tainted", ALLOW, [BLOCK], [], 1, Decision.REJECT, "R2"),
    ("probe-fail", ALLOW, [OK], [PROBE_FAIL], 2, Decision.REJECT, "R3"),
    ("other-drift", ALLOW, [ESCALATE], [], 1, Decision.REQUIRE_HUMAN, "R4"),
    ("tier-3", ALLOW, [OK], [PROBE_OK], 3, Decision.REQUIRE_HUMAN, "R5"),
    ("tier-4", ALLOW, [OK], [], 4, Decision.REQUIRE_HUMAN, "R5"),
    ("tier-0-clean", ALLOW, [OK], [], 0, Decision.ACCEPT_WITH_LOGGING, "R6"),
    ("tier-0-info", ALLOW, [OK, INFO], [], 0, Decision.ACCEPT_WITH_LOGGING, "R6"),
    ("tier-1-clean", ALLOW, [OK], [], 1, Decision.ACCEPT, "R7"),
    ("tier-2-probes-pass", ALLOW, [OK], [PROBE_OK], 2, Decision.ACCEPT, "R7"),
    ("tier-2-info", ALLOW, [INFO], [PROBE_OK], 2, Decision.ACCEPT, "R7"),
    ("no-checks", ALLOW, [], [], 1, Decision.ACCEPT, "R7"),
]


@pytest.mark.parametrize("authz,checks,probes,tier,expected,rid", [r[1:] for r in ROWS], ids=[r[0] for r in ROWS])
def test_rows(authz, checks, probes, tier, expected, rid):
    decision, reasons = decide(authz, checks, probes, tier)
    assert decision == expected
    assert row(reasons) == rid


def test_every_table_row_is_covered():
    assert {r[-1] for r in ROWS} == {rid for rid, _ in DECISION_TABLE}
    assert dict(DECISION_TABLE) == {r[-1]: r[-2] for r in ROWS}


# Precedence: the stricter row wins whatever else is present.
PRECEDENCE = [
    ("opa-error-beats-deny-and-taint", AuthzResult(allow=False, error="x"), [BLOCK], [PROBE_FAIL], 1, "E1"),
    ("opa-deny-beats-check-error", AuthzResult(allow=False), [CHECK_ERR], [], 1, "R1"),
    ("check-error-beats-taint", ALLOW, [BLOCK, CHECK_ERR], [], 1, "E2"),
    ("taint-beats-probe-fail", ALLOW, [BLOCK], [PROBE_FAIL], 2, "R2"),
    ("taint-beats-escalate", ALLOW, [ESCALATE, BLOCK], [], 1, "R2"),
    ("probe-fail-beats-escalate", ALLOW, [ESCALATE], [PROBE_FAIL], 2, "R3"),
    ("escalate-beats-tier-0", ALLOW, [ESCALATE], [], 0, "R4"),
    ("escalate-beats-tier-4", ALLOW, [ESCALATE], [], 4, "R4"),
    ("probe-fail-beats-tier-3", ALLOW, [OK], [PROBE_FAIL], 3, "R3"),
    ("taint-at-tier-0", ALLOW, [BLOCK], [], 0, "R2"),
]


@pytest.mark.parametrize("authz,checks,probes,tier,rid", [p[1:] for p in PRECEDENCE], ids=[p[0] for p in PRECEDENCE])
def test_precedence(authz, checks, probes, tier, rid):
    decision, reasons = decide(authz, checks, probes, tier)
    assert row(reasons) == rid
    assert decision in BLOCKED


def test_reasons_carry_detail():
    decision, reasons = decide(ALLOW, [PROTECTED, BLOCK], [], 2)
    assert decision == Decision.REJECT
    assert "scope: drift into ci" in reasons and "provenance: tainted params" in reasons


@pytest.mark.parametrize(
    "args",
    [
        (None, [OK], [], 1),  # not an AuthzResult
        (ALLOW, None, [], 1),  # checks not iterable
        (ALLOW, [object()], [], 1),  # garbage check result
        (ALLOW, [OK], [object()], 1),  # garbage probe result
        (ALLOW, [OK], [], "1"),  # tier of the wrong type
    ],
    ids=["authz-none", "checks-none", "check-garbage", "probe-garbage", "tier-str"],
)
def test_any_error_defers(args):
    decision, reasons = decide(*args)
    assert decision == Decision.DEFER
    assert reasons


def test_pure():
    args = (ALLOW, [OK], [PROBE_OK], 2)
    assert decide(*args) == decide(*args)


def test_decide_has_no_contract_parameter():
    """Structural trust boundary: decide() can't see agent_claims because it never gets a contract."""
    import inspect

    assert list(inspect.signature(decide).parameters) == ["authz", "checks", "probes", "tier"]
