"""HashBoundExecutor: Executor implemented as hash re-check, state re-check, then apply.

Order (spec M6): (1) recompute contract_hash from the contract about to be applied; a mismatch
with approved_hash is "refused". (2) For mutating tools, re-hash the target on disk and compare
with the snapshot taken at verification time; drift is "stale" (the pipeline re-verifies instead
of executing). (3) only then call workspace.apply(). Non-mutating tools skip (2).
"""

from __future__ import annotations

from av.contracts import ActionContract, ExecResult, contract_hash
from av.interfaces import Snapshot, Workspace


class HashBoundExecutor:
    def apply(
        self,
        contract: ActionContract,
        approved_hash: str,
        workspace: Workspace,
        snapshot: Snapshot,
    ) -> ExecResult:
        if contract_hash(contract) != approved_hash:
            return ExecResult(status="refused", detail="params hash differs from approved hash")
        if contract.is_mutating:
            target = contract.target
            if target not in snapshot:
                return ExecResult(status="stale", detail=f"{target} has no verification-time snapshot")
            now = workspace.snapshot_hashes([target]).get(target)
            if now != snapshot[target]:
                return ExecResult(status="stale", detail=f"{target} changed since verification")
        return workspace.apply(contract)
