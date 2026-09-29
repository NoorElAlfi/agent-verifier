"""ScopeDriftCheck: does this action stay inside what the TASK (never the agent) says is in scope?

Inputs: the task (scope_globs, declared_protected), the contract's tool and target, and the
workspace on disk (for symlinks and the old contents of a test file). Nothing the agent says
about itself is an input.

Results (severity is what decide() acts on):
- block    unsafe path (absolute, `..` escape, backslash, NUL, `.git`, a symlink leaving the
           workspace, a hard-linked target), or drift into a protected class the task did not
           declare: CI config, dependency manifests and lockfiles, secret-like paths, test
           deletion, test weakening, or any test-config change (conftest.py, pytest.ini);
- escalate a mutating action outside task.scope_globs (ordinary drift -> require_human);
- pass     everything else. Non-mutating tools pass unless their path is unsafe.

Every view of the target must pass: the lexical path and, when it differs, the path after
following symlinks. Scope globs match case-sensitively; protected patterns case-insensitively
(see av/verify/paths.py).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from av.contracts import MUTATING_TOOLS, ActionContract, CheckResult, TaskDefinition
from av.interfaces import CheckContext
from av.verify import paths

# --------------------------------------------------------------------------- test weakening

_SKIP_WORDS = ("skip", "xfail", "importorskip")


@dataclass(frozen=True)
class SuiteStats:
    tests: int
    asserts: int
    skips: int
    trivial_asserts: int


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def suite_stats(source: str) -> SuiteStats:
    """Count test functions/classes, assertions, skip/xfail markers and always-true asserts.
    Raises SyntaxError when `source` doesn't parse."""
    tree = ast.parse(source)
    tests = asserts = skips = trivial = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.lower().startswith("test"):
            tests += 1
        elif isinstance(node, ast.ClassDef) and node.name.lower().startswith("test"):
            tests += 1
        elif isinstance(node, ast.Assert):
            asserts += 1
            if isinstance(node.test, ast.Constant) and node.test.value:
                trivial += 1
        elif isinstance(node, ast.Call):
            name = _dotted(node.func).lower()
            last = name.rsplit(".", 1)[-1]
            if last.startswith("assert") or name.endswith("pytest.raises") or name.endswith("pytest.approx"):
                asserts += 1
            if any(w in last for w in _SKIP_WORDS) or last == "skiptest":
                skips += 1
        elif isinstance(node, ast.Assign | ast.AnnAssign) and any(
            isinstance(t, ast.Name) and t.id in ("__test__", "pytestmark", "collect_ignore", "collect_ignore_glob")
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        ):
            skips += 1  # `__test__ = False` / module-level markers switch collection off
        elif isinstance(node, ast.Attribute) and any(w in node.attr.lower() for w in _SKIP_WORDS):
            # decorators like @pytest.mark.skip / @unittest.skip used without a call
            skips += 1
    return SuiteStats(tests, asserts, skips, trivial)


def weakening_reason(path: str, old: str | None, new: str) -> str | None:
    """Why writing `new` over `old` at a test path weakens the tests, or None if it doesn't.

    A new file (old is None) adds tests: not weakening. Test-config files always count. For
    Python test files it compares AST counts; a file that doesn't parse counts as weakening.
    Non-Python files under a test path (fixtures, data) count as weakening when modified,
    since expected values can hide there. Known gap: changing an expected value to match a
    bug (`== 5` -> `== 6`) keeps every count the same (see the xfail test).
    """
    if paths.is_test_config(path):
        return "changes test configuration (can deselect or skip tests)"
    if old is None:
        return None
    if old == new:
        return None
    if not paths.is_python(path):
        return "modifies a non-Python file under a test path"
    try:
        after = suite_stats(new)
    except SyntaxError:
        return "new test file does not parse"
    try:
        before = suite_stats(old)
    except SyntaxError:
        return "old test file does not parse, so weakening can't be ruled out"
    reasons = []
    if after.tests < before.tests:
        reasons.append(f"test count {before.tests} -> {after.tests}")
    if after.asserts < before.asserts:
        reasons.append(f"assertion count {before.asserts} -> {after.asserts}")
    if after.skips > before.skips:
        reasons.append(f"skip/xfail markers {before.skips} -> {after.skips}")
    if after.trivial_asserts > before.trivial_asserts:
        reasons.append(f"always-true asserts {before.trivial_asserts} -> {after.trivial_asserts}")
    return "weakens tests: " + ", ".join(reasons) if reasons else None


# --------------------------------------------------------------------------- the check


def scope_ok(tool: str, target: str, task: TaskDefinition) -> bool:
    """ScopeFn for ContractBuilder(scope_fn=...): the lexical half of the check (no workspace).
    Fills the informational derived_scope_ok; the ScopeDriftCheck below is authoritative."""
    if tool not in MUTATING_TOOLS:
        return True
    norm = paths.lexical(target)
    if norm.path is None or not paths.in_scope(norm.path, task):
        return False
    undeclared = paths.protected_classes(norm.path) - set(task.declared_protected)
    if tool == "write_file" and not paths.is_test_config(norm.path):
        undeclared -= {"tests"}
    return not undeclared


def _read_text(file: Path | None) -> str | None:
    if file is None or not file.is_file():
        return None
    return file.read_bytes().decode("utf-8", errors="replace")


class ScopeDriftCheck:
    """Verification check. Put it first in Pipeline(checks=[...])."""

    name = "scope_drift"

    def run(self, contract: ActionContract, task: TaskDefinition, ctx: CheckContext) -> CheckResult:
        tool = contract.tool
        if tool == "submit":
            return self._ok("submit has no path")
        # The target is re-derived from params, never trusted from the contract alone.
        target = contract.params.get("path") if tool in ("list_files", "read_file", "write_file", "delete_file") else "."
        if tool == "list_files" and not target:
            target = "."
        if target != contract.target:
            return self._block(f"target {contract.target!r} does not match params path {target!r}")
        if target == "." and tool not in MUTATING_TOOLS:
            return self._ok(f"{tool} on the workspace root")

        norm = paths.lexical(target)
        if norm.path is None:
            return self._block(f"unsafe path {target!r}: {norm.problem}")
        resolved = paths.resolve_in_workspace(ctx.workspace.root, target)
        if resolved.path is None:
            return self._block(f"unsafe path {target!r}: {resolved.problem}")
        if tool not in MUTATING_TOOLS:
            return self._ok(f"{tool} stays inside the workspace")

        views = paths.paths_of(norm.path, resolved)
        declared = set(task.declared_protected)

        # 1. Protected classes (block unless declared).
        for view in views:
            classes = paths.protected_classes(view)
            for cls in sorted(classes - declared):
                if cls == "tests" and tool == "write_file":
                    old = _read_text(resolved.file)
                    why = weakening_reason(view, old, contract.params.get("content", ""))
                    if why is None:
                        continue
                    return self._block(f"protected class 'tests' (undeclared): {view}: {why}")
                what = "deletes" if tool == "delete_file" else "writes"
                return self._block(f"protected class {cls!r} (undeclared by the task): {tool} {what} {view}")

        # 2. Ordinary scope (escalate).
        for view in views:
            if not paths.in_scope(view, task):
                via = "" if view == norm.path else f" (symlink target of {norm.path})"
                return CheckResult(
                    name=self.name,
                    passed=False,
                    severity="escalate",
                    reason=f"scope drift: {tool} {view}{via} matches none of the task's scope_globs {list(task.scope_globs)}",
                )
        return self._ok(f"{tool} {norm.path} is in task scope")

    def _ok(self, reason: str) -> CheckResult:
        return CheckResult(name=self.name, passed=True, reason=reason)

    def _block(self, reason: str) -> CheckResult:
        return CheckResult(name=self.name, passed=False, severity="block", reason=f"scope drift: {reason}")
