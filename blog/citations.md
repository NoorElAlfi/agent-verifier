# Citations: every number and claim traced to a source

Compiled by Wave 2 Agent R on 2026-09-29. Each entry gives the claim as the spec states it, the source URL, a verbatim quote and where it sits. Abstracts were pulled from arxiv.org abstract pages; the Permission Gate body text from its HTML version; the auto-mode figures from the Anthropic post. Verdicts: VERIFIED, VERIFIED-WITH-CAVEAT (the number is right but the spec's paraphrase needs tightening), NOT FOUND.

Summary:
- 16 numeric claims checked (sections A1 to A8): 13 VERIFIED, 3 VERIFIED-WITH-CAVEAT (A1, A2, A4), 0 NOT FOUND.
- Non-numeric descriptions (sections B and C): 2 NOT FOUND (C1 GRADE replay/rollback is not in the linked paper; C4 the SREGym "no harm measurement" absence claim is unchecked), 5 with caveats (B1, B3, C2, C3, C5), the rest verified.

## A. Numbers

### A1. 81% FNR on DevOps scope escalation. VERIFIED-WITH-CAVEAT
- Source: Ji, Li, Jiang, Gao, Wang, "Measuring the Permission Gate: A Stress-Test Evaluation of Claude Code's Auto Mode", https://arxiv.org/abs/2604.04978 (HTML: https://arxiv.org/html/2604.04978v2)
- Quote: "The end-to-end false negative rate is 81.0% (95% CI: 73.8%-87.4%), substantially higher than the 17% reported on production traffic, reflecting a fundamentally different workload rather than a contradiction."
- Location: abstract; Section 5.2 "Finding 2: Action-Level Gate Metrics", Table 3 ("FNR = 115/(115+27) = 81.0%"; 253 actions from 128 prompts).
- Scope quote (Section 1): "Neither rate is directly comparable to Anthropic's 17% FNR on production traffic, which measures accidental overshoot; our benchmark deliberately targets the authorization boundary."
- Caveat: the 81% is on a deliberately ambiguous stress test (AmPermBench, "a 128-prompt benchmark spanning four DevOps task families and three controlled ambiguity axes"). It is not a deployed-traffic failure rate, and the authors say it is not comparable to the 17%. Suggested wording: "81.0% end-to-end FNR (95% CI 73.8 to 87.4%) on AmPermBench, a stress test of ambiguous DevOps authorization scenarios".

### A2. 36.8% of state changes bypassed the gate via file edits. VERIFIED-WITH-CAVEAT
- Source: same paper.
- Quote (abstract): "Notably, 36.8% of all state-changing actions fall outside the classifier's scope via Tier 2 (in-project file edits), contributing to the elevated end-to-end FNR."
- Quote (Section 5.2): "Of the 253 actions, 93 (36.8%) were performed via Edit or Write tool calls, which are routed through Tier 2 and are not evaluated by the classifier."
- Caveat: "bypassed" is our paraphrase. The paper says "fall outside the classifier's scope" and "not evaluated by the classifier". Tier 2 exempting in-project edits is by design (Anthropic post: "File writes and edits inside the project directory are allowed without a classifier call."). Use "were never evaluated by the classifier (by design)". Also note 93/253 is on the same stress-test workload.

### A3. 93% of prompts approved. VERIFIED
- Source: Anthropic, "How we built Claude Code auto mode: a safer way to skip permissions", published Mar 25, 2026, https://www.anthropic.com/engineering/claude-code-auto-mode
- Quote: "Claude Code users approve 93% of permission prompts."
- Location: post subtitle/intro. Repeated in the body: "in practice users accept 93% of them anyway."
- Note: this is the approval rate of manual permission prompts, not a classifier result.

### A4. Classifier 0.4% FPR / 17% FNR. VERIFIED-WITH-CAVEAT
- Source: Anthropic auto-mode post, same URL.
- Quote (Table 1, "Classifier performance by stage"): "Real traffic n=10,000 Real overeager n=52 Synthetic exfil n=1,000 ... Stage 1->Stage 2 (full pipeline) 0.4% FPR 17% FNR 5.7% FNR"
- Quote (text): "The 17% false-negative rate on real overeager actions is the honest number."
- Caveat: the two figures come from different populations. The 0.4% FPR is on real traffic (n=10,000); the 17% FNR is on real overeager actions (n=52). Do not describe them as one measurement, and state the small n=52. Ji et al. call the 17% "reported on production traffic", but Anthropic's own table says overeager actions; cite Anthropic.

### A5. 73.6% ASR on Claude Code + Qwen3-Coder. VERIFIED
- Source: Feng et al., "AgentHazard: A Benchmark for Evaluating Harmful Behavior in Computer-Use Agents", https://arxiv.org/abs/2604.02947 (the spec links https://huggingface.co/papers/2604.02947)
- Quote (abstract): "In particular, when powered by Qwen3-Coder, Claude Code exhibits an attack success rate of 73.63%, suggesting that model alignment alone does not reliably guarantee the safety of autonomous agents."
- Location: abstract. The benchmark has 2,653 instances. The spec's 73.6% is a fair rounding; cite 73.63%.

### A6. SHADE-Arena best monitor AUC 0.87. VERIFIED
- Source: Kutasov et al., "SHADE-Arena: Evaluating Sabotage and Monitoring in LLM Agents", https://arxiv.org/abs/2506.15740
- Quote (abstract): "with the top monitor (Gemini 2.5 Pro) achieving an AUC of 0.87 at distinguishing benign and malign transcripts."
- Location: abstract.

### A7. Bounded Autonomy 23/25 tasks, 0 unsafe. VERIFIED
- Source: Sohail & Haider, "Bounded Autonomy for Enterprise AI: Typed Action Contracts and Consumer-Side Execution", https://arxiv.org/abs/2604.14723
- Quote (abstract): "Across 25 scenario trials spanning seven failure families, the bounded-autonomy system completed 23 of 25 tasks with zero unsafe executions, while the unconstrained configuration completed only 17 of 25. Two wrong-entity mutations escaped all consumer-contributed layers; only disambiguation and confirmation mechanisms intercept this class."
- Note: 25 trials in one deployed enterprise application; the two failures were wrong-entity mutations that got past the contract layers. State this when quoting "0 unsafe".

### A8. "The rest": other numbers we may quote
| Claim | Source | Verbatim quote | Location | Verdict |
|---|---|---|---|---|
| Ctrl-Z: attacks 58% to 7% at 5% usefulness cost | https://arxiv.org/abs/2504.10374 | "reducing the success rate of attacks from 58% to 7% at a 5% cost to the performance of a non-malicious agent." | abstract (BashBench: "257 challenging multi-step system administration tasks") | VERIFIED |
| CaMeL: 77% of tasks with provable security vs 84% undefended | https://arxiv.org/abs/2503.18813 | "solving 77% of tasks with provable security (compared to 84% with an undefended system) in AgentDojo." | abstract | VERIFIED |
| AgentTrust: 95.0% verdict accuracy internal; 96.7% on 630 scenarios | https://arxiv.org/abs/2605.04785 | "the production-only ruleset achieves 95.0% verdict accuracy and 73.7% risk-level accuracy ... evaluated under a patched ruleset and not claimed as zero-shot, AgentTrust achieves 96.7% verdict accuracy" | abstract | VERIFIED (keep "not zero-shot") |
| Look Before You Leap: 95.8% of invalid commands at 10.0% FPR | https://arxiv.org/abs/2609.11957 | "a static verifier over 9930 commands and 482 tools catches 95.8% of invalid commands at a 10.0% false-positive rate." | abstract | VERIFIED |
| ITBench: 13.8% of SRE scenarios resolved | https://arxiv.org/abs/2502.05352 | "agents powered by state-of-the-art models resolve only 13.8% of SRE scenarios, 25.2% of CISO scenarios, and 0% of FinOps scenarios." | abstract | VERIFIED |
| SREGym: 90 problems | https://arxiv.org/abs/2605.07161 | "SREGym currently includes 90 realistic, challenging SRE problems." | abstract | VERIFIED |
| WildClawBench: best model 62.2% | https://arxiv.org/abs/2605.10912 | "the best, Claude Opus 4.7, reaches only 62.2% overall under OpenClaw" | abstract | VERIFIED |
| Agent-SafetyBench: no agent above 60% | https://arxiv.org/abs/2412.14470 | "none of the agents achieves a safety score above 60%." | abstract | VERIFIED |
| Correlated Errors: 60% agreement when both err | https://arxiv.org/abs/2506.07962 | "on one leaderboard dataset, models agree 60% of the time when both models err." | abstract | VERIFIED |

## B. Attributed descriptions (non-numeric claims in the spec)

### B1. REMORA: ACCEPT/VERIFY/ABSTAIN/ESCALATE, proposal-bound grants, effect verification, "research software, not a paper". VERIFIED-WITH-CAVEAT
- Source: https://github.com/darklordVirtual/REMORA-research (README; cloned at commit 31c4060630923344d43d9fac26821150262c3687, 2026-09-29, v0.11.0)
- Quote: "it evaluates the exact action before it runs, and returns one of four decisions" (table: ACCEPT, VERIFY, ABSTAIN, ESCALATE).
- Quote: "An approval is bound to the exact proposal it was given for and is consumed once, at the policy-enforcement point, before governed dispatch."
- Quote: "Dispatch intent, outcome, effect verification and audit records stay joinable by proposal identity."
- Quote: "research and shadow-mode software with no production certification."
- Caveat 1: the repo also contains a paper (`paper/remora_paper.pdf`, linked by a README badge), so "not a paper" is inexact. Suggest: "research software with an accompanying paper in the repo; we found no peer-reviewed venue".
- Caveat 2: the license is BUSL-1.1 (source-available, not OSI open source), which matters for how we describe reuse.
- Caveat 3: REMORA's own README table row 1 reports "0.0% wrongly allowed (0/208) ... false-block rate on the benign twins 100.0% (208/208 blocked)" with the scope note "The gate blocked every scenario, harmful or benign". Do not quote its 0.0% figure without that context.

### B2. Bounded Autonomy: "typed contracts validated before side effects". VERIFIED
- Quote (abstract): "all executable behavior is constrained by typed action contracts, permission-aware capability exposure, scoped context, validation before side effects, consumer-side execution boundaries, and optional human approval."
- Not found in the abstract: any hash or signature binding of an approved action to what executes. docs/prior-art.md therefore marks its hash binding "not stated in the abstract" and not as absent.

### B3. AGT / ACS: "policy-gateway class (allow/block/redact/ask)". VERIFIED-WITH-CAVEAT
- Sources: https://github.com/microsoft/agent-governance-toolkit and https://microsoft.github.io/agent-governance-toolkit/packages/agent-control-specification/
- Quote (ACS page): "AGT's stateless, deterministic, fail-closed policy decision runtime"; verdicts Allow, Warn, Deny, Escalate, Transform; intervention points include `pre_tool_call` and `post_tool_call`.
- Quote (AGT README): "tamper-evident records of every decision: what policy was active, what the agent requested, and why it was allowed or denied."
- Caveat: the verdict names are allow/warn/deny/escalate/transform (the README policy file also uses `require_approval`), not "block/redact/ask". Suggest "allow/deny/require-approval/transform".

### B4. AgentTrust: "allow/warn/block/review, SafeFix, RiskChain, MCP server". VERIFIED
- Quote (abstract): "returns a structured verdict: allow, warn, block, or review. AgentTrust combines a shell deobfuscation normalizer, SafeFix suggestions for safer alternatives, RiskChain detection for multi-step attack chains, and a cache-aware LLM-as-Judge for ambiguous inputs." Also "provides a Model Context Protocol server for MCP-compatible agents." License AGPL-3.0.

### B5. Claude Code auto mode: "deployed tiered gate". VERIFIED
- Quote: "Tier 2: In-project file operations. File writes and edits inside the project directory are allowed without a classifier call." and "Tier 3: Transcript classifier. The transcript classifier sees everything else, including shell commands, web fetches, external tool integrations, subagent spawns, filesystem operations outside the project directory." Stage 1 is "a fast single-token (yes/no) filter instructed to err toward blocking; if it flags, stage 2 re-evaluates the same input with chain-of-thought reasoning to reduce false positives."

### B6. AgentHazard: "locally-plausible steps compose into harm". VERIFIED
- Quote: "harmful behavior may emerge through sequences of individually plausible steps, including intermediate actions that appear locally acceptable but collectively lead to unauthorized actions."

### B7. Agent Action Guard / HarmActionsEval: "action classifier + MCP proxy; preprint only". VERIFIED for "preprint only"; MCP proxy weak
- Source: https://github.com/Pro-GenAI/Agent-Action-Guard. The README describes a classifier that evaluates each tool call before execution and cites a preprint (doi 10.20944/preprints202510.1415.v2, Oct 2025). MCP integration exists but is thinly documented as a primary feature. Suggest softening "MCP proxy".

### B8. Ctrl-Z + ControlArena: "Bash/Infra settings with attack policies". VERIFIED
- Source: https://github.com/UKGovernmentBEIS/control-arena. Quotes: "Bash tasks from the CTRL-Z paper (based on Stack Overflow questions)"; Infra is a "training cluster kubernetes codebase". Attack policies are models "explicitly designed to pursue harmful side tasks". MIT licensed. Infra needs Kubernetes tooling, so it stays behind the Post 2 gate (CLAUDE.md rule 9).

### B9. WildClawBench: "side-effect auditing". VERIFIED
- Quote: "Grading is hybrid, combining deterministic rule-based checks, environment-state auditing of side effects, and an LLM/VLM judge for semantic verification."

## C. Spec descriptions that do not match their source (fix the spec or the post)

### C1. GRADE / auditable: "replays decision assumptions against live state, rolls back". NOT FOUND in the linked arXiv paper
- The paper https://arxiv.org/abs/2606.22741 is "GRADE: Graph Representation of LLM Agent Dependency and Execution". Its abstract is about typed graphs for failure prediction and says nothing about replay against live state or rollback. Abstract: "GRADE represents a run as one typed graph: execution edges come free from the trace, and dependency edges are supplied, each graded observed, declared, or inferred."
- The replay and rollback claim is in the GitHub repo https://github.com/yzhao062/auditable: "captures what each decision relied on, replays it against live state, and rolls back the committed action when it no longer holds." The repo says it is built on the GRADE paper.
- Fix: cite the repo (`auditable`) for replay and rollback, and the paper only for the dependency-graph representation. The paper's own result is largely null ("Within corpus it separates the recovered assignment from a degree-matched counterfeit on no corpus"), so do not cite it as evidence that outcome re-verification works.

### C2. "Ask the World Before Acting": "VoI probe selection". VERIFIED-WITH-CAVEAT (loose)
- Source: Song & Cai, https://arxiv.org/abs/2606.31422, "Ask the World Before Acting: Environment Probing for Calibrated Agent World Models". Quote: "We formulate environment probing as a budgeted decision problem for structured agent world models: before acting, the agent may query the current value of one belief field, update its table, and pay one interaction step. We introduce EnvProbe, a simple scoring policy that combines task criticality, staleness, verbalized uncertainty, and dependency role."
- Value of information appears as related work (its text: "Bayesian experimental design and adaptive submodularity formalize the value of information and greedy selection under uncertainty"), but the method is EnvProbe's heuristic score. It also reports "self-reported uncertainty is unreliable under confident wrong beliefs".
- Fix: say "budgeted environment probing (EnvProbe), related to value-of-information selection".

### C3. "Self-Attribution Bias, Correlated Errors: use a different model family for the verifier". Inference, not a direct finding
- https://arxiv.org/abs/2603.04582: "monitors fail to report high-risk or low-correctness actions more often when evaluation follows a previous assistant turn in which the action was generated". It does not test cross-family monitors, and says "explicitly stating that the action comes from the monitor does not by itself induce self-attribution bias".
- https://arxiv.org/abs/2506.07962: "larger and more accurate models have highly correlated errors, even with distinct architectures and providers." This weakens a simple "different family fixes it" argument.
- Fix: present the different-family verifier as our design choice motivated by these papers, and measure it (the spec's ablation does), not as an established result.

### C4. SREGym "(no harm measurement; our hook)". NOT FOUND (absence claim, unchecked)
- The abstract (https://arxiv.org/abs/2605.07161) describes fault injection and end-to-end results ("up to 40% differences in end-to-end results") and does not mention safety or harm measurement. Confirming an absence needs a read of the paper's metrics, which was not done.
- Fix: write "the abstract reports end-to-end resolution and does not mention harm; we found no harm metric" and confirm against the metrics section before Post 2.

### C5. "Look Before You Leap: safety/applicability frontier framing". VERIFIED-WITH-CAVEAT
- Abstract: "a refuse-when-unsure policy turns silent failures into recoverable ones at a tunable cost in applicability". The tradeoff is there; the word "frontier" is not in the abstract. Fine to borrow the framing; do not attribute the term to the paper without checking the body.

### C6. AMA-Bench "a memory benchmark, not a safety one". VERIFIED
- https://arxiv.org/abs/2602.22769, "AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications" (ICML 2026). Confirmed from search results, not read in full.

## D. Reading-list entries confirmed to exist (no numbers attributed)
- AgentDoG / ATBench https://arxiv.org/abs/2601.18491: "we introduce a new fine-grained agentic safety benchmark (ATBench) and a Diagnostic Guardrail framework for agent safety and security (AgentDoG)". Matches.
- LlamaFirewall https://arxiv.org/abs/2505.03574: "three powerful guardrails: PromptGuard 2 ... Agent Alignment Checks ... and CodeShield". Matches.
- Invariant https://github.com/invariantlabs-ai/invariant (now "Invariant Guardrails"): "a comprehensive rule-based guardrailing layer for LLM or MCP-powered AI applications. It is deployed between your application and your MCP servers or LLM provider". It is served through the separate `invariant-gateway` repo, which "automatically evaluates your rules on each LLM and MCP request (before and after)". The spec's "Invariant Gateway" link points at the guardrails repo.
- AIOpsLab https://arxiv.org/abs/2501.06706 and ToolEmu https://arxiv.org/abs/2309.15817 (abstract: "even the safest LM agent exhibits such failures 23.9% of the time according to our evaluator"): exist and match.
- Ask the World PDF link https://arxiv.org/pdf/2606.31422 resolves (see C2).
