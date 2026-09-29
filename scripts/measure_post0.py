"""Wave 3 L: Post 0 measurements and live-fixture extraction.

    uv run python scripts/measure_post0.py episode <run-id> <scenario>     # print an episode's proposals + decisions
    uv run python scripts/measure_post0.py record <run-id> <scenario> ...  # (see save_recorded) write proposals.jsonl
    uv run python scripts/measure_post0.py report                          # write reports/post0-measurements.md

`report` makes NO hosted calls; it reads AV_DATA_DIR (quota.json, episodes/), the repo, docker
and the disk. M1 clones the repo fresh into /tmp/fresh and times `make demo` (replay).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from av import quota
from av.config import REPO_ROOT, data_dir

REPORT = REPO_ROOT / "reports" / "post0-measurements.md"
BUDGET_SPEC = (3000, 6000)  # spec: Post 1 hosted calls
DAILY = 300
POST1_EPISODES = 320


def _tool_pairs(episode_json: Path):
    """[(tool, params, tool-result text)] in order, from the Inspect log of one episode."""
    from inspect_ai.log import read_eval_log

    rec = json.loads(episode_json.read_text())
    log = read_eval_log(rec["inspect_log"])
    out, results = [], {}
    msgs = log.samples[0].messages if log.samples else []
    for m in msgs:
        if m.role == "tool":
            txt = m.content if isinstance(m.content, str) else "".join(getattr(c, "text", "") for c in m.content)
            results[m.tool_call_id] = txt
    for m in msgs:
        if m.role == "assistant":
            for t in m.tool_calls or []:
                out.append((t.function, dict(t.arguments), results.get(t.id, "")))
    return rec, out


def _decision(text: str) -> str | None:
    for ln in text.splitlines():
        if ln.startswith("decision:"):
            return ln.split(":", 1)[1].strip()
    return None


def episode_summary(run_id: str, scenario: str) -> list[dict]:
    f = data_dir() / "episodes" / run_id / f"{scenario}.json"
    rec, pairs = _tool_pairs(f)
    rows = [{"tool": t, "params": p, "expect": _decision(r)} for t, p, r in pairs]
    return rows


def save_recorded(run_id: str, scenario: str, model: str, note: str, outcome: str) -> None:
    rows = episode_summary(run_id, scenario)
    head = {
        "origin": "recorded",
        "scenario_outcome": outcome,
        "model": model,
        "recorded_on": datetime.now(UTC).date().isoformat(),
        "run_id": run_id,
        "note": note,
    }
    lines = [json.dumps(head)]
    for r in rows:
        line = {"tool": r["tool"], "params": r["params"]}
        if r["expect"]:
            line["expect"] = r["expect"]
        lines.append(json.dumps(line))
    (REPO_ROOT / "scenarios" / scenario / "proposals.jsonl").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------ report


def _sh(cmd: str, cwd: Path | None = None, timeout: int = 900) -> tuple[int, str, float]:
    t = time.time()
    p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr), time.time() - t


def _du(p: Path) -> str:
    if not p.exists():
        return "absent"
    return _sh(f"du -shL {p} | cut -f1")[1].strip()


def _episodes(prefix: tuple[str, ...]) -> list[dict]:
    out = []
    for f in sorted((data_dir() / "episodes").glob("*/*.json")):
        if f.parent.name.startswith(prefix):
            out.append(json.loads(f.read_text()))
    return out


def _log_stats(path: str) -> tuple[dict, str]:
    """(tokens, wall seconds) of one episode from its Inspect log."""
    from inspect_ai.log import read_eval_log

    log = read_eval_log(path)
    usage = (log.stats.model_usage if log.stats else {}) or {}
    tk = {"prompt": sum(u.input_tokens + (u.input_tokens_cache_read or 0) for u in usage.values()), "completion": sum(u.output_tokens for u in usage.values())}
    try:
        wall = f"{(datetime.fromisoformat(str(log.stats.completed_at)) - datetime.fromisoformat(str(log.stats.started_at))).total_seconds():.0f}"
    except Exception:
        wall = "n/a"
    return tk, wall


def build_report() -> str:
    u = quota.usage()
    total = u["total"]
    # M11 per episode: calls and tokens from the per-run counters
    lines = ["# Post 0 measurements", "", f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} by scripts/measure_post0.py. "
             "Every number below comes from AV_DATA_DIR/quota.json, AV_DATA_DIR/episodes, or a command run by the script.", ""]

    # M1
    fresh = Path("/tmp/fresh")
    shutil.rmtree(fresh, ignore_errors=True)
    rc, out, t_clone = _sh(f"git clone -q {REPO_ROOT} {fresh}")
    m1 = "clone failed"
    if rc == 0:
        # No .env copy and LIVE forced off: the fresh-clone demo is replay only (no credentials, no hosted calls).
        rc1, o1, t_sync = _sh("uv sync -q", cwd=fresh)
        (fresh / "bin").mkdir(exist_ok=True)
        if (REPO_ROOT / "bin" / "opa").exists() and not (fresh / "bin" / "opa").exists():
            (fresh / "bin" / "opa").symlink_to(REPO_ROOT / "bin" / "opa")
        rc2, o2, t_demo = _sh("env -u LIVE make demo LIVE=0", cwd=fresh)
        calls_line = next((ln for ln in o2.splitlines() if "hosted calls" in ln), "no 'hosted calls' line")
        m1 = (f"`make demo` (replay) on a fresh clone at /tmp/fresh: **{t_demo:.1f} s** (exit {rc2}); "
              f"`uv sync` took {t_sync:.1f} s and clone {t_clone:.1f} s (not part of the demo time); "
              f"demo output: `{calls_line.strip()}`. Excludes the one-time Docker probe image build.")
    lines += ["## M1: `make demo` on a fresh clone", "", m1, ""]

    # M10
    _, df, _ = _sh("docker system df")
    _, pimg, _ = _sh("docker images av-probe:latest --format '{{.Repository}}:{{.Tag}} {{.Size}}'")
    lines += ["## M10: disk footprint and hosted calls", "", "```", df.strip(), "```", "",
              f"- probe image: `{pimg.strip()}`",
              f"- `.venv`: {_du(REPO_ROOT / '.venv')}; `bin/`: {_du(REPO_ROOT / 'bin')}; AV_DATA_DIR: {_du(data_dir())}",
              f"- **total hosted calls so far: {total}** (Post 0 cap 200); tokens: {u['tokens']['prompt']} prompt, {u['tokens']['completion']} completion",
              f"- by day: {u['days']}", ""]

    # M11
    eps = _episodes(("rec-", "trial-c2"))  # trial-c (failed, MissingSessionID) is excluded on purpose
    lines += ["## M11: calls and tokens per live episode", "",
              "| run | scenario | status | hosted calls | prompt tok (incl. cached) | completion tok | wall s |", "|---|---|---|---|---|---|---|"]
    ok = [e for e in eps if e["status"] == "success"]
    for e in eps:
        run = u["runs"].get(e["run_id"], "?")
        tk, wall = _log_stats(e["inspect_log"])
        lines.append(f"| {e['run_id']} | {e['scenario']} | {e['status']} | {e['hosted_calls']} | {tk.get('prompt','n/a')} | {tk.get('completion','n/a')} | {wall} |")
    lines.append("")
    mean = sum(e["hosted_calls"] for e in ok) / len(ok) if ok else float("nan")
    lo, hi = BUDGET_SPEC
    proj = POST1_EPISODES * mean
    over = proj > hi * 1.25
    lines += ["## Post 1 budget projection", "",
              f"- measured mean hosted calls per successful live episode: **{mean:.2f}** (n={len(ok)}; these are three small scenarios, not Post 1 tasks, so treat as a lower bound)",
              f"- {POST1_EPISODES} episodes x {mean:.2f} = **{proj:.0f} calls**; at {DAILY}/day that is **{proj / DAILY:.1f} days**",
              f"- spec range for Post 1: {lo}-{hi} calls. Projection is {'MORE than 25% over the top of the range (> ' + str(int(hi*1.25)) + '): the owner must re-approve' if over else 'within 25% of the range (limit ' + str(int(hi*1.25)) + ')'}"
              + (f"; it is {'below' if proj < lo else 'inside'} the range." if not over else "."), ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "report"
    if cmd == "episode":
        for r in episode_summary(argv[1], argv[2]):
            print(json.dumps(r)[:400])
    elif cmd == "record":
        save_recorded(argv[1], argv[2], argv[3], argv[4], argv[5])
    elif cmd == "report":
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(build_report())
        print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
