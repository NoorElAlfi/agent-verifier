# W2-D: Gateway, agent, replay, scenarios
**Status:** done   **Branch:** w2/D

## Built
- `av/gateway/core.py`: `Gateway.call(tool, params, agent_claims)`, the single code path for live and replay: ContractBuilder -> Pipeline.run() -> reply text; executed reads are recorded into the TaintStore.
- `av/gateway/server.py`: MCP server (official SDK 2.x `MCPServer`, stdio), exactly the 6 tools; loads the task from `scenarios/<id>/task.yaml` at start (`python -m av.gateway.server --scenario ID --workspace DIR --ledger FILE`).
- `av/gateway/workspace.py`: `SandboxWorkspace` (real `Workspace`: symlink/`..`-safe apply for all 6 tools, snapshots, disposable copy) and `prepare_workspace()` (fresh private copy of the repo plus a scenario's `overlay/`).
- `av/gateway/wiring.py`: the ONE table (`COMPONENTS`) that picks every component; each row is labelled `standin`, and `describe()` prints the labels.
- `av/gateway/standins.py`: clearly labelled stand-ins for A, B and C components (see Handoff).
- `av/agent/provider.py`: Inspect model provider `av-hosted/<model>` whose `generate()` calls `av.clients.hosted().chat(...)`, so Inspect's calls are counted by av.quota and fakes work offline.
- `av/agent/react.py`: Inspect `react(tools=[mcp_tools(mcp_server_stdio(...))], submit=False)`; `run_episode()` asserts the quota budget first, writes one file per episode under `AV_DATA_DIR/episodes/<run>/` and skips finished ones; CLI `python -m av.agent.react`.
- `av/replay.py`: replays proposals.jsonl through `Gateway`, prints the per-scenario decision table, writes a ledger per scenario under `AV_DATA_DIR/ledgers/<run>/`, ends with `hosted calls: N`; any model client use during replay raises.
- `scenarios/{scope_drift,injection,benign}/` (task.yaml, proposals.jsonl, `injection/overlay/ISSUE.md`), all `origin: synthetic`.
- `examples/sample_repo/`: real bug (`average()` uses `//`), a failing test, `.github/workflows/ci.yml`, `ISSUE.md`.
- `Makefile`: `demo` target (`LIVE=1` for the hosted path). `tests/test_gateway.py`, `tests/test_replay.py`.
- `pyproject.toml`/`uv.lock`: added `mcp`, `inspect-ai` (add-only).

## Decisions
- **All six tools go through the pipeline**, reads included (full mediation; tier 0 -> `accept_with_logging` and a ledger row). Only after `executed` is a read's output recorded into the TaintStore (sources: `<path>`, `list_files:<path>`, `run_tests:.`).
- **Scenarios run on a fresh copy** of `examples/sample_repo` (+ `overlay/`) under `AV_DATA_DIR`, never on the checked-in repo; that is what "resets the sample repo" means. The injection scenario needs a different `ISSUE.md`, hence the overlay.
- **Injection task has CI in scope on purpose** (`declared_protected: [ci]`, workflow glob in `scope_globs`) so the ONLY thing stopping the injected edit is provenance. A test asserts the failed check is `provenance` and `derived_scope_ok` is true. scope_drift covers the scope path.
- **Scenario outcome** is a header key `scenario_outcome` (`blocked` = any action not accepted-and-executed) alongside each proposal's `expect`; replay exits non-zero on any mismatch. `ProposalsHeader` already allows extras, no shared-file change.
- **run_tests tool**: the result the agent sees is the `summary` of the probe named `run_tests`. Tests run in a disposable copy (probe path); `Workspace.apply(run_tests)` does nothing. For the run_tests tool the probe passes whenever the run completes (a red suite is information, not a reason to reject); for write/delete the probe applies the change to the copy and passes only if the tests then pass.
- **Inspect**: `react()` adds its own `submit` tool (a 7th tool, clashing with the gateway's), so `submit=False`; the gateway's `submit` is the only one. Inspect's built-in `openai-api/...` provider would bypass av.quota, so a custom provider goes through `av.clients.hosted()` (rule 7). Model name from `AV_HOSTED_MODEL` in `.env`.
- **Live budget**: each episode asserts `quota.assert_budget(max_model_calls)` (default 20) before starting and Inspect's `message_limit` is 2*N+2, so an episode cannot exceed N model calls; a run of >100 planned calls still needs the owner's approval per rule 7.
- **Live is refused while any component is a stand-in** (`av/agent/react.py::assert_live_ready`): the stand-in probe runs agent-written code with pytest on the host (no Docker). Offline tests set `AV_ALLOW_STANDINS=1`. After the merge, no component is labelled `standin`, so the guard lifts by itself. (Code-reviewer finding.)
- **Calls that can't become a contract** (unknown tool, bad params, builder/taint/scope/tier exception) have no DecisionRecord; they are logged to `<ledger>.refusals.jsonl` and nothing executes. (Code-reviewer finding.)
- The stand-in TaintStore ignores `.py` reads (documented; reviewer flagged it). B's real store replaces it.
- Agent has no channel for claims on the live path (MCP tool schemas have only the fixed params); replay fixtures may carry `agent_claims`, which go to the ledger only. Tests assert identical decisions with and without lying claims.

## Deviations
None from spec/PLAN. (`make demo` "resets the sample repo" by never modifying it, see Decisions.)

## Tests
`uv run pytest -q`: 145 passed offline (121 from Wave 1 + 24 new: M5 in-process, over real stdio, no scope/provenance fields in tool schemas, unknown-tool refusal, claims never change a decision, path traversal, injection blocked by provenance, run_tests via probe path, bad fix rejected by probe, ledger chain, live agent path offline with a scripted client (Inspect + MCP + provider), quota gate first, replay of all 3 scenarios, zero hosted calls, sample repo untouched, mismatch detection). Unverified: anything against a real model, real OPA/ledger/executor/verify/probes (stand-ins), Docker isolation.

## Interface requests
- `Workspace` protocol (interfaces.py) and `ExecResult`: no `run_tests` output channel other than a probe's `ProbeResult.summary`. The gateway relies on the probe named `run_tests` putting pytest output in `summary`. Please keep that convention for C (or add an `output` field to ProbeResult).
- Real `TaintStore` (B): the stand-in ignores reads of `.py` files, otherwise a benign rewrite of a file the agent just read shares whole lines (>= 20 chars) with it and would be flagged as tainted. B's matcher needs some equivalent rule (or the `benign` scenario will regress at merge); `make demo` shows it.

## Cost / quota
0 hosted calls (0 Ollama). Nothing was run live. Pending gate: none for Wave 2; a live trial (1 episode, calls and tokens per episode, projected total) is required before any run over 100 calls.

## Handoff
**Merge step, swap stand-ins for real components by editing only `av/gateway/wiring.py::COMPONENTS`** (one row each; change the label to `real`):
| row | stand-in (`av/gateway/standins.py`) | replace with |
|---|---|---|
| `policy` | `StandInPolicy` | A: OPA `PolicyEngine` |
| `ledger` | `ChainLedger(path)` (JSONL chain; factory takes the path) | A: `SqliteLedger(path)` |
| `executor` | `StandInExecutor` | A: `av/executor.py` executor |
| `checks` | `StandInScopeCheck`, `StandInProvenanceCheck` | B: `ScopeDriftCheck`, `ProvenanceCheck` |
| `tier_fn`, `probe_catalog` | `stand_in_tier`, `STAND_IN_CATALOG` | B: `assign_tier`, tier -> probes table |
| `taint_store` | `StandInTaintStore` | B: real TaintStore |
| `probes` | `{"run_tests": StandInRunTestsProbe()}` (pytest in a copy, no Docker) | C: `{"run_tests": RunTestsProbe(), "diff": ..., "secret_scan": ...}` (key `run_tests` must stay) |
| `outcome_checks` | `[]` | B: `OutcomeCheck` |
| `scope_fn` | `basic_scope_ok` (core) | optionally B's scope function |

Then: delete `standins.py` (nothing else imports it, except `tests/test_gateway.py::test_live_agent_path_offline...` and the ledger assertions, which use `ChainLedger`/`.records()`; switch them to the real ledger reader), and re-run `make demo`: the table must still read blocked, blocked, accept. Watch the `benign` row for taint false positives (see Interface requests) and for the probe catalog: the gateway expects tier-1/2 writes and `run_tests` to have the `run_tests` probe in the catalog.
- Live path: `make demo LIVE=1` (or `uv run python -m av.agent.react [ids] --run-id X`) needs `AV_HOSTED_MODEL` in `.env`; resumable (finished episodes in `AV_DATA_DIR/episodes/<run-id>/<scenario>.json` are skipped; check progress with `ls` there and `uv run python -m av.quota`). Not run in Wave 2.
- Wave 3 L re-records the proposals: change `origin` to `recorded` in each `proposals.jsonl` header.
- `SandboxWorkspace.apply` re-checks paths (no `..`, no symlinks) as defence in depth; policy/scope checks stay authoritative.
