"""RunTestsProbe, DiffProbe, SecretScanProbe (Probe protocol, av/interfaces.py).

Probes never write to workspace.root. Errors are returned as ProbeResult(error=...), which
decide() turns into defer (fail closed).
"""

from __future__ import annotations

import difflib
import tempfile
from pathlib import Path

from av.contracts import ActionContract, ProbeResult
from av.interfaces import Workspace
from av.probes.sandbox import SandboxError, run_in_sandbox


def _inside(root: Path, rel: str) -> Path:
    """Resolve rel under root or raise ValueError (no absolute paths, no escape)."""
    root = root.resolve()
    p = (root / rel).resolve()
    if rel.startswith("/") or not p.is_relative_to(root):
        raise ValueError(f"path {rel!r} escapes the workspace")
    return p


def apply_to_copy(contract: ActionContract, copy_root: Path) -> None:
    """Apply a mutating contract to the disposable copy only."""
    if contract.tool == "write_file":
        p = _inside(copy_root, contract.target)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contract.params["content"])
    elif contract.tool == "delete_file":
        _inside(copy_root, contract.target).unlink(missing_ok=True)


class RunTestsProbe:
    """Apply the contract to a copy, then run pytest on it in the sandbox."""

    name = "run_tests"

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        cmd = ["python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"]
        try:
            with workspace.disposable_copy() as copy:
                apply_to_copy(contract, copy)
                res = run_in_sandbox(copy, cmd)
        except (SandboxError, ValueError, OSError) as e:
            return ProbeResult(name=self.name, passed=False, error=f"{type(e).__name__}: {e}")
        if res.timed_out:
            return ProbeResult(name=self.name, passed=False, error="probe timed out")
        lines = res.stdout.strip().splitlines()
        tail = lines[-1] if lines else ""
        details = {"exit_code": res.exit_code, "output_tail": res.stdout[-2000:]}
        if res.exit_code == 0:
            return ProbeResult(name=self.name, passed=True, summary=tail or "tests passed", details=details)
        if res.exit_code in (1, 5):  # 1 = failures, 5 = no tests collected
            return ProbeResult(name=self.name, passed=False, summary=tail or "tests failed", details=details)
        return ProbeResult(
            name=self.name, passed=False, details=details,
            error=f"pytest exit {res.exit_code}: {res.stderr[-300:]}",
        )


class DiffProbe:
    """Unified diff plus stats for the contract's target. Informational: passes unless it errors."""

    name = "diff"

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        if contract.tool not in ("write_file", "delete_file"):
            return ProbeResult(
                name=self.name, passed=True, summary="not a mutating action",
                details={"added": 0, "removed": 0, "diff": ""},
            )
        try:
            src = _inside(workspace.root, contract.target)
            old = src.read_text().splitlines(keepends=True) if src.is_file() else []
            new = contract.params["content"].splitlines(keepends=True) if contract.tool == "write_file" else []
        except (ValueError, OSError, UnicodeDecodeError) as e:
            return ProbeResult(name=self.name, passed=False, error=f"{type(e).__name__}: {e}")
        lines = list(difflib.unified_diff(old, new, f"a/{contract.target}", f"b/{contract.target}"))
        added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
        removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
        return ProbeResult(
            name=self.name, passed=True, summary=f"+{added} -{removed} in {contract.target}",
            details={
                "added": added, "removed": removed, "created": not old and bool(new),
                "deleted": contract.tool == "delete_file", "diff": "".join(lines)[:20000],
            },
        )


class SecretScanProbe:
    """detect-secrets on the proposed content. Findings never include the secret value."""

    name = "secret_scan"

    def run(self, contract: ActionContract, workspace: Workspace) -> ProbeResult:
        if contract.tool != "write_file":
            return ProbeResult(name=self.name, passed=True, summary="no content to scan")
        try:
            from detect_secrets.core.scan import scan_file
            from detect_secrets.settings import default_settings

            # scan_file (not scan_line: its eager entropy mode flags ordinary code). The temp
            # file lives outside the workspace and is deleted straight away.
            with tempfile.TemporaryDirectory(prefix="av-scan-") as d:
                f = Path(d) / ("scan" + Path(contract.target).suffix)
                f.write_text(contract.params["content"])
                with default_settings():
                    findings = [{"line": s.line_number, "type": s.type} for s in scan_file(str(f))]
        except Exception as e:  # noqa: BLE001 - fail closed via error
            return ProbeResult(name=self.name, passed=False, error=f"{type(e).__name__}: {e}")
        if findings:
            return ProbeResult(
                name=self.name, passed=False,
                summary=f"{len(findings)} potential secret(s) in {contract.target}",
                details={"findings": findings},
            )
        return ProbeResult(name=self.name, passed=True, summary="no secrets detected")
