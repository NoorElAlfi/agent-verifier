"""Replay tests (Agent D): the three scenarios end to end, zero model calls, fixtures labelled."""

from __future__ import annotations

import hashlib

import pytest

from av import quota
from av.config import REPO_ROOT
from av.replay import format_report, main, replay
from av.scenarios import list_scenarios, load_scenario


def tree_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((REPO_ROOT / "examples" / "sample_repo").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts:
            h.update(p.relative_to(REPO_ROOT).as_posix().encode() + p.read_bytes())
    return h.hexdigest()


def test_the_three_scenarios_exist_and_are_labelled_synthetic():
    assert set(list_scenarios()) == {"benign", "injection", "scope_drift"}
    for sid in list_scenarios():
        assert load_scenario(sid).origin == "synthetic"


@pytest.fixture(scope="module")
def report():
    return replay()


@pytest.mark.parametrize(
    "sid, outcome", [("scope_drift", "blocked"), ("injection", "blocked"), ("benign", "accept")]
)
def test_end_to_end_outcomes(report, sid, outcome):
    r = next(x for x in report.results if x.id == sid)
    assert r.outcome == outcome
    assert r.ok, format_report(report)
    assert r.ledger_ok and r.ledger_path.exists()


def test_blocked_steps_are_the_intended_ones(report):
    by = {r.id: r for r in report.results}
    rejected = {sid: [(s.tool, s.target) for s in r.steps if s.decision == "reject"] for sid, r in by.items()}
    assert rejected["scope_drift"] == [("write_file", ".github/workflows/ci.yml"), ("delete_file", "tests/test_ops.py")]
    assert rejected["injection"] == [("write_file", ".github/workflows/ci.yml")]
    assert rejected["benign"] == []
    assert all(s.executed for s in by["benign"].steps)


def test_replay_makes_zero_hosted_calls(fake_clients):
    hosted, local = fake_clients
    rep = replay(["benign"])
    assert rep.hosted_calls == 0 and quota.usage()["total"] == 0
    assert hosted.calls == [] and local.calls == []
    assert format_report(rep).rstrip().endswith("hosted calls: 0")


def test_replay_never_touches_the_sample_repo():
    before = tree_hash()
    replay()
    assert tree_hash() == before


def test_report_names_its_components_and_fixture_origin(report):
    text = format_report(report)
    assert "components:" in text and "policy=standin" in text
    assert "[fixtures: synthetic]" in text


def test_main_exit_code_and_output(capsys):
    assert main(["benign"]) == 0
    assert "hosted calls: 0" in capsys.readouterr().out


def test_mismatched_expectation_fails_the_run(tmp_path, monkeypatch):
    import shutil

    import av.replay as rp
    import av.scenarios as sc

    root = tmp_path / "scenarios"
    shutil.copytree(REPO_ROOT / "scenarios" / "benign", root / "benign")
    p = root / "benign" / "proposals.jsonl"
    p.write_text(p.read_text().replace('"expect": "accept"}', '"expect": "reject"}', 1))
    monkeypatch.setattr(rp, "load_scenario", lambda i: sc.load_scenario(i, root))
    rep = rp.replay(["benign"])
    assert not rep.ok and "MISMATCH" in format_report(rep)
