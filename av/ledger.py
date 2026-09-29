"""SqliteLedger: append-only, hash-chained decision log (spec M7/M8).

row_hash = sha256(prev_hash + canonical row JSON), where the row JSON is
{"seq", "hosted_calls", "record"} (canonical_json). prev_hash of the first row is "". Each row
records the hosted-call total at append time (from av.quota by default). The code issues only
INSERT and SELECT statements; there is no UPDATE or DELETE anywhere.

Verify a ledger: `uv run python -m av.ledger verify <ledger.db>` (exit 0 ok, 1 mismatch).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

from av.contracts import DecisionRecord, canonical_json, sha256_hex

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    seq          INTEGER PRIMARY KEY,
    record_id    TEXT NOT NULL,
    hosted_calls INTEGER NOT NULL,
    prev_hash    TEXT NOT NULL,
    row_json     TEXT NOT NULL,
    row_hash     TEXT NOT NULL
)
"""


def _default_hosted_calls() -> int:
    from av.quota import usage

    return int(usage()["total"])


def row_bytes(seq: int, hosted_calls: int, record_json: str) -> bytes:
    """Canonical bytes of one row; the record is embedded as parsed JSON, not as a string."""
    return canonical_json({"seq": seq, "hosted_calls": hosted_calls, "record": json.loads(record_json)})


class SqliteLedger:
    def __init__(self, path: str | Path, hosted_calls_fn: Callable[[], int] = _default_hosted_calls):
        self.path = str(path)
        self.hosted_calls_fn = hosted_calls_fn
        con = self._connect()
        try:
            con.execute(_SCHEMA)
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def append(self, record: DecisionRecord) -> str:
        calls = int(self.hosted_calls_fn())
        record_json = canonical_json(record).decode("utf-8")
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            last = con.execute("SELECT seq, row_hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (last[0] + 1, last[1]) if last else (1, "")
            h = sha256_hex(prev.encode() + row_bytes(seq, calls, record_json))
            con.execute(
                "INSERT INTO ledger (seq, record_id, hosted_calls, prev_hash, row_json, row_hash)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (seq, record.record_id, calls, prev, record_json, h),
            )
            con.execute("COMMIT")
            return h
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def rows(self) -> list[tuple[int, int, str, str, str]]:
        """(seq, hosted_calls, prev_hash, row_json, row_hash) in order."""
        con = self._connect()
        try:
            return con.execute(
                "SELECT seq, hosted_calls, prev_hash, row_json, row_hash FROM ledger ORDER BY seq"
            ).fetchall()
        finally:
            con.close()

    def records(self) -> list[DecisionRecord]:
        return [DecisionRecord.model_validate_json(r[3]) for r in self.rows()]

    def problems(self) -> list[str]:
        """Every mismatch found walking the chain; empty means the ledger verifies."""
        try:
            rows = self.rows()
        except sqlite3.Error as exc:
            return [f"cannot read ledger: {exc}"]
        out: list[str] = []
        prev = ""
        expected_seq = 1
        for seq, calls, p, rj, h in rows:
            if seq != expected_seq:
                out.append(f"row {seq}: expected seq {expected_seq} (row missing or reordered)")
            if p != prev:
                out.append(f"row {seq}: prev_hash does not match the previous row")
            try:
                good: str | None = sha256_hex(p.encode() + row_bytes(seq, calls, rj))
            except Exception as exc:
                out.append(f"row {seq}: unreadable row json ({exc})")
                good = None
            if good is not None and good != h:
                out.append(f"row {seq}: row_hash mismatch (row was edited)")
            prev = h
            expected_seq = seq + 1
        return out

    def verify(self) -> bool:
        return not self.problems()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "verify":
        print("usage: python -m av.ledger verify <ledger.db>", file=sys.stderr)
        return 2
    if not Path(args[1]).is_file():
        print(f"no such ledger: {args[1]}", file=sys.stderr)
        return 2
    ledger = SqliteLedger(args[1], hosted_calls_fn=lambda: 0)
    problems = ledger.problems()
    if problems:
        print("LEDGER INVALID")
        for p in problems:
            print(" ", p)
        return 1
    print(f"ledger ok: {len(ledger.rows())} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
