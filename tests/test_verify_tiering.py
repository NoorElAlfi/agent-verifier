"""assign_tier, the probe catalog, and the path helpers behind them."""

import pytest

from av.contracts import TOOLS, TaskDefinition
from av.verify import PROBE_CATALOG, assign_tier, tier_for
from av.verify import paths
from tests.test_verify_helpers import build

TASK = TaskDefinition(task_id="t", objective="fix calc", scope_globs=("calc/*.py", "scripts/*.sh", "tests/*.py"))
CI_TASK = TaskDefinition(
    task_id="t-ci",
    objective="bump python in CI",
    scope_globs=(".github/workflows/*.yml", "pyproject.toml", "tests/*.py"),
    declared_protected=("ci", "dependencies", "tests"),
)


@pytest.mark.parametrize(
    "tool,params,task,tier",
    [
        ("list_files", {}, TASK, 0),
        ("read_file", {"path": ".github/workflows/ci.yml"}, TASK, 0),
        ("run_tests", {}, TASK, 0),
        ("submit", {"summary": "done"}, TASK, 0),
        ("write_file", {"path": "calc/ops.py", "content": "x"}, TASK, 1),
        ("delete_file", {"path": "calc/ops.py"}, TASK, 3),
        ("write_file", {"path": "tests/test_ops.py", "content": "x"}, TASK, 2),
        ("write_file", {"path": "scripts/run.sh", "content": "x"}, TASK, 2),
        ("write_file", {"path": "calc/tool.py", "content": "#!/usr/bin/env python\n"}, TASK, 2),
        ("write_file", {"path": "docs/readme.md", "content": "x"}, TASK, 3),
        ("write_file", {"path": ".github/workflows/ci.yml", "content": "x"}, TASK, 4),
        ("delete_file", {"path": "tests/test_ops.py"}, TASK, 4),
        ("write_file", {"path": "pyproject.toml", "content": "x"}, TASK, 4),
        ("write_file", {"path": ".env", "content": "x"}, TASK, 4),
        ("write_file", {"path": "tests/conftest.py", "content": "x"}, TASK, 4),
        ("write_file", {"path": "../outside.py", "content": "x"}, TASK, 4),
        ("write_file", {"path": ".git/hooks/pre-commit", "content": "x"}, TASK, 4),
        ("write_file", {"path": ".github/workflows/ci.yml", "content": "x"}, CI_TASK, 3),
        ("write_file", {"path": "pyproject.toml", "content": "x"}, CI_TASK, 3),
        ("delete_file", {"path": ".github/workflows/ci.yml"}, CI_TASK, 4),
        ("delete_file", {"path": "tests/test_ops.py"}, CI_TASK, 3),
    ],
)
def test_tier_table(tool, params, task, tier):
    assert assign_tier(build(task, tool, params), task) == tier


def test_builder_uses_assign_tier_and_ignores_claims():
    c = build(TASK, "write_file", {"path": ".github/workflows/ci.yml", "content": "x"}, claims={"risk_tier": 0, "in_scope": True})
    assert c.risk_tier == 4 and c.derived_scope_ok is False


def test_every_tier_has_a_catalog_entry_and_reads_run_no_probes():
    assert set(PROBE_CATALOG) == {0, 1, 2, 3, 4}
    assert PROBE_CATALOG[0] == ()
    assert "run_tests" in PROBE_CATALOG[2] and "run_tests" not in PROBE_CATALOG[1]
    for t in range(1, 5):  # a higher tier never runs fewer probes
        assert set(PROBE_CATALOG[t - 1]) <= set(PROBE_CATALOG[t])


def test_every_tool_gets_a_tier_and_unknown_is_4():
    for tool in TOOLS:
        assert 0 <= tier_for(tool, "calc/ops.py", TASK)[0] <= 4
    assert tier_for("shell", "x", TASK)[0] == 4


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("calc/ops.py", "calc/ops.py"),
        ("./calc//ops.py", "calc/ops.py"),
        ("calc/../.github/workflows/x.yml", ".github/workflows/x.yml"),
        ("../x", None),
        ("calc/../../x", None),
        ("/etc/passwd", None),
        ("~/x", None),
        ("C:/x", None),
        ("calc\\ops.py", None),
        ("a\x00b", None),
        (".", None),
        ("", None),
        (".git/config", None),
        ("sub/.GIT/hooks/x", None),
        (".gitignore", ".gitignore"),
    ],
)
def test_lexical(raw, expect):
    assert paths.lexical(raw).path == expect


@pytest.mark.parametrize(
    "path,cls",
    [
        (".github/workflows/ci.yml", "ci"),
        (".GitHub/Workflows/CI.yml", "ci"),
        (".github./workflows/ci.yml", "ci"),
        (".git\u200bhub/workflows/ci.yml", "ci"),
        ("\uff0egithub/workflows/ci.yml", "ci"),  # fullwidth full stop, NFKC -> "."
        (".gitlab-ci.yml", "ci"),
        ("tox.ini", "ci"),
        ("pyproject.toml", "dependencies"),
        ("PyProject.TOML", "dependencies"),
        ("requirements-dev.txt", "dependencies"),
        ("uv.lock", "dependencies"),
        ("sub/package.json", "dependencies"),
        (".env", "secrets"),
        (".env.production", "secrets"),
        ("deploy/id_rsa", "secrets"),
        ("config/client_secret.json", "secrets"),
        ("tests/test_ops.py", "tests"),
        ("pkg/ops_test.py", "tests"),
        ("conftest.py", "tests"),
    ],
)
def test_protected_classes(path, cls):
    assert cls in paths.protected_classes(path)


@pytest.mark.parametrize("path", ["calc/ops.py", "README.md", "docs/secrets-management.md", "calc/secret_math.py"])
def test_ordinary_paths_are_not_protected(path):
    assert paths.protected_classes(path) == frozenset()


@pytest.mark.parametrize(
    "path,glob,ok",
    [
        ("calc/ops.py", "calc/*.py", True),
        ("calc/sub/ops.py", "calc/*.py", False),
        ("calc/sub/ops.py", "calc/**/*.py", True),
        ("calc/ops.py", "calc/**/*.py", True),
        ("CALC/ops.py", "calc/*.py", False),
        ("calc/ops.py", "./calc/*.py", True),
        ("calc/ops.py", "../calc/*.py", False),
    ],
)
def test_glob_match_is_segmentwise_and_case_sensitive(path, glob, ok):
    assert paths.glob_match(path, glob) is ok
