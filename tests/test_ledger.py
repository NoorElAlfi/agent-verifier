"""SqliteLedger: hash chain, tamper detection (M8), authorization as its own field (M7)."""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from av.contracts import AuthzResult, CheckResult, ContractBuilder, Decision, DecisionRecord
from av.ledger import SqliteLedger
from tests.fakes import FakeTaintStore


def rec(task, i=0, **kw):
    c = ContractBuilder().build(
        "write_file", {"path": "calc/ops.py", "content": f"v{i}\n"}, task, FakeTaintStore(),
        agent_claims={"in_scope": True},
    )
    base = dict(
        task_id=task.task_id,
        contract=c,
        contract_hash=c.hash(),
        authorization=AuthzResult(allow=True),
        verification=(CheckResult(name="scope", passed=True),),
        final_decision=Decision.ACCEPT,
    )
    base.update(kw)
    return DecisionRecord(**base)


@pytest.fixture
def ledger(tmp_path):
    calls = iter(range(0, 1000))
    return SqliteLedger(tmp_path / "l.db", hosted_calls_fn=lambda: next(calls))


def test_chain_and_roundtrip(ledger, task):
    records = [rec(task, i) for i in range(3)]
    hashes = [ledger.append(r) for r in records]
    assert len(set(hashes)) == 3 and ledger.verify()
    assert ledger.records() == records
    rows = ledger.rows()
    assert rows[0][2] == "" and rows[1][2] == hashes[0] and rows[2][2] == hashes[1]
    assert [r[1] for r in rows] == [0, 1, 2]  # hosted calls so far, per row


def test_default_counts_hosted_calls_from_quota(tmp_path, task):
    from av.quota import record

    record(prompt_tokens=1, completion_tokens=1)
    led = SqliteLedger(tmp_path / "q.db")
    led.append(rec(task))
    assert led.rows()[0][1] == 1


def test_empty_ledger_verifies(ledger):
    assert ledger.verify()


def test_reopen_continues_chain(tmp_path, task):
    p = tmp_path / "r.db"
    SqliteLedger(p, lambda: 0).append(rec(task, 1))
    b = SqliteLedger(p, lambda: 0)
    b.append(rec(task, 2))
    assert b.verify() and len(b.rows()) == 2


def _sql(path, stmt, *args):
    con = sqlite3.connect(path)
    con.execute(stmt, args)
    con.commit()
    con.close()


def test_m8_edited_row_fails_verify(ledger, task):
    for i in range(3):
        ledger.append(rec(task, i))
    row = ledger.rows()[1][3]
    tampered = row.replace('"final_decision":"accept"', '"final_decision":"reject"')
    assert tampered != row
    _sql(ledger.path, "UPDATE ledger SET row_json = ? WHERE seq = 2", tampered)
    assert not ledger.verify()
    assert any("row 2" in p for p in ledger.problems())


def test_m8_edited_hosted_calls_fails_verify(ledger, task):
    ledger.append(rec(task))
    _sql(ledger.path, "UPDATE ledger SET hosted_calls = 0 WHERE seq = 1")
    assert ledger.verify()  # 0 already; change to something else
    _sql(ledger.path, "UPDATE ledger SET hosted_calls = 5 WHERE seq = 1")
    assert not ledger.verify()


def test_m8_deleted_row_fails_verify(ledger, task):
    for i in range(3):
        ledger.append(rec(task, i))
    _sql(ledger.path, "DELETE FROM ledger WHERE seq = 2")
    assert not ledger.verify()


def test_m8_rehashed_row_still_breaks_the_chain(ledger, task):
    """An attacker who recomputes one row's hash still breaks the next row's prev_hash."""
    from av.contracts import sha256_hex
    from av.ledger import row_bytes

    for i in range(3):
        ledger.append(rec(task, i))
    seq, calls, prev, rj, _ = ledger.rows()[0]
    new_rj = rj.replace('"final_decision":"accept"', '"final_decision":"reject"')
    _sql(ledger.path, "UPDATE ledger SET row_json = ?, row_hash = ? WHERE seq = 1",
         new_rj, sha256_hex(prev.encode() + row_bytes(seq, calls, new_rj)))
    assert not ledger.verify()


def test_cli_verify_exit_codes(ledger, task):
    ledger.append(rec(task))
    cmd = [sys.executable, "-m", "av.ledger", "verify", ledger.path]
    ok = subprocess.run(cmd, capture_output=True, text=True)
    assert ok.returncode == 0 and "ledger ok" in ok.stdout
    _sql(ledger.path, "UPDATE ledger SET row_json = replace(row_json, 'v0', 'v9') WHERE seq = 1")
    bad = subprocess.run(cmd, capture_output=True, text=True)
    assert bad.returncode == 1 and "INVALID" in bad.stdout
    missing = subprocess.run([*cmd[:-1], ledger.path + ".nope"], capture_output=True, text=True)
    assert missing.returncode != 0


def test_m7_authorization_is_a_separate_field(ledger, task):
    """A record whose authorization denied but verification passed (and vice versa) is stored
    with both fields distinct; the decision is recorded separately."""
    r = rec(task, authorization=AuthzResult(allow=False, reasons=("denied",)),
            final_decision=Decision.REJECT)
    ledger.append(r)
    back = ledger.records()[0]
    assert back.authorization.allow is False and back.authorization.reasons == ("denied",)
    assert back.verification[0].passed is True
    assert back.final_decision == Decision.REJECT
    import json

    row = json.loads(ledger.rows()[0][3])
    assert {"authorization", "verification", "final_decision"} <= set(row)


def test_agent_claims_are_recorded_but_only_in_the_claims_field(ledger, task):
    ledger.append(rec(task))
    assert ledger.records()[0].contract.agent_claims == {"in_scope": True}


def test_no_update_or_delete_statements_in_ledger_source():
    src = (Path(__file__).parent.parent / "av" / "ledger.py").read_text()
    sql = " ".join(re.findall(r'"([^"\n]*)"', src)).upper()
    assert "UPDATE " not in sql and "DELETE " not in sql
