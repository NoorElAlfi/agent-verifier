"""OpaPolicyEngine: PolicyEngine implemented with `./bin/opa eval` in a subprocess.

Authorization answers "may it?" only (tool allowlist, path denylist, max file size). Scope drift
and provenance belong to verification. Any OPA failure (missing binary, timeout, non-zero exit,
bad or undefined output) returns AuthzResult(allow=False, error=...), which decide() turns into
defer (CLAUDE.md rule 5). The input is built only from the contract's tool/target/params and the
TaskDefinition; agent_claims is never read.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from av.config import REPO_ROOT
from av.contracts import ActionContract, AuthzResult, TaskDefinition

DEFAULT_OPA = REPO_ROOT / "bin" / "opa"
DEFAULT_POLICY_DIR = REPO_ROOT / "policies"
QUERY = "data.av.authz.result"
MAX_FILE_BYTES = 1_048_576
TIMEOUT_S = 2.0


class OpaPolicyEngine:
    def __init__(
        self,
        opa_path: str | Path = DEFAULT_OPA,
        policy_dir: str | Path = DEFAULT_POLICY_DIR,
        timeout: float = TIMEOUT_S,
        max_file_bytes: int = MAX_FILE_BYTES,
    ):
        self.opa_path = str(opa_path)
        self.policy_dir = str(policy_dir)
        self.timeout = timeout
        self.max_file_bytes = max_file_bytes

    def build_input(self, contract: ActionContract, task: TaskDefinition) -> dict[str, Any]:
        content = contract.params.get("content")
        return {
            "tool": contract.tool,
            "target": contract.target,
            "params": contract.params,
            "allowed_tools": list(task.allowed_tools),
            "max_file_bytes": self.max_file_bytes,
            "content_bytes": len(content.encode("utf-8")) if isinstance(content, str) else 0,
        }

    def authorize(self, contract: ActionContract, task: TaskDefinition) -> AuthzResult:
        try:
            payload = json.dumps(self.build_input(contract, task))
            proc = subprocess.run(
                [
                    self.opa_path,
                    "eval",
                    "--format",
                    "json",
                    "--stdin-input",
                    "--data",
                    self.policy_dir,
                    QUERY,
                ],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return AuthzResult(allow=False, error=f"opa timed out after {self.timeout}s")
        except Exception as exc:  # missing binary, bad input, ...
            return AuthzResult(allow=False, error=f"opa failed to run: {exc}")
        if proc.returncode != 0:
            return AuthzResult(
                allow=False, error=f"opa exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            )
        try:
            value = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
            allow = value["allow"]
            reasons = tuple(str(r) for r in value["reasons"])
            if not isinstance(allow, bool):
                raise TypeError("allow is not a bool")
        except Exception as exc:  # undefined result, unexpected shape
            return AuthzResult(allow=False, error=f"opa returned an unusable result: {exc!r}")
        return AuthzResult(allow=allow, reasons=reasons)
