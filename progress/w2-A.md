# W2-A: Policy, ledger, hash-bound executor
**Status:** done   **Branch:** w2/A

## Built
- `av/policy/opa.py`, `av/policy/__init__.py`: `OpaPolicyEngine` (PolicyEngine). `./bin/opa eval --stdin-input`, 2 s timeout; timeout, missing binary, non-zero exit, undefined or malformed output all return `AuthzResult(allow=False, error=...)` (decide() then defers).
- `policies/authz.rego`: `data.av.authz.result = {allow, reasons}`. Tool allowlist per task, denylist (absolute, drive-letter, `~`, backslash, NUL, empty, any `..` segment, any `.git` segment case-insensitively), max file size (1 MiB, UTF-8 bytes). No scope or provenance logic.
- `av/ledger.py`: `SqliteLedger` (Ledger). Table `ledger(seq, record_id, hosted_calls, prev_hash, row_json, row_hash)`, only INSERT/SELECT. `row_hash = sha256(prev_hash + canonical_json({seq, hosted_calls, record}))`. Extras: `rows()`, `records()`, `problems()`. CLI: `uv run python -m av.ledger verify <db>` (0 ok, 1 invalid, 2 usage/missing file).
- `av/executor.py`: `HashBoundExecutor` (Executor): hash check (refused), target snapshot check (stale), then `workspace.apply`.
- `tests/test_policy.py`, `tests/test_ledger.py`, `tests/test_executor.py`.

## Decisions
- `content_bytes` (UTF-8 size of `params.content`) is computed in Python and passed to OPA, since Rego has no byte-length builtin. It derives from params, never from claims.
- `.git` and `..` are matched per path segment after replacing `\` with `/` and lowercasing, so `./.git/x`, `sub/.GIT/x`, `calc/..` are denied. Symlink escapes are the Workspace's job (D), not policy's.
- Ledger `hosted_calls` defaults to `av.quota.usage()["total"]` at append time; injectable via `hosted_calls_fn`. It is inside the hashed row, so editing it fails verify.
- Executor: a mutating target absent from the snapshot dict is "stale" (fail closed). Only the target is re-checked; the pipeline re-checks the whole workspace.
- No SQLite triggers (an attacker with file access can drop them anyway); append-only is by code, tested by scanning ledger.py's SQL strings.
- Authorization is not scope: `.github/workflows/ci.yml` is allowed by policy (test documents this); B's ScopeDriftCheck decides.

## Deviations
None.

## Tests
194 passed offline (121 from Wave 1 + 73 new across policy, ledger, executor). code-reviewer found one bug, now fixed and tested: `submit` (target "") was denied as an empty path; Rego now only treats target as a path for path tools, and denies non-string paths. Covered: M6 (tampered params/target/tool refused, nothing written), M7 (authorization, verification, final_decision are separate stored fields; end-to-end pipeline with real OPA + ledger + executor), M8 (raw-SQL edit, edited hosted_calls, deleted row, and a re-hashed row all fail verify; CLI exit codes), OPA timeout/missing binary/bad rego/undefined/garbage output give defer, denylisted paths x 3 tools. Tests need `bin/opa` (skipped in test_policy.py if missing; `make setup`). Not verified: concurrent multi-process appends beyond SQLite's `BEGIN IMMEDIATE` lock; OPA latency under load (each authorize spawns a process, roughly tens of ms).

## Interface requests
None. (Note for the merge: wire `Pipeline(policy=OpaPolicyEngine(), executor=HashBoundExecutor(), ledger=SqliteLedger(path))`.)

## Cost / quota
0 hosted calls.

## Handoff
- Class names: `av.policy.OpaPolicyEngine`, `av.ledger.SqliteLedger`, `av.executor.HashBoundExecutor`.
- Ledger files belong under `AV_DATA_DIR` (e.g. `data_dir() / "ledgers" / f"{run}.db"`); the caller creates the directory.
- D: real Workspace.apply must refuse symlink escapes (policy only sees path strings).
- Each `authorize` call spawns an OPA process; fine for replay and episodes at this scale.
