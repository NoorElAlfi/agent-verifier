"""Hosted-call accounting and caps (CLAUDE.md rule 7). OpenCode Go is shared with the owner's
personal use, so every hosted call is counted here, via av.clients.

The counter is `AV_DATA_DIR/quota.json` (shared by every worktree), guarded by a file lock.
Check a run's standing with `uv run python -m av.quota`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock

from av.config import data_dir

POST0_TOTAL_CAP = 200
"""Post 0: fewer than 200 hosted calls in total (so at most 199)."""
DAILY_CAP = 300
"""Post 1: at most 300 hosted calls per (UTC) day. Applies in every phase."""
APPROVAL_THRESHOLD = 100
"""A planned run of more than this many calls needs a 1-episode trial and owner approval."""


class QuotaGate(RuntimeError):
    """Raised instead of making a hosted call that would break a cap or skip an approval."""


def _path() -> Path:
    return data_dir() / "quota.json"


def _lock() -> FileLock:
    return FileLock(str(data_dir() / "quota.json.lock"), timeout=30)


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _run_id() -> str:
    return os.environ.get("AV_RUN_ID", "adhoc")


def _phase() -> str:
    return os.environ.get("AV_PHASE", "post0")


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {"total": 0, "days": {}, "runs": {}, "tokens": {"prompt": 0, "completion": 0}}
    return json.loads(p.read_text())


def usage() -> dict[str, Any]:
    """{"total", "days": {date: n}, "runs": {run_id: n}, "tokens": {"prompt", "completion"}}."""
    with _lock():
        return _load()


def record(n: int = 1, *, prompt_tokens: int = 0, completion_tokens: int = 0, run_id: str | None = None) -> None:
    """Count n hosted calls (made or attempted) against the total, today and the run."""
    with _lock():
        data = _load()
        run = run_id or _run_id()
        data["total"] += n
        data["days"][_today()] = data["days"].get(_today(), 0) + n
        data["runs"][run] = data["runs"].get(run, 0) + n
        data["tokens"]["prompt"] += prompt_tokens
        data["tokens"]["completion"] += completion_tokens
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(_path())


def approved_cap() -> int | None:
    """An owner-approved call cap for the current run, from AV_APPROVED_CALLS, if any."""
    raw = os.environ.get("AV_APPROVED_CALLS")
    return int(raw) if raw else None


def assert_budget(n: int = 1, *, approved: int | None = None) -> None:
    """Raise QuotaGate unless n more hosted calls fit every cap.

    - n > APPROVAL_THRESHOLD needs `approved` (or AV_APPROVED_CALLS) >= n;
    - the same holds for the current run's running total (AV_RUN_ID), so per-call checks
      can't creep past the approval gate either;
    - today's count + n <= DAILY_CAP;
    - in phase post0 (AV_PHASE, default): total + n < POST0_TOTAL_CAP.
    Call with the planned size before a run, and with n=1 before every call (av.clients does).
    Check and record take the lock separately, so parallel runs can overshoot a cap by a few
    calls; acceptable at this scale.
    """
    cap = approved if approved is not None else approved_cap()
    if n > APPROVAL_THRESHOLD and (cap is None or n > cap):
        raise QuotaGate(
            f"a run of {n} hosted calls needs owner approval: do a 1-episode trial, write calls and "
            f"tokens per episode and the projected total to your progress file, then stop"
        )
    data = usage()
    run_total = data["runs"].get(_run_id(), 0) + n
    if run_total > APPROVAL_THRESHOLD and (cap is None or run_total > cap):
        raise QuotaGate(
            f"run {_run_id()!r} would reach {run_total} hosted calls (> {APPROVAL_THRESHOLD}) without "
            f"an approved cap covering it (AV_APPROVED_CALLS); do a 1-episode trial and ask the owner"
        )
    today = data["days"].get(_today(), 0)
    if today + n > DAILY_CAP:
        raise QuotaGate(f"daily cap: {today} used today + {n} > {DAILY_CAP}")
    if _phase() == "post0" and data["total"] + n >= POST0_TOTAL_CAP:
        raise QuotaGate(f"Post 0 cap: {data['total']} used + {n} would reach {POST0_TOTAL_CAP}")


if __name__ == "__main__":
    print(json.dumps(usage(), indent=2, sort_keys=True))
