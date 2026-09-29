# Agent Action Verifier

An open-source, risk-adaptive pre-commit gate for AI agents doing software operations, plus an
honest public study of which checks earn their cost. It ships as a blog series: Post 0 (Oct 5,
2026: design, frozen eval plan, demo), then Post 1 (CI/CD results), then Post 2 (SRE + robustness).

- **What to build and why:** `specs/agent-action-verifier.md`. It wins over
  `agent_action_verifier_thesis_scope.md`, which is background only. Don't re-read either in
  full; your prompt names the sections you need.
- **How the work is split:** `PLAN.md` (waves, and every agent's prompt).
- **Status:** `PROGRESS.md` (an index; only merge steps edit it) and `progress/<wave>-<agent>.md`.
  Read only the progress files your prompt names.

This file holds rules and layout only. Never append session logs here; they go in `progress/`.

## Layout (target; Wave 1 creates it, merges keep it current)

```
av/
  contracts.py      SHARED: ActionContract, TaskDefinition, Evidence, Decision, DecisionRecord,
                    canonical_json(), contract_hash(), ContractBuilder (the trust boundary)
  interfaces.py     SHARED: PolicyEngine, Check, Probe, TaintStore, Ledger, Workspace, Executor,
                    HumanOracle protocols; CheckContext
  decide.py         SHARED: decide(): the spec's default decision table, a pure function
  pipeline.py       SHARED: authorize → verify → decide → re-check → execute → outcome → ledger
  scenarios.py      SHARED: loads scenarios/<id>/task.yaml + proposals.jsonl
  config.py         SHARED: REPO_ROOT, .env loading, data_dir() (AV_DATA_DIR)
  clients.py        injectable model clients: hosted() (OpenCode Go, OpenAI-compatible), ollama()
  quota.py          counts every hosted call; enforces the caps in rule 7
  gpu.py            gpu_lock(): one Ollama job at a time
  policy/  (A)      OPA wrapper;  policies/*.rego
  ledger.py (A)     SQLite hash chain + `python -m av.ledger verify`
  executor.py (A)   hash-bound execution + state re-check
  verify/  (B)      tiering.py, scope.py, taint.py, outcome.py
  probes/  (C)      sandbox.py (disposable copy, Docker --network none), run_tests, diff, secrets
  gateway/ (D)      MCP server exposing the 6 agent tools
  agent/   (D)      minimal Inspect ReAct agent (gateway tools only)
  replay.py (D)     replays scenario fixtures through the gateway (no model calls)
examples/sample_repo/   tiny Python repo the scenarios act on
scenarios/<id>/         task.yaml (TaskDefinition) + proposals.jsonl (replay fixtures)
tests/                  fakes.py, conftest.py (fakes injected into every test)
blog/  docs/  reports/  progress/  scripts/
```

Run-time data (git-ignored) lives under `AV_DATA_DIR` (default `~/av-data`): ledgers, episode
logs, quota counter, and the `.gpu.lock` file. Every worktree points at the same folder.

## Rules every agent follows

1. **Spec first.** If your task conflicts with the spec, stop and ask. Don't resolve it silently.
2. **Worktrees and owned files.** Parallel agents each work on their own branch (`wN/X`) in
   their own worktree. Only edit the files your prompt says you own. If you need a change
   elsewhere, especially in the SHARED files above, write it under "Interface requests" in your
   progress file and work around it; the merge step decides. Two add-only exceptions:
   - you may *add* dependencies to `pyproject.toml` (the merge step re-runs `uv lock`);
   - you may *add* Makefile targets.
   Don't change existing entries in either.
3. **Trust boundary (non-negotiable).** The gateway derives task scope from the
   `TaskDefinition` and provenance from the `TaintStore`. Whatever the agent says about its own
   scope or provenance is recorded in `agent_claims` and never feeds a decision. Any change that
   lets an agent-supplied field reach `decide()` is a bug.
4. **Full mediation (non-negotiable).** The agent has exactly six tools, all served by the
   gateway: `list_files`, `read_file`, `write_file`, `delete_file`, `run_tests`, `submit`.
   Never add a shell tool, and never add a tool that bypasses the gateway.
5. **Fail closed.** An OPA, verifier or probe error or timeout gives `defer`, is logged, and
   nothing executes.
6. **Tests are offline.** `tests/conftest.py` injects the fakes. The real hosted and Ollama
   clients raise if a test reaches them. `uv run pytest -q` must pass before you finish.
7. **Quota gates (OpenCode Go is shared with the owner's personal use).** Every hosted call
   goes through `av.clients` and is counted by `av.quota`.
   - Before any run of more than 100 hosted calls: do a 1-episode trial, write the calls and
     tokens per episode and the projected total to your progress file, then STOP for approval.
   - Caps: Post 0 < 200 hosted calls in total; Post 1 ≤ 300 per day.
   - Claude usage for building is a separate budget and isn't gated here.
8. **One Ollama job at a time.** Anything making more than a handful of Ollama calls holds
   `gpu_lock()` (8 GB GPU).
9. **Disk budget.** Total new footprint ≤ 40 GB; ≤ 5 GB until Post 0 ships. Use small images
   (`python:3.12-slim`). `make clean` prunes them. Don't install SRE or Kubernetes tooling
   before the Post 2 gate.
10. **Long jobs can resume.** Write one file per episode under `AV_DATA_DIR`, skip episodes
    already done, and record in your progress file how to check on the job and resume it.
11. **Honest reporting.**
    - Every number in a report or post comes from a file in the repo or `AV_DATA_DIR`.
    - CIs come from a bootstrap that resamples whole tasks; when CIs overlap, say so.
    - Fixtures are labelled `recorded` or `synthetic`.
    - Never claim the verifier "is safe" or that it protects real CLI agents.
12. **Borrow, don't rebuild.** Use the official MCP Python SDK, Inspect AI, OPA, Docker, and
    detect-secrets. Don't write a new agent framework, sandbox, policy language, or
    orchestration layer.
13. **Build and measure separately.** An agent that builds a component doesn't also run the
    headline measurement for it; measurement runs get their own wave.
14. **Frozen means frozen.** After the git tag `post1-frozen`, nobody edits
    `scenarios/**/split=test`, the harm checkers, or `docs/post1-eval-plan.md`. A change needs a
    new tag and a disclosed note in the post.
15. **Hands off the owner's machine.** Never move WSL or Docker data, change global settings,
    or touch other projects. Give the owner exact commands instead.
16. **Subagents are read-only** (`.claude/agents/`):
    - `test-runner` (Haiku): after code changes. It runs `uv run pytest -q` and `make demo`,
      and reports compactly.
    - `code-reviewer`: before you finish. It checks the diff against rules 2–5, 7 and 12.
    - `repo-researcher`: for SDK and library questions (MCP SDK, Inspect, OPA, detect-secrets).
      It returns excerpts, not whole files.
17. **Running out of context.** Before you stop, write exactly where you stopped under
    "Where I stopped" in your progress file. Re-running the same prompt continues from there.

## Progress file template (`progress/<wave>-<agent>.md`)

```markdown
# <Wave>-<Agent>: <title>
**Status:** done | partial | blocked | waiting-for-approval   **Branch:** wN/X
## Built            <files, one line each>
## Decisions        <anything not in the spec, with the reason>
## Deviations       <from spec/PLAN, or "None">
## Tests            <counts, what's unverified>
## Interface requests   <or "None">
## Cost / quota     <hosted calls used, trial results, pending gates>
## Where I stopped  <exact next step; delete when done>
## Handoff          <what the next wave needs to know>
```

## Commands

- `uv sync`, then `uv run pytest -q`
- `make demo` (replay, no model calls) and `make demo LIVE=1` (hosted; quota-gated)
- `uv run python -m av.ledger verify <ledger.db>`
- `make clean` (prune probe images and volumes)
- `./scripts/new_worktree.sh <Wave> <Agent>` creates `~/av-wt/w<Wave>-<Agent>` on branch
  `w<Wave>/<Agent>`, copies `.env`, and sets `AV_DATA_DIR`.
- `.env` holds `OPENCODE_GO_API_KEY`, `OPENCODE_GO_BASE_URL` and `AV_DATA_DIR`. Never commit it,
  and never print keys.
