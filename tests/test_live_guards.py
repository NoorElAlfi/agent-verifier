"""Wave 3 L (owner-approved): hosted session header, and fail-loud on an empty model reply."""

from __future__ import annotations

import av.clients
from av.clients import HostedClient, use_clients
from tests.test_gateway import ScriptedHosted, completion


def test_hosted_client_sends_session_header_from_run_id(monkeypatch):
    monkeypatch.setattr(av.clients, "BLOCK_REAL_CLIENTS", False)
    monkeypatch.setenv("AV_RUN_ID", "my-run")
    c = HostedClient(base_url="http://localhost:1/v1", api_key="k")
    assert c._client.default_headers["x-opencode-session"] == "my-run"
    monkeypatch.delenv("AV_RUN_ID")
    c = HostedClient(base_url="http://localhost:1/v1", api_key="k")
    assert c._client.default_headers["x-opencode-session"] == "av"


def test_empty_model_reply_is_an_error_not_success_and_is_retried(tmp_path):
    from av.agent.react import run_episode

    client = ScriptedHosted([completion(text="")])
    with use_clients(hosted=client):
        rec = run_episode("benign", "empty-run", model="fake-model", max_model_calls=5)
    assert rec["status"] == "error", rec
    # an errored episode file does not count as done: a re-run tries again
    client2 = ScriptedHosted([completion(tool_calls=[("submit", {"summary": "x"})]), completion(text="ok")])
    with use_clients(hosted=client2):
        rec2 = run_episode("benign", "empty-run", model="fake-model", max_model_calls=5)
    assert rec2["status"] == "success" and client2.calls
