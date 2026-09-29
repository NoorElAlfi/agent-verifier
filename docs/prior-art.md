# Prior art

Written by Wave 2 Agent R, 2026-09-29. Every cell is drawn from a source listed in `blog/citations.md` (abstracts, READMEs, the Anthropic post). "Not stated" means the sources we read do not say; it does not mean the system lacks the feature. Only REMORA's code was run (see the runnability check below); everything else is read, not run.

## Comparison

| System | Interception point | Decision states | Contract / hash binding | Scope drift | Provenance and taint | Probes | Outcome verification | Evaluation |
|---|---|---|---|---|---|---|---|---|
| REMORA (research software, BUSL-1.1) | Governance overlay between the agent's proposed tool call and the protected tool; enforcing surface `POST /v1/execution/*` | ACCEPT, VERIFY, ABSTAIN, ESCALATE | Yes: "An approval is bound to the exact proposal it was given for and is consumed once" (single-use grant plus an `ExecutionLease`) | No drift detector found; tool meaning, target and approved intent come from a Signed ToolSpec, "never from the calling agent" | Hard-guard floor includes a "tainted argument" check (ARCHITECTURE.md); how taint is tracked was not examined | VERIFY routes to a "defined check or review"; no fixed probe catalog seen | Yes: "effect verification" records joinable by proposal identity | Own benchmarks in the README, each with scope caveats; AgentHarm row blocked every scenario incl. benign (208/208 benign blocked); "External replication is pending" |
| Bounded Autonomy (Sohail & Haider 2026) | Orchestration engine over a published actions manifest; consumer-side execution boundary | Not enumerated in the abstract; validation before side effects plus "optional human approval" | Typed action contracts; hash or signature binding not stated | Permission-aware capability exposure and scoped context; no drift detector stated | Not stated | Not stated | Not stated (validation feedback to the model before side effects) | 25 trials, one deployed enterprise app: 23/25 completed, 0 unsafe executions; 2 wrong-entity mutations escaped |
| AGT / ACS (Microsoft) | Application middleware; ACS evaluates at eight points including `pre_tool_call` / `post_tool_call` | Allow, Warn, Deny, Escalate, Transform (README also `require_approval`) | Not stated; tamper-evident decision records | Policy rules on action type; no task-scope derivation stated | Not stated | Not stated | `post_tool_call` hook exists; effect verification not stated | Claims "structural impossibility" of policy violations for denied actions; no benchmark read |
| AgentTrust (Yang 2026, AGPL-3.0) | Runtime layer intercepting tool calls before execution; MCP server | allow, warn, block, review | Not stated | Not stated | RiskChain detects multi-step attack chains; provenance not stated | LLM-as-Judge for ambiguous inputs; SafeFix suggests safer alternatives | Not stated (pre-execution focus) | 300-scenario internal benchmark (95.0% verdict accuracy); 630 external scenarios (96.7%, patched ruleset, not zero-shot) |
| Claude Code auto mode (Anthropic) | Permission prompts: tier 1 allowlist and settings, tier 2 in-project file edits (no classifier), tier 3 two-stage transcript classifier | Allow or block (classifier), else user prompt | None stated | None; the classifier judges each action against the transcript, and the authors' independent study found scope-escalation misses | Not stated | None; classifier only | None | Anthropic: 0.4% FPR (real traffic, n=10,000), 17% FNR (real overeager, n=52). Independent: 81.0% FNR on a stress test (Ji et al.) |
| GRADE / `auditable` (Zhao 2026) | Not an action gate: post-decision layer; the repo captures what a decision relied on | Not applicable (replay re-decides) | Dependency capture, not hash binding | Not stated | Dependency edges graded observed, declared or inferred | Not applicable | Yes: replays a decision against live state and rolls back the committed action if it no longer holds (repo) | Paper: six trace corpora for failure prediction, mostly null on the preregistered attachment control |
| Invariant Guardrails / Gateway | Rule layer between the app and the MCP servers or LLM provider (via `invariant-gateway`) | Rule match: not enumerated in the README | Not stated | Rules written as Python-like conditions; no derived task scope stated | Not stated | Not stated | Not stated | Not stated in the README |
| LlamaFirewall (Meta 2025) | "Final layer of defense": PromptGuard 2 on inputs, Agent Alignment Checks on reasoning, CodeShield on generated code | Guardrail verdicts; states not enumerated in the abstract | None stated | Agent Alignment Checks target "goal misalignment" via reasoning audit | Aimed at indirect prompt injection from untrusted inputs; not taint tracking | None | None | Abstract claims state-of-the-art PromptGuard 2; Alignment Checks called "still experimental" |
| CaMeL (Debenedetti et al. 2025) | Interpreter around the LLM; policies enforced "when tools are called" | Allow or block per capability policy | Capabilities on values; no action hash | By construction: untrusted data "can never impact the program flow" | Yes: control and data flow extracted from the trusted query; capabilities track data flows | None | None | AgentDojo: 77% of tasks solved with provable security vs 84% undefended |

## Where this project differs

**From REMORA:** REMORA gets tool meaning and approved intent from deployment-owned sources and binds a single-use grant to the proposal; this project also binds execution to a contract hash and re-checks state, but its point is to derive task scope (from the `TaskDefinition`) and provenance (from gateway-side taint on everything the agent read) and use them to detect scope drift, then measure which checks earn their cost against OPA-only, auto-mode-style and REMORA-style baselines on a frozen split.

**From Claude Code auto mode:** auto mode lets in-project file edits skip its classifier by design and judges the rest from the transcript, whereas this gateway mediates all six agent tools (including `write_file` and `delete_file`) and decides from task-derived scope and taint rather than from the agent's own transcript.

## Notes on fairness

- The "auto-mode-style classifier" and "REMORA-style" baselines in Post 1 are approximations built by us; see the runnability verdict below for what that means for REMORA.
- Contracts, graded decisions and hash-bound grants are already claimed by REMORA, Bounded Autonomy, AGT/ACS and AgentTrust. The contribution claimed here is the measured comparison and the scope-drift and provenance checks, not the decision vocabulary.
- Numbers for auto mode carry different populations (0.4% is real traffic, 17% is 52 real overeager actions, 81% is a stress test); see `blog/citations.md` A1, A2, A4 before quoting.

## REMORA runnability check

Time box: 30 minutes; it took about 3 minutes. Run on 2026-09-29 in a throwaway directory `/home/noorelalfi/.claude/jobs/6300cd62/tmp/remora` (deleted afterwards; nothing installed globally or in the project env). No hosted model calls, no API keys.

Steps:
1. `git clone --depth 1 https://github.com/darklordVirtual/REMORA-research.git repo` (commit `31c4060630923344d43d9fac26821150262c3687`, 134 MB, package `remora-assurance` 0.11.0, Python 3.12.3 available).
2. `python3 -m venv venv`, then `venv/bin/pip install -q -e "repo[dev]"`. Succeeded in under a minute with no errors.
3. `venv/bin/python -m remora try` (the README's command). Started, printed the banner and a five-item interactive menu (labelled SHADOW_ONLY), then exited on EOF because it is interactive.
4. Called the decision logic directly, in-process and offline, via `remora.assess.assess_tool_call(name, arguments, risk_tier=..., action_type=..., target_environment="staging")`, the same function the CLI wraps. Results:
   - `write_file` (high risk, action type `execute`, a CI-workflow path with `curl -d $SECRETS` content) returned `DecisionAction.VERIFY`.
   - `read_file` (low risk, `read`) returned `DecisionAction.ABSTAIN`. REMORA's SDK doc explains this: "with no server-side evidence even a low-risk read lands on ABSTAIN".
   - `delete_file` (medium risk, `destructive_write`, a test path) returned `DecisionAction.VERIFY`.
5. Deleted the throwaway directory.

Verdict: REMORA can be installed and its decision function called offline in a throwaway venv, so the Post 1 condition list can say **"REMORA (run)"**, with these disclosures:
- We would be running only its deterministic `assess_tool_call` decision path, with risk tier and action type supplied by our harness, not its full deployed system (Signed ToolSpec, evidence and oracle components, the `/v1/execution` grant flow). The honest label is "REMORA (run, decision function only, harness-supplied risk tier and action type)".
- It returns ABSTAIN for reads without server-side evidence, so the mapping from its four states to our accept/block outcome needs a written rule fixed before `post1-frozen`.
- License is BUSL-1.1 (source-available; its pyproject says commercial use needs a separate REMORA Commercial License). We have not had the license terms legally reviewed; running it for research and citing it looks fine, but redistributing its code in this repo's Apache-2.0 tree is not; call it as an external dependency, do not vendor it.
- Because the decision depends on `risk_tier` and `action_type` we would supply, a REMORA condition is only as fair as that mapping. If the owner prefers a simpler, safer statement, "REMORA-style (reimplemented)" remains available as a fallback.
