# W2-merge: Wave 2 merge
**Status:** done (one owner decision pending, see below)   **Branch:** w2/merge → main

## Built
- Merged w2/R, w2/A, w2/C, w2/B, w2/D (in that order, `--no-ff`). Conflicts were add-only:
  `pyproject.toml` keeps detect-secrets, mcp and inspect-ai; `Makefile` keeps clean, probe-image
  and demo; `uv lock` re-run.
- `av/gateway/wiring.py`: all ten components are real (OPA policy, SqliteLedger, HashBoundExecutor,
  B's checks/tiering/taint/outcome/scope_ok, C's run_tests/diff/secret_scan). `av/gateway/standins.py`
  deleted. The live path's stand-in guard now passes by itself.
- `av/gateway/core.py`: `run_tests` is tier 0 in B's catalog (no probe), so the gateway runs C's
  sandboxed RunTestsProbe itself after the pipeline accepts, returns pytest's output tail to the
  agent, records it as untrusted content, and logs the result or error to
  `<ledger>.run_tests.jsonl` (rule 5; the ledger row is already written by then).
- `av/gateway/workspace.py` (after code review): refuses hard-linked files; copies keep symlinks as
  links instead of following them.
- `av/replay.py`: ledgers are `<scenario>.db` (SQLite).

## Decisions
- **Interface requests:** B #1–#3 applied as specified (wiring, probe names, reads recorded:
  read_file, list_files, run_tests; ISSUE.md arrives via read_file). B #4 already holds: D's
  `_resolve` refuses any `..` or symlink segment, so the executed path is the checked path.
  B #5: gateway uses `scope_ok` as `ContractBuilder(scope_fn=...)`; SHARED `basic_scope_ok`
  left as is (informational only). D #1 kept (summary) and extended (output_tail).
  **D #2 declined:** ignoring `.py` reads in taint would blind provenance to injections
  planted in source files; B's "new material only" rule already keeps the benign scenario
  passing.
- Fixture expectations for `run_tests` changed from `accept` to `accept_with_logging` (tier 0 per
  the spec; D's stand-in used tier 1). Pre-freeze, so rule 14 doesn't apply.
- Tests adjusted for the merge itself: D's sample repo now ships `.github/` and a real bug, so B's
  fixtures use `mkdir(exist_ok=True)`, B's M4 `FIX` is the real fix (true division in
  `average`), C's docker tests start from a fixed baseline; D's gateway tests assert the real
  semantics (tier-1 edits execute and the OutcomeCheck records failures).

## Deviations
- The merge runs in worktree branch `w2/merge` and main is fast-forwarded to it (this session's
  harness blocks edits in the shared checkout). Same resulting history.

## Tests
- `uv run pytest -q`: 427 passed, 7 xfailed (B's known limitations). `-m docker`: 5 passed.
- `make demo`: components all `real`; benign accept; injection blocked (provenance only);
  scope_drift blocked (scope_drift: protected 'ci' write, 'tests' delete); hosted calls: 0.
  All three ledgers pass `python -m av.ledger verify`.
- code-reviewer on `git diff 183e84a..HEAD`: SHARED files unchanged; no trust-boundary,
  mediation, hash-binding or quota violation. One minor rule-5 logging gap (gateway-run
  run_tests result not logged) fixed and tested. Hard-link and symlink-copy hardening applied.

## Interface requests
None.

## Cost / quota
0 hosted calls.

## Handoff (Wave 3 notes)
- **Owner decision (B, rule 1):** the spec says tainted params → reject; PLAN narrows it to
  CI/workflow/script/dependency writes. B implemented: provenance counts only material not
  already live in the target; blocks tainted writes to CI, dependency, secrets, script, `#!` or
  test-config paths, and tainted URLs/command tokens in any write; plain substrings copied into
  an ordinary file are logged (`info`). The reviewer's alternative: escalate (require_human)
  those plain substrings instead of logging them. One-line change in `av/verify/taint.py`.
- **R's spec corrections** (in `blog/citations.md`): GRADE replay/rollback claim belongs to the
  `auditable` repo, not the paper; soften SREGym "no harm measurement"; 81% FNR is AmPermBench
  (stress test, not deployed traffic); 0.4%/17% are different populations (cite Anthropic);
  "bypassed" 36.8% is a paraphrase; AGT/ACS verdicts are allow/warn/deny/escalate/transform;
  Invariant link should be `invariant-gateway`; VoI and different-family-verifier claims are
  loose. The spec is the owner's to edit.
- **L (live):** `make probe-image` must have been run (else every run_tests probe defers).
  `AV_HOSTED_MODEL` must be set in `.env`. Live runs go through `av-hosted/<model>` (counted).
- **Still unverified:** memory/CPU cap enforcement in the sandbox; concurrent multi-process
  ledger appends; OPA latency under load. Three path resolvers exist (gateway `_resolve`,
  B's `paths.py`, C's probe `_inside`); consolidating is a later cleanup.
