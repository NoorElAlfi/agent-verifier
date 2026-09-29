"""OPA authorization: allowlist, path denylist, size limit, fail-closed on OPA problems."""

import shutil
import stat

import pytest

from av.contracts import ContractBuilder, Decision, TaskDefinition
from av.decide import decide
from av.policy import OpaPolicyEngine
from tests.fakes import FakeTaintStore

pytestmark = pytest.mark.skipif(
    not (OpaPolicyEngine().opa_path and __import__("os").path.exists(OpaPolicyEngine().opa_path)),
    reason="bin/opa missing (run `make setup`)",
)


def build(task, tool, **params):
    return ContractBuilder().build(tool, params, task, FakeTaintStore())


@pytest.fixture
def engine():
    return OpaPolicyEngine()


def test_benign_write_allowed(engine, task):
    res = engine.authorize(build(task, "write_file", path="calc/ops.py", content="x = 1\n"), task)
    assert res.allow and res.error is None and res.reasons == ()


@pytest.mark.parametrize(
    "tool,params",
    [
        ("read_file", {"path": "calc/ops.py"}),
        ("list_files", {"path": "."}),
        ("run_tests", {}),
    ],
)
def test_benign_reads_allowed(engine, task, tool, params):
    assert engine.authorize(build(task, tool, **params), task).allow


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../secrets.txt",
        "calc/../../x",
        "calc/..",
        ".git/config",
        "./.git/hooks/pre-commit",
        "sub/.GIT/config",
        "C:/Windows/x",
        "..\\x",
        "~/.ssh/id_rsa",
        "",
    ],
)
@pytest.mark.parametrize("tool", ["write_file", "read_file", "delete_file"])
def test_denylisted_paths(engine, task, tool, path):
    params = {"path": path, "content": "x"} if tool == "write_file" else {"path": path}
    res = engine.authorize(build(task, tool, **params), task)
    assert not res.allow and res.error is None and res.reasons
    assert decide(res, [], [], 1)[0] == Decision.REJECT


def test_tool_allowlist_is_per_task(engine, task):
    c = build(task, "delete_file", path="calc/ops.py")  # built under a permissive task
    narrow = task.model_copy(update={"allowed_tools": ("read_file", "submit")})
    res = engine.authorize(c, narrow)
    assert not res.allow and "not allowed" in res.reasons[0]


def test_max_file_size(task):
    eng = OpaPolicyEngine(max_file_bytes=100)
    ok = eng.authorize(build(task, "write_file", path="a.py", content="x" * 100), task)
    big = eng.authorize(build(task, "write_file", path="a.py", content="x" * 101), task)
    assert ok.allow and not big.allow and "too large" in big.reasons[0]
    # multi-byte characters count as bytes, not characters
    wide = eng.authorize(build(task, "write_file", path="a.py", content="é" * 60), task)
    assert not wide.allow


def test_authorization_ignores_agent_claims(engine, task):
    c = ContractBuilder().build(
        "write_file", {"path": "../x", "content": "y"}, task, FakeTaintStore(),
        agent_claims={"in_scope": True, "allowed": True, "path": "ok.py"},
    )
    assert not engine.authorize(c, task).allow


def test_does_not_judge_scope_drift(engine, task):
    """Authorization is 'may it?': an out-of-scope but permitted path is allowed here (Agent B's
    ScopeDriftCheck handles 'should it?')."""
    res = engine.authorize(build(task, "write_file", path=".github/workflows/ci.yml", content="x"), task)
    assert res.allow


def test_opa_timeout_defers(task):
    eng = OpaPolicyEngine(timeout=0.0001)
    res = eng.authorize(build(task, "read_file", path="calc/ops.py"), task)
    assert not res.allow and "timed out" in res.error
    assert decide(res, [], [], 1)[0] == Decision.DEFER


def test_missing_binary_defers(task, tmp_path):
    res = OpaPolicyEngine(opa_path=tmp_path / "nope").authorize(build(task, "read_file", path="a"), task)
    assert res.error and not res.allow
    assert decide(res, [], [], 1)[0] == Decision.DEFER


def test_opa_nonzero_exit_defers(task, tmp_path):
    bad = tmp_path / "policies"
    bad.mkdir()
    (bad / "broken.rego").write_text("package av.authz\nthis is not rego\n")
    res = OpaPolicyEngine(policy_dir=bad).authorize(build(task, "read_file", path="a"), task)
    assert res.error and "exited" in res.error
    assert decide(res, [], [], 1)[0] == Decision.DEFER


def test_undefined_result_defers(task, tmp_path):
    empty = tmp_path / "policies"
    empty.mkdir()
    (empty / "other.rego").write_text("package other\nx := 1\n")
    res = OpaPolicyEngine(policy_dir=empty).authorize(build(task, "read_file", path="a"), task)
    assert res.error and not res.allow


def test_garbage_output_defers(task, tmp_path):
    fake = tmp_path / "opa"
    fake.write_text("#!/bin/sh\necho '{\"result\": []}'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    res = OpaPolicyEngine(opa_path=fake).authorize(build(task, "read_file", path="a"), task)
    assert res.error and "unusable" in res.error
    assert shutil.which("sh")  # sanity: the stub really ran


def test_submit_is_allowed(engine, task):
    assert engine.authorize(build(task, "submit", summary="done"), task).allow
    assert engine.authorize(build(task, "submit"), task).allow


def test_non_string_path_is_denied(engine, task):
    c = build(task, "read_file", path="a")
    evil = c.model_copy(update={"params": {"path": 5}, "target": "a"})  # bypasses the builder
    assert not engine.authorize(evil, task).allow
