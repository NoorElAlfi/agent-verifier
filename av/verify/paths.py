"""Path normalisation and classification shared by tiering, scope and provenance.

Two views of every path:
- the *lexical* view: `..` and `.` resolved as text, never touching the disk. Used for scope
  globs, which match case-SENSITIVELY (being in scope is the permissive answer, so it must be
  exact);
- the *canonical* view: the lexical path, Unicode NFKC, case-folded, zero-width characters
  removed, trailing dots and spaces stripped from each segment. Used for protected-class
  patterns, which match case-INSENSITIVELY (being protected is the restrictive answer, so
  `.GitHub/Workflows/CI.yml` must still count as CI on a case-insensitive filesystem).

Symlink resolution needs the workspace, so it lives in `resolve_in_workspace()` and only the
checks (which get a CheckContext) use it; tiering is lexical only.

Every pattern table in this project that says "which paths are CI / tests / dependencies /
secrets / scripts" lives here, in one place.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from av.contracts import TaskDefinition

# --------------------------------------------------------------------------- normalisation

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class NormPath:
    """Result of lexical normalisation. `path` is None when the input is unsafe; `problem` says why."""

    raw: str
    path: str | None
    problem: str = ""


def lexical(raw: object) -> NormPath:
    """Normalise a workspace-relative POSIX path as text.

    Unsafe (path=None): not a string, empty, NUL, backslash, absolute, a drive letter, `~`
    prefix, resolving to the workspace root itself, or escaping it via `..`. Anything inside
    a `.git` directory is also unsafe (git hooks and config execute code and are never task
    scope). `calc/../.github/x` is NOT unsafe: it normalises to `.github/x`, which is then
    classified like any other path.
    """
    if not isinstance(raw, str) or raw == "":
        return NormPath(str(raw), None, "empty or non-string path")
    if "\x00" in raw:
        return NormPath(raw, None, "NUL byte in path")
    if "\\" in raw:
        return NormPath(raw, None, "backslash in path")
    if raw.startswith("/") or raw.startswith("~") or _DRIVE.match(raw):
        return NormPath(raw, None, "absolute path")
    norm = posixpath.normpath(raw)
    if norm == ".":
        return NormPath(raw, None, "path is the workspace root")
    if norm == ".." or norm.startswith("../"):
        return NormPath(raw, None, "path escapes the workspace")
    if ".git" in {canon_segment(s) for s in norm.split("/")}:
        return NormPath(raw, None, "path is inside a .git directory")
    return NormPath(raw, norm)


def canon_segment(seg: str) -> str:
    seg = unicodedata.normalize("NFKC", seg).translate(_ZERO_WIDTH).casefold()
    return seg.rstrip(" .") or seg


def canonical(path: str) -> str:
    """Case-folded, NFKC, zero-width-free form of a lexical path (for protected matching)."""
    return "/".join(canon_segment(s) for s in path.split("/"))


# --------------------------------------------------------------------------- scope globs


def _glob_segments(pattern: list[str], parts: list[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_glob_segments(rest, parts[i:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _glob_segments(rest, parts[1:])


def glob_match(path: str, pattern: str) -> bool:
    """Segment-wise glob, case-sensitive. `*`, `?` and `[...]` stay inside one segment;
    `**` matches zero or more whole segments. `./` prefixes in the pattern are ignored."""
    pat = posixpath.normpath(pattern.strip()) if pattern.strip() else ""
    if not pat or pat == "." or pat.startswith("/") or pat.startswith(".."):
        return False
    return _glob_segments(pat.split("/"), path.split("/"))


def in_scope(path: str, task: TaskDefinition) -> bool:
    """True when a lexically normalised path matches one of task.scope_globs."""
    return any(glob_match(path, g) for g in task.scope_globs)


# --------------------------------------------------------------------------- classes

# All patterns are matched against the CANONICAL (case-folded) path. `seg:` = any path segment
# equals it; `base:` = basename glob; `path:` = whole-path glob (segment-wise, `**` allowed).
PROTECTED_PATTERNS: dict[str, tuple[str, ...]] = {
    "ci": (
        "seg:.github",
        "seg:.gitlab",
        "seg:.circleci",
        "seg:.buildkite",
        "seg:.azure-pipelines",
        "seg:.woodpecker",
        "seg:.forgejo",
        "seg:.gitea",
        "seg:.husky",
        "base:.gitlab-ci.yml",
        "base:.gitlab-ci.yaml",
        "base:.travis.yml",
        "base:azure-pipelines.yml",
        "base:azure-pipelines.yaml",
        "base:jenkinsfile",
        "base:jenkinsfile.*",
        "base:.drone.yml",
        "base:.woodpecker.yml",
        "base:bitbucket-pipelines.yml",
        "base:appveyor.yml",
        "base:.appveyor.yml",
        "base:cloudbuild.yaml",
        "base:cloudbuild.yml",
        "base:.pre-commit-config.yaml",
        "base:.pre-commit-hooks.yaml",
        "base:tox.ini",
        "base:noxfile.py",
        "base:codecov.yml",
        "base:.codecov.yml",
    ),
    "dependencies": (
        "base:pyproject.toml",
        "base:setup.py",
        "base:setup.cfg",
        "base:requirements*.txt",
        "base:requirements*.in",
        "base:constraints*.txt",
        "path:**/requirements/*.txt",
        "path:**/requirements/*.in",
        "base:pipfile",
        "base:*.lock",
        "base:package.json",
        "base:package-lock.json",
        "base:npm-shrinkwrap.json",
        "base:pnpm-lock.yaml",
        "base:go.mod",
        "base:go.sum",
        "base:cargo.toml",
        "base:gemfile",
        "base:environment.yml",
        "base:environment.yaml",
        "base:.gitmodules",
        "base:.pip.conf",
        "base:pip.conf",
    ),
    "secrets": (
        "base:.env",
        "base:.env.*",
        "base:*.env",
        "base:*.pem",
        "base:*.key",
        "base:*.p12",
        "base:*.pfx",
        "base:*.jks",
        "base:*.keystore",
        "base:*.kdbx",
        "base:id_rsa*",
        "base:id_dsa*",
        "base:id_ecdsa*",
        "base:id_ed25519*",
        "base:.netrc",
        "base:.pypirc",
        "base:.npmrc",
        "base:.git-credentials",
        "base:.htpasswd",
        "base:credentials",
        "base:credentials.*",
        "base:*secret*.json",
        "base:*secret*.yaml",
        "base:*secret*.yml",
        "base:*secret*.toml",
        "base:*secret*.txt",
        "base:*secret*.ini",
        "base:*secret*.cfg",
        "base:*secret*.conf",
        "base:*secret*.env",
        "base:secrets",
        "seg:.ssh",
        "seg:.aws",
        "seg:.gnupg",
        "seg:.docker",
        "seg:.kube",
    ),
    "tests": (
        "seg:tests",
        "seg:test",
        "seg:testing",
        "base:test_*.py",
        "base:*_test.py",
        "base:*_tests.py",
        "base:conftest.py",
        "base:pytest.ini",
    ),
}

#: Test-path files whose ANY change counts as weakening: they configure collection and can
#: deselect or skip tests without touching a test body.
TEST_CONFIG_BASENAMES: frozenset[str] = frozenset({"conftest.py", "pytest.ini"})

#: Executable or build-script paths. Not a protected class (the spec names four), but a write
#: here is tier 2 and provenance-sensitive (PLAN: "CI, workflow, script or dependency write").
SCRIPT_PATTERNS: tuple[str, ...] = (
    "base:*.sh",
    "base:*.bash",
    "base:*.zsh",
    "base:*.fish",
    "base:*.ps1",
    "base:*.psm1",
    "base:*.bat",
    "base:*.cmd",
    "base:makefile",
    "base:gnumakefile",
    "base:*.mk",
    "base:justfile",
    "base:dockerfile",
    "base:dockerfile.*",
    "base:*.dockerfile",
    "base:containerfile",
    "base:docker-compose*.yml",
    "base:docker-compose*.yaml",
    "base:compose.yml",
    "base:compose.yaml",
    "base:procfile",
    "base:conftest.py",
    "base:setup.py",
    "base:noxfile.py",
    "base:tasks.py",
    "base:fabfile.py",
    "base:sitecustomize.py",
    "base:usercustomize.py",
    "base:*.pth",
    "seg:scripts",
    "seg:bin",
    "seg:hooks",
)


def _match_one(cpath: str, pattern: str) -> bool:
    kind, _, pat = pattern.partition(":")
    parts = cpath.split("/")
    if kind == "seg":
        return pat in parts
    if kind == "base":
        return fnmatchcase(parts[-1], pat)
    if kind == "path":
        return _glob_segments(pat.split("/"), parts)
    raise ValueError(f"bad pattern {pattern!r}")


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    cpath = canonical(path)
    return any(_match_one(cpath, p) for p in patterns)


def protected_classes(path: str) -> frozenset[str]:
    """Every protected class a lexically normalised path belongs to (usually zero or one).

    For "tests" this says the path is a test path; whether a WRITE to it is a protected change
    (deletion or weakening) is decided by the scope check, which can read the old content.
    """
    return frozenset(c for c, pats in PROTECTED_PATTERNS.items() if _matches(path, pats))


def is_test_config(path: str) -> bool:
    return canonical(path).split("/")[-1] in TEST_CONFIG_BASENAMES


def is_script(path: str, content: str | None = None) -> bool:
    return _matches(path, SCRIPT_PATTERNS) or (content is not None and content.lstrip("﻿").startswith("#!"))


def is_python(path: str) -> bool:
    return canonical(path).endswith(".py")


# --------------------------------------------------------------------------- the disk view


@dataclass(frozen=True)
class Resolved:
    """A path as the filesystem will see it: symlinks in any component followed."""

    path: str | None
    """Workspace-relative POSIX path after resolution; None when it leaves the workspace."""
    file: Path | None
    """Absolute resolved location (may not exist)."""
    problem: str = ""


def resolve_in_workspace(root: Path, lex_path: str) -> Resolved:
    """Follow symlinks for `lex_path` under `root`. Leaving the workspace (via any symlink) is a
    problem; so is landing inside `.git`, and writing through a hard-linked file (another path
    shares the same bytes, so the change would land somewhere the scope check never saw)."""
    root_r = Path(root).resolve()
    full = (root_r / lex_path).resolve(strict=False)
    if not full.is_relative_to(root_r) or full == root_r:
        return Resolved(None, None, "path resolves outside the workspace (symlink)")
    rel = full.relative_to(root_r).as_posix()
    if ".git" in {canon_segment(s) for s in rel.split("/")}:
        return Resolved(None, None, "path resolves into a .git directory (symlink)")
    try:
        if full.is_file() and full.stat().st_nlink > 1:
            return Resolved(None, None, "target is hard-linked to another path")
    except OSError as exc:  # can't tell: fail closed
        return Resolved(None, None, f"cannot stat target: {exc}")
    return Resolved(rel, full)


def paths_of(lex_path: str, resolved: Resolved | None) -> tuple[str, ...]:
    """The distinct views of one target that every rule must accept (lexical, resolved)."""
    out = [lex_path]
    if resolved is not None and resolved.path is not None and resolved.path != lex_path:
        out.append(resolved.path)
    return tuple(out)
