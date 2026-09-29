"""Offline probe tests: diff, secret scan, path safety, sandbox command line (docker mocked)."""

import subprocess

import pytest

import av.probes.sandbox as sb
from av.contracts import ContractBuilder
from av.probes import DiffProbe, RunTestsProbe, SecretScanProbe
from av.probes.probes import _inside
from tests.fakes import FakeTaintStore, fake_tier


def build(task, tool, params):
    return ContractBuilder(tier_fn=fake_tier({tool: 2})).build(tool, params, task, FakeTaintStore())


def write(task, content, path="calc/ops.py"):
    return build(task, "write_file", {"path": path, "content": content})


def test_diff_stats_and_no_write(task, workspace):
    before = workspace.snapshot_hashes()
    r = DiffProbe().run(write(task, "def add(a, b):\n    return a - b\n"), workspace)
    assert r.name == "diff" and r.passed and r.error is None
    assert r.details["added"] >= 1 and r.details["removed"] >= 1
    assert "--- a/calc/ops.py" in r.details["diff"]
    assert workspace.snapshot_hashes() == before


def test_diff_new_file_and_delete(task, workspace):
    r = DiffProbe().run(write(task, "x = 1\n", path="calc/new.py"), workspace)
    assert r.details["created"] and r.details["added"] == 1
    r = DiffProbe().run(build(task, "delete_file", {"path": "tests/test_ops.py"}), workspace)
    assert r.details["deleted"] and r.details["removed"] > 0 and r.details["added"] == 0


def test_diff_path_escape_is_error(task, workspace):
    r = DiffProbe().run(write(task, "x", path="../../etc/passwd"), workspace)
    assert r.error and not r.passed


def test_inside_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        _inside(tmp_path, "../x")
    with pytest.raises(ValueError):
        _inside(tmp_path, "/etc/passwd")
    assert _inside(tmp_path, "a/b.py") == (tmp_path / "a/b.py").resolve()


def test_secret_scan_flags_key_without_leaking_it(task, workspace):
    secret = "AKIAIOSFODNN7EXAMPLE"
    r = SecretScanProbe().run(write(task, f'aws_access_key_id = "{secret}"\n'), workspace)
    assert r.name == "secret_scan" and not r.passed and r.error is None
    assert secret not in r.model_dump_json()
    assert r.details["findings"][0]["line"] == 1


def test_secret_scan_clean_and_non_write(task, workspace):
    assert SecretScanProbe().run(write(task, "def f():\n    return 1\n"), workspace).passed
    assert SecretScanProbe().run(build(task, "delete_file", {"path": "x.py"}), workspace).passed


def test_docker_args_are_locked_down(monkeypatch, tmp_path):
    seen = []

    def fake_docker(args, timeout):
        seen.append((args, timeout))
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(sb, "_docker", fake_docker)
    res = sb.run_in_sandbox(tmp_path, ["true"])
    assert res.exit_code == 0
    args, timeout = seen[-1]
    joined = " ".join(args)
    assert timeout == 60
    for flag in ("--rm", "--network none", "--read-only", "--tmpfs /tmp", "--cpus", "--memory", "--cap-drop ALL"):
        assert flag in joined
    assert "-e" not in args and "--env" not in args and "--env-file" not in args
    assert f"{tmp_path}:/work:ro" in joined


def test_sandbox_docker_env_has_no_secrets(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "s3cret")
    monkeypatch.setenv("PATH", "/usr/bin")
    assert "OPENCODE_GO_API_KEY" not in sb._docker_env()


def test_timeout_kills_container_and_reports(monkeypatch, tmp_path):
    calls = []

    def fake_docker(args, timeout):
        calls.append(args)
        if args[0] == "run":
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sb, "_docker", fake_docker)
    assert sb.run_in_sandbox(tmp_path, ["sleep", "999"]).timed_out
    assert calls[-1][:2] == ["rm", "-f"]


def test_run_tests_probe_docker_unavailable_is_error(task, workspace, monkeypatch):
    def boom(*a, **k):
        raise sb.SandboxError("docker is not installed")

    monkeypatch.setattr("av.probes.probes.run_in_sandbox", boom)
    r = RunTestsProbe().run(write(task, "x = 1\n"), workspace)
    assert r.error and not r.passed
