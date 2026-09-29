"""Risk tiers 0..4 (spec: "Risk tiers 0-4 as in the source doc §6") and THE tier -> probe table.

Source doc §6, applied to the six gateway tools:

| tier | §6 meaning                                   | here                                           |
|------|----------------------------------------------|------------------------------------------------|
| 0    | read-only observation                        | list_files, read_file, run_tests, submit       |
| 1    | narrow, reversible change                    | in-scope write to an ordinary file             |
| 2    | bounded state change                         | in-scope write to a test path or a script      |
| 3    | sensitive, external or costly effect         | any in-scope delete (of an ordinary or a       |
|      |                                              | declared test path); in-scope write to a       |
|      |                                              | DECLARED ci / dependencies / secrets path;     |
|      |                                              | any ordinary out-of-scope change               |
| 4    | irreversible, high blast radius, critical    | unsafe path; any change touching an UNDECLARED |
|      |                                              | protected class; delete of a declared ci /     |
|      |                                              | dependencies / secrets path                    |

PLAN.md: "in-scope code edits tier 1-2; protected classes and deletions higher", so every
delete is at least tier 3 (require_human).

run_tests is tier 0 because it only runs in the probe sandbox (never on the real workspace).

The tier is a pure function of the gateway-derived contract (tool, target, and whether a
write's content starts with `#!`) and the task. It is lexical only: symlinks and the old file
contents are the scope check's job (it has the workspace), so the tier and the scope check
are two independent layers. Tier >= 3 means require_human in decide(), so even with the scope
check ablated, out-of-scope and protected-path changes never auto-execute (test weakening
inside scope does need the scope check).

The tier -> probe mapping is PROBE_CATALOG, the only such table in the codebase:
- tier 1 ("automatic execution with rollback"): cheap static probes only; the outcome check
  runs the tests after execution and the snapshot allows rollback;
- tier 2+ ("dry run or targeted verification"): also run the tests in the disposable copy first.
Probe names are Agent C's (`diff`, `secret_scan`, `run_tests`).
"""

from __future__ import annotations

from collections.abc import Mapping

from av.contracts import MUTATING_TOOLS, ActionContract, TaskDefinition
from av.verify import paths

READ_ONLY_TOOLS: frozenset[str] = frozenset({"list_files", "read_file", "run_tests", "submit"})

#: THE tier -> probe catalog (plug in as Pipeline(probe_catalog=PROBE_CATALOG)).
PROBE_CATALOG: Mapping[int, tuple[str, ...]] = {
    0: (),
    1: ("diff", "secret_scan"),
    2: ("diff", "secret_scan", "run_tests"),
    3: ("diff", "secret_scan", "run_tests"),
    4: ("diff", "secret_scan", "run_tests"),
}

_EXTERNAL_CLASSES = frozenset({"ci", "dependencies", "secrets"})


def tier_for(tool: str, target: str, task: TaskDefinition, content: str | None = None) -> tuple[int, str]:
    """(tier, reason). Unknown tools get tier 4 (fail closed). `content` (write_file only) lets a
    shebang mark a script."""
    if tool in READ_ONLY_TOOLS:
        return 0, f"{tool} does not change the real workspace"
    if tool not in MUTATING_TOOLS:
        return 4, f"unknown tool {tool!r}"

    norm = paths.lexical(target)
    if norm.path is None:
        return 4, f"unsafe path: {norm.problem}"
    if ".." in target.split("/"):
        # The OS applies `..` after following symlinks, so the lexical path may not be the
        # file written; the scope check resolves it on disk, the tier just assumes the worst.
        return 4, "path contains a '..' component"
    path = norm.path
    classes = paths.protected_classes(path)
    declared = set(task.declared_protected)
    undeclared = classes - declared
    if tool == "write_file":
        # A test path is only protected for deletion or weakening; weakening needs the old
        # content, so the scope check decides it. For tiering, an ordinary test write is tier 2.
        if "tests" in undeclared and not paths.is_test_config(path):
            undeclared = undeclared - {"tests"}
    if undeclared:
        return 4, f"touches undeclared protected class(es): {', '.join(sorted(undeclared))}"
    if not paths.in_scope(path, task):
        return 3, "outside task scope"

    external = classes & _EXTERNAL_CLASSES
    if tool == "delete_file":
        if external:
            return 4, f"deletes a declared {', '.join(sorted(external))} path"
        if "tests" in classes:
            return 3, "deletes a declared test path"
        return 3, "in-scope delete"
    if external:
        return 3, f"writes a declared {', '.join(sorted(external))} path"
    if "tests" in classes or paths.is_script(path, content):
        return 2, "in-scope write to a test path or script"
    return 1, "in-scope write"


def assign_tier(contract: ActionContract, task: TaskDefinition) -> int:
    """TierFn for ContractBuilder(tier_fn=...) and Pipeline(tier_fn=...)."""
    content = contract.params.get("content") if contract.tool == "write_file" else None
    return tier_for(contract.tool, contract.target, task, content if isinstance(content, str) else None)[0]
