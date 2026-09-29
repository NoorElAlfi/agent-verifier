"""Clients, quota, GPU lock, scenario loading, and the offline guarantees of conftest."""

import json
import os
import socket
from types import SimpleNamespace

import pytest
from filelock import Timeout

import av.clients
from av import quota
from av.clients import HostedClient, RealClientBlocked, hosted, ollama, use_clients
from av.config import data_dir
from av.gpu import gpu_lock
from av.scenarios import list_scenarios, load_proposals, load_scenario
from tests.fakes import FakeHostedClient


# ------------------------------------------------------------------ offline guarantees

def test_injected_fakes_are_returned(fake_clients):
    h, o = fake_clients
    assert hosted() is h and ollama() is o
    assert hosted().chat([{"role": "user", "content": "hi"}]).text == "ok"
    assert len(h.calls) == 1


def test_real_clients_raise_in_tests(monkeypatch):
    monkeypatch.setattr(av.clients, "_hosted_override", None)
    monkeypatch.setattr(av.clients, "_ollama_override", None)
    monkeypatch.setenv("OPENCODE_GO_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "not-a-key")
    with pytest.raises(RealClientBlocked):
        hosted()
    with pytest.raises(RealClientBlocked):
        ollama()
    with pytest.raises(RealClientBlocked):
        HostedClient(base_url="https://example.invalid/v1", api_key="x")


def test_network_is_blocked():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="offline"):
            s.connect(("93.184.216.34", 443))
    finally:
        s.close()


def test_each_test_has_its_own_data_dir(tmp_path):
    assert data_dir() == tmp_path / "av-data"
    assert "OPENCODE_GO_API_KEY" not in os.environ


def test_use_clients_restores():
    outer = hosted()
    inner = FakeHostedClient()
    with use_clients(hosted=inner):
        assert hosted() is inner
    assert hosted() is outer


# ------------------------------------------------------------------ hosted client counting

class _StubCompletions:
    def __init__(self, fail=False):
        self.fail = fail

    def create(self, model, messages, **kw):
        if self.fail:
            raise ConnectionError("upstream down")
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
            choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))],
        )


def _stub_hosted(monkeypatch, fail=False):
    monkeypatch.setattr(av.clients, "BLOCK_REAL_CLIENTS", False)
    c = HostedClient(base_url="https://example.invalid/v1", api_key="x", default_model="m")
    c._client = SimpleNamespace(chat=SimpleNamespace(completions=_StubCompletions(fail)))
    return c


def test_hosted_calls_are_counted(monkeypatch):
    c = _stub_hosted(monkeypatch)
    monkeypatch.setenv("AV_RUN_ID", "run-1")
    r = c.chat([{"role": "user", "content": "ping"}])
    assert r.text == "pong" and r.prompt_tokens == 11
    u = quota.usage()
    assert u["total"] == 1 and u["runs"] == {"run-1": 1} and u["tokens"] == {"prompt": 11, "completion": 7}


def test_failed_hosted_calls_are_still_counted(monkeypatch):
    c = _stub_hosted(monkeypatch, fail=True)
    with pytest.raises(ConnectionError):
        c.chat([{"role": "user", "content": "ping"}])
    assert quota.usage()["total"] == 1


def test_hosted_call_refused_at_cap(monkeypatch):
    c = _stub_hosted(monkeypatch)
    quota.record(quota.POST0_TOTAL_CAP - 1)
    with pytest.raises(quota.QuotaGate):
        c.chat([{"role": "user", "content": "ping"}])
    assert quota.usage()["total"] == quota.POST0_TOTAL_CAP - 1  # refused before calling


# ------------------------------------------------------------------ quota

def test_quota_file_lives_in_data_dir():
    quota.record(2, prompt_tokens=5)
    data = json.loads((data_dir() / "quota.json").read_text())
    assert data["total"] == 2 and sum(data["days"].values()) == 2


def test_post0_cap_is_strictly_below_200():
    quota.record(198, run_id="earlier")
    quota.assert_budget(1)  # 199 total is fine
    with pytest.raises(quota.QuotaGate, match="Post 0"):
        quota.assert_budget(2)


def test_daily_cap(monkeypatch):
    monkeypatch.setenv("AV_PHASE", "post1")
    quota.record(290, run_id="earlier")
    quota.assert_budget(10, approved=10)
    with pytest.raises(quota.QuotaGate, match="daily"):
        quota.assert_budget(11)


def test_large_runs_need_approval(monkeypatch):
    monkeypatch.setenv("AV_PHASE", "post1")
    quota.assert_budget(100)
    with pytest.raises(quota.QuotaGate, match="approval"):
        quota.assert_budget(101)
    quota.assert_budget(150, approved=150)
    with pytest.raises(quota.QuotaGate, match="approval"):
        quota.assert_budget(151, approved=150)
    monkeypatch.setenv("AV_APPROVED_CALLS", "200")
    quota.assert_budget(200)


# ------------------------------------------------------------------ gpu lock

def test_gpu_lock_is_exclusive():
    with gpu_lock():
        assert (data_dir() / ".gpu.lock").exists()
        from filelock import FileLock

        other = FileLock(str(data_dir() / ".gpu.lock"), timeout=0, is_singleton=False, thread_local=False)
        with pytest.raises(Timeout):
            other.acquire()


# ------------------------------------------------------------------ scenarios

def test_example_scenario_loads():
    s = load_scenario("_example")
    assert s.origin == "synthetic"
    assert s.task.scope_globs == ("calc/*.py",)
    assert [p.tool for p in s.proposals] == ["read_file", "write_file", "submit"]
    assert s.workspace.joinpath("calc/ops.py").exists()
    assert "_example" not in list_scenarios() and "_example" in list_scenarios(include_examples=True)


def test_proposals_need_origin_header(tmp_path):
    p = tmp_path / "proposals.jsonl"
    p.write_text('{"tool": "submit", "params": {}}\n')
    with pytest.raises(Exception):
        load_proposals(p)
    p.write_text('{"origin": "invented"}\n')
    with pytest.raises(Exception):
        load_proposals(p)


def test_per_call_checks_cannot_creep_past_approval(monkeypatch):
    monkeypatch.setenv("AV_PHASE", "post1")
    monkeypatch.setenv("AV_RUN_ID", "long-run")
    quota.record(100, run_id="long-run")
    with pytest.raises(quota.QuotaGate, match="approved cap"):
        quota.assert_budget(1)
    monkeypatch.setenv("AV_APPROVED_CALLS", "150")
    quota.assert_budget(1)
