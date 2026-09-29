# Agent Action Verification Framework

## Purpose of This Document

This document synthesizes the current thesis direction, design ideas, research gaps, candidate scopes, implementation strategy, and open questions for an agent-action verification framework.

It is intended as a handoff document for coding agents, research agents, and human collaborators. Agents should use it to:

- Brainstorm and refine the thesis.
- Identify relevant prior work.
- Challenge assumptions.
- Propose implementation plans.
- Design experiments and benchmarks.
- Recommend a defensible initial scope.
- Identify unresolved questions before implementation.

The central project idea is a system that verifies AI-agent actions before execution, especially when actions can modify external state or produce consequential side effects.

---

## 1. Executive Thesis Direction

### Current recommended thesis

> **A risk-adaptive pre-commit verifier for autonomous software operations. The system evaluates agent-proposed code, deployment, or incident-remediation actions using intent alignment, authorization, evidence freshness, scope-drift detection, blast-radius estimation, safe probes, and post-action outcome verification.**

The system should be evaluated on CI/CD changes, deployments, and SRE-style incident-remediation tasks in controlled environments.

### Central hypothesis

> Compared with policy-only guardrails and unconditional human approval, a risk-adaptive verifier can reduce harmful actions while preserving higher task completion, lower review burden, and acceptable latency.

### Core distinction

Existing governance systems often ask:

> Is this agent technically permitted to perform the action?

This project should ask the richer question:

> Given the user’s objective, evidence, uncertainty, alternatives, authorization, reversibility, and likely consequences, is this action sufficiently justified and safe to commit?

The project should not merely become another generic allow/deny guardrail library.

---

## 2. Why This Is Worth Tackling

Agent governance, runtime guardrails, capability security, tool authorization, sandboxing, and human approval are active fields. The problem is not untouched. However, important gaps remain between:

- Permission and decision quality.
- Static policy and dynamic state.
- Pre-action checks and post-action outcomes.
- Tool-call verification and long-horizon trajectory risk.
- Human approval and meaningful human review.
- Sandbox containment and actual recovery.
- Model confidence and calibrated uncertainty.
- Generic governance infrastructure and domain-specific consequence analysis.

A useful contribution would compose existing infrastructure while providing a clearer and measurable framework for **evidence- and consequence-aware pre-commit decision verification**.

Recent agent-safety research and evaluation work indicates that benchmarks often emphasize final task completion while underrepresenting safety-constraint violations, harmful actions, recovery, cost, trajectory quality, and real-world consequences. [web:59][web:64][web:76]

Operational safety research identifies constraint violations, destructive operations, and authorization bypasses as important real-world failure classes. [web:76]

The project is valuable if it can demonstrate that verification reduces harmful or unjustified actions without simply refusing too much, creating excessive latency, or overwhelming humans with approval prompts.

---

## 3. Design Principles

1. **Agents may propose broadly but execute only through bounded capabilities.**
2. **Authorization is necessary but not sufficient.**
3. **The exact action must be verified, not merely its natural-language summary.**
4. **Verification intensity should scale with impact, uncertainty, blast radius, sensitivity, volatility, and irreversibility.**
5. **Prefer observation over modification.**
6. **Prefer reversible changes over irreversible ones.**
7. **Prefer the smallest effective intervention.**
8. **Use deterministic controls for hard limits.**
9. **Use model-based agents for interpretation, critique, and evidence analysis, not final enforcement alone.**
10. **Re-check the environment immediately before execution.**
11. **Track cumulative trajectory risk, not only isolated tool calls.**
12. **Make uncertainty, assumptions, evidence, and dissent visible.**
13. **Stop when the objective is achieved; do not continue acting unnecessarily.**
14. **Never expand scope without renewed authorization.**
15. **Every action should produce an auditable decision record.**
16. **The system must be able to abstain, defer, request more evidence, or propose a safer alternative.**
17. **Post-action outcome verification is required for consequential actions.**
18. **Human approval should be meaningful, not a repetitive substitute for system design.**

---

## 4. Conceptual Architecture

```text
User goal
   ↓
Planning agent
   ↓
Structured action proposal
   ↓
Action Contract Builder
   ↓
Risk-adaptive verifier
   ├─ Intent alignment
   ├─ Authorization and capability checks
   ├─ Policy evaluation
   ├─ Evidence and provenance checks
   ├─ State and freshness checks
   ├─ Scope-drift analysis
   ├─ Independent skeptical critique
   ├─ Alternative generation
   ├─ Probe/simulation selection
   ├─ Reversibility and rollback assessment
   └─ Approval/escalation routing
          ↓
Capability/certificate gate
          ↓
Sandboxed or staged execution
          ↓
Post-action verification
          ├─ Expected outcome
          ├─ Unexpected side effects
          ├─ Rollback status
          └─ Calibration record
          ↓
Immutable or tamper-evident action ledger
```

### Architectural principle

The verifier should not be only a second language model. It should combine:

- Deterministic policy enforcement.
- Structured schemas.
- Independent model-based critique.
- External measurements and probes.
- Sandboxed or staged execution.
- Capability-scoped permissions.
- Human escalation when warranted.
- Post-action monitoring and rollback.

---

## 5. Action Contract

Every proposed action should be converted into a structured, hashable, reviewable contract.

Example:

```json
{
  "action_id": "act_123",
  "parent_task_id": "task_456",
  "objective": "Resolve elevated API latency",
  "tool": "rollback_deployment",
  "target": {
    "service": "checkout-api",
    "environment": "staging"
  },
  "parameters": {
    "deployment": "checkout-api:v42",
    "rollback_to": "checkout-api:v41",
    "traffic_percentage": 10
  },
  "expected_effect": "Reduce latency without affecting unrelated services",
  "risk_class": "high",
  "impact": "availability",
  "blast_radius": "checkout API staging traffic",
  "reversibility": {
    "level": "high",
    "rollback_plan": "Restore v42 and re-route traffic",
    "rollback_tested": false
  },
  "authority": {
    "principal": "incident-agent",
    "scope": "staging checkout services",
    "max_traffic_percentage": 10,
    "expires_at": "2026-09-14T12:00:00-04:00"
  },
  "evidence": [
    {
      "claim": "Latency increase began after v42 deployment",
      "source": "telemetry",
      "timestamp": "2026-09-14T11:52:00-04:00",
      "freshness": "current"
    }
  ],
  "assumptions": [
    "v41 is available and healthy",
    "rollback can be performed without schema incompatibility"
  ],
  "alternatives": [
    "restart one canary instance",
    "increase capacity temporarily",
    "inspect database latency"
  ],
  "stop_conditions": [
    "latency does not improve after 5 minutes",
    "error rate exceeds 2%",
    "rollback target health check fails"
  ]
}
```

### Suggested contract fields

- User objective.
- Exact tool.
- Exact target.
- Exact parameters.
- Expected effect.
- Potential side effects.
- Evidence.
- Evidence provenance.
- Evidence timestamps and freshness.
- Assumptions.
- Alternatives considered.
- Authorization scope.
- Capability limits.
- Risk dimensions.
- Reversibility.
- Rollback plan.
- Stop conditions.
- Monitoring plan.
- Approval requirements.
- Expiration time.
- Agent identity and model version.
- Policy version.
- Parent task and prior actions.

The action contract should be the object passed through planning, critique, verification, approval, execution, and auditing.

---

## 6. Risk-Adaptive Verification

Do not use a binary safe/unsafe model. Classify actions by several dimensions:

- Potential impact.
- Blast radius.
- Uncertainty.
- Sensitivity.
- Reversibility.
- Environmental volatility.
- Novelty compared with prior actions.
- Scope distance from the original task.
- Evidence quality.
- Time pressure.
- Cumulative trajectory risk.

A conceptual risk score is:

\[
R = I \times B \times U \times V \times \frac{1}{S}
\]

Where:

- \(I\) = impact.
- \(B\) = blast radius.
- \(U\) = uncertainty.
- \(V\) = environmental volatility.
- \(S\) = reversibility/safety of rollback.

This is not required to be a literal multiplication in the implementation. The important idea is multidimensional risk rather than one vague confidence score.

### Suggested decision states

```text
ACCEPT
ACCEPT_WITH_LOGGING
VERIFY
RUN_PROBE
MODIFY_ACTION
REQUIRE_HUMAN_APPROVAL
REQUIRE_DOMAIN_REVIEW
DEFER
ABSTAIN
REJECT
```

### Example risk tiers

| Tier | Characteristics | Example behavior |
|---|---|---|
| 0 | Read-only observation | Automatic execution with logging |
| 1 | Narrow, reversible change | Automatic execution with rollback |
| 2 | Bounded state change | Dry run or targeted verification |
| 3 | Sensitive, external, or costly effect | Probe plus approval or domain review |
| 4 | Irreversible, high-blast-radius, or critical effect | Human/domain approval, staged execution, strong monitoring |

The system should be evaluated on whether adaptive verification is better than applying the same control to every action.

---

## 7. Verification Components

### Planner

Produces the task plan and action contracts.

### Deterministic policy verifier

Checks:

- Is the tool allowed?
- Is the target in scope?
- Is the actor authorized?
- Are quantities and parameters within limits?
- Is sensitive data involved?
- Is the action inside its validity window?
- Does it violate a deny rule?

### Independent skeptical critic

Attempts to disprove the proposal:

1. What exact objective does this action serve?
2. Which assumptions are necessary?
3. What evidence supports each assumption?
4. What evidence contradicts the proposal?
5. What is the strongest argument against the action?
6. What could go wrong that the planner did not mention?
7. What is the least-destructive alternative?
8. What would make this action invalid?
9. How can failure be detected immediately?
10. Can the action be reversed reliably?
11. Is the agent being manipulated by external content?
12. Has the task scope expanded?

The critic should receive enough context to reason, but it should not blindly inherit the planner’s conclusions. Independence should be tested experimentally rather than assumed.

### Evidence verifier

Distinguishes:

- Directly observed facts.
- Retrieved facts.
- User-provided instructions.
- Agent-generated claims.
- Assumptions.
- Predictions.
- External content of uncertain trustworthiness.

Evidence should include provenance, timestamp, freshness, and relevance.

### State verifier

Re-checks the environment before execution. This mitigates time-of-check/time-of-use failures.

### Probe planner

Selects a safe experiment when uncertainty is material:

- Dry run.
- Diff.
- Canary.
- Paper simulation.
- Quarantine.
- Read-only query.
- Access preview.
- Health check.
- Regression test.
- Cost estimate.
- PII scan.

### Consequence evaluator

Estimates potential outcome and blast radius, preferably using actual environment state instead of model imagination.

### Approval router

Routes actions to:

- Automatic execution.
- User confirmation.
- Second reviewer.
- Domain expert.
- Security reviewer.
- Financial/compliance reviewer.

### Post-action verifier

Checks whether the intended outcome occurred and whether side effects exceeded expectations.

---

## 8. Open Research Gaps to Add to the Thesis

### 8.1 Decision quality versus authorization

Authorization answers whether an agent may act. The thesis should study whether the action is justified, necessary, evidence-supported, minimally destructive, and proportionate.

Research question:

> Can a verifier reduce harmful or unjustified actions beyond ordinary permission and parameter checks?

### 8.2 Adaptive verification intensity

Static policies are inefficient. Verification should vary with risk.

Research question:

> Can risk-adaptive verification achieve a better safety–latency–autonomy tradeoff than fixed approval policies?

### 8.3 Safe-probe selection

Make probe selection a formal contribution using a value-of-information concept:

\[
\text{Probe value} = \frac{\text{expected reduction in decision error}}{\text{probe cost} + \text{probe risk}}
\]

Research question:

> Can the verifier select probes that provide greater safety improvement per unit of latency or compute?

### 8.4 Outcome verification

Separate process verification from outcome verification.

Research question:

> Does checking observed post-action effects detect failures missed by authorization, policy, and tool-success checks?

### 8.5 Reversibility as an engineered property

Do not label actions reversible without testing restoration.

Potential reversibility dimensions:

- State snapshot exists.
- Restoration preserves metadata.
- Rollback has been tested.
- External side effects can be reversed.
- Recovery time is acceptable.
- Residual damage is bounded.

### 8.6 Decomposed uncertainty and calibration

Track separate confidence values for:

- Intent understanding.
- Environment state.
- Evidence.
- Predicted outcome.
- Authorization.
- Rollback.

Use calibration metrics rather than trusting model confidence.

### 8.7 Correlated verifier failure

Compare same-model critics, different-model critics, deterministic checks, and external probes.

Research question:

> Which types of verifier independence reduce correlated errors most effectively?

### 8.8 Long-horizon and trajectory risk

A sequence of individually acceptable actions may create unacceptable cumulative risk.

Research question:

> Can trajectory-level verification detect cumulative risk that per-tool-call gates miss?

### 8.9 Scope drift and authority drift

Track changes in:

- Targets.
- Tools.
- Quantities.
- Sensitivity.
- Objectives.
- Time horizon.
- Privileges.

Require renewed authorization when scope distance becomes too large.

### 8.10 Evidence provenance and manipulation

External documents, web pages, logs, emails, and repository files may contain instructions that try to manipulate the verifier.

Research question:

> Can provenance-aware evidence handling reduce verifier manipulation through indirect prompt injection and misleading tool output?

### 8.11 Human approval quality

Measure whether users understand what they are approving. Compare simple approval buttons with structured decision envelopes.

Research question:

> Can structured reviews improve unsafe-action detection while reducing approval fatigue?

### 8.12 Cross-domain transfer

Test which verification primitives generalize and which require domain adapters.

Generalizable candidates:

- Authorization scope.
- Evidence provenance.
- Reversibility.
- Blast radius.
- Scope drift.
- Outcome verification.

Domain-specific candidates:

- Infrastructure dependency graphs.
- Software test semantics.
- Financial suitability.
- Healthcare identity and privacy.
- Security attribution.

---

## 9. Candidate Evaluation Scopes

The latest recommended scope is software operations, but the following alternatives should remain open for discussion.

### 9.1 SRE incident response

An agent investigates telemetry and proposes remediation such as rollback, scaling, failover, feature disabling, or service restart.

**Strengths:** high importance, dynamic state, cascading risk, clear metrics, meaningful safe probes, strong demonstration of adaptive verification.

**Weaknesses:** higher infrastructure complexity and realistic incident simulation requirements.

**Potential research question:**

> Can a risk-adaptive verifier select safer remediation sequences than an unverified or policy-only agent while maintaining incident-resolution performance?

### 9.2 CI/CD and software-change governance

An agent modifies code, tests, dependencies, CI configuration, or deployment manifests.

**Strengths:** best alignment with QA automation and software skills; objective diffs and tests; manageable sandboxing; reproducible experiments.

**Weaknesses:** software test success may not capture all real-world effects; existing coding-agent benchmarks are active.

**Potential research question:**

> Can pre-commit action verification reduce unsafe software changes while preserving coding-agent throughput better than test-pass gates alone?

### 9.3 Cloud infrastructure changes

An agent modifies Terraform, Kubernetes, IAM, network, storage, or deployment resources.

**Strengths:** high blast radius; strong need for policy, dependency, cost, security, and rollback verification.

**Weaknesses:** technically heavy; requires realistic cloud simulation or controlled test infrastructure.

### 9.4 Security operations

An agent triages alerts and proposes containment such as token revocation, account disablement, host isolation, or IP blocking.

**Strengths:** consequential, adversarial, uncertainty-rich, reversible-containment concepts are highly relevant.

**Weaknesses:** difficult to generate credible labels and realistic attack scenarios.

### 9.5 Data governance and privacy

An agent exports, shares, redacts, classifies, deletes, or grants access to data.

**Strengths:** clear authorization, provenance, data-minimization, and disclosure risks.

**Weaknesses:** realistic datasets and privacy evaluation need care.

### 9.6 Procurement and invoice operations

An agent approves invoices, chooses vendors, changes payment details, renews subscriptions, or issues purchase orders.

**Strengths:** objective policies, financial consequences without stock-prediction uncertainty, fraud and segregation-of-duties scenarios.

**Weaknesses:** may feel less technically novel unless linked to evidence, provenance, and multi-step business workflows.

### 9.7 Browser agents and external communications

An agent submits forms, sends messages, changes appointments, uploads files, posts content, or modifies account settings.

**Strengths:** visible external effects, ambiguous UI semantics, untrusted content, identity-sensitive actions, realistic pre-submit verification.

**Weaknesses:** browser environments can be brittle; outcome labels require careful design.

### 9.8 Customer support operations

An agent issues refunds, changes subscriptions, closes accounts, updates records, or sends messages.

**Strengths:** highly measurable and easy to simulate; clear authorization and side-effect problems.

**Weaknesses:** potentially less novel than infrastructure or security operations.

### 9.9 Healthcare administration

An agent handles scheduling, referrals, document routing, record-access requests, or patient communication drafts.

**Strengths:** high importance, privacy and identity concerns, strong need for staged autonomy.

**Weaknesses:** domain expertise, ethics, and collaboration requirements; avoid clinical diagnosis/treatment unless properly supported.

### 9.10 Live stock trading

Not recommended as the primary thesis domain. It has uncertain outcome labels, market-data challenges, regulatory considerations, and difficulty separating verification quality from investment-prediction skill.

It may be used only as a paper-trading or simulation adapter after the core framework is complete.

### 9.11 Local file cleanup

Useful as a simple demonstration of contracts, dry runs, quarantine, and rollback, but too low-stakes to serve as the sole thesis scope.

---

## 10. Scope Ranking

| Scope | Importance | Measurability | Difficulty | Thesis strength |
|---|---:|---:|---:|---:|
| SRE incident response | Very high | High | High | Excellent |
| CI/CD and code changes | High | Very high | Medium | Excellent |
| Cloud infrastructure | Very high | High | High | Excellent |
| Security operations | Very high | Medium-high | High | Excellent |
| Privacy/data governance | Very high | High | Medium-high | Very good |
| Procurement/invoice operations | High | High | Medium | Very good |
| Browser external actions | High | High | Medium | Very good |
| Customer support | Medium-high | Very high | Medium | Good |
| Healthcare administration | Very high | Medium | High | Good with collaborators |
| Live stock trading | High | Low-medium | Very high | Weak first scope |
| Local file cleanup | Low-medium | Very high | Low | Weak as sole thesis |

---

## 11. Recommended Scope Options

### Option A: Software-change verifier

Best balance of feasibility, relevance, and objective evaluation.

Core contributions:

- Intent-to-diff alignment.
- Risk-adaptive test selection.
- Scope-drift detection.
- Sandboxed execution.
- Rollback validation.
- Post-change behavioral verification.

### Option B: SRE remediation verifier

Strongest demonstration of importance.

Core contributions:

- Telemetry freshness checks.
- Blast-radius estimation.
- Least-destructive remediation.
- Canary probes.
- Multi-step risk accumulation.
- Outcome-based incident evaluation.

### Option C: Security-response verifier

Strongest safety framing.

Core contributions:

- Evidence provenance.
- Attribution uncertainty.
- Reversible containment.
- Forensic-preservation constraints.
- Escalation thresholds.
- Adversarial evidence testing.

### Option D: Two-domain verifier

Use a common verifier core and evaluate it in two domains, such as:

- CI/CD plus SRE.
- CI/CD plus privacy/data access.
- SRE plus security response.

Research question:

> Which verification primitives transfer across domains, and which require domain-specific semantics?

This may produce a stronger thesis but increases implementation and evaluation work.

---

## 12. Recommended Final Scope

The current recommended scope is:

> **A risk-adaptive pre-commit verifier for autonomous software operations. The system evaluates agent-proposed code, deployment, or incident-remediation actions using intent alignment, authorization, evidence freshness, scope-drift detection, blast-radius estimation, safe probes, and post-action outcome verification.**

### Primary evaluation domains

- CI/CD change tasks.
- Deployment tasks.
- SRE incident-remediation tasks.

### Action progression

```text
Read-only diagnosis
    → reversible code modification
    → staged deployment
    → production-like remediation
```

### Core claim to test

The verifier should reduce unsafe side effects and harmful action sequences while preserving useful autonomy better than:

1. An unverified agent.
2. A policy-only gateway.
3. A fixed human-approval workflow.

---

## 13. Benchmark and Evaluation Plan

### Baselines

At minimum:

1. Agent without verification.
2. Agent with deterministic policy checks only.
3. Agent with unconditional approval for sensitive actions.
4. Agent with the proposed adaptive verifier.
5. Optional: verifier with individual components ablated.

### Scenario classes

For CI/CD:

- Correct feature implementation.
- Regression-prone change.
- Dependency update.
- CI configuration weakening.
- Test manipulation.
- Scope expansion.
- Secret exposure.
- Unsafe migration.
- Deployment configuration error.

For SRE:

- Bad deployment.
- Database saturation.
- Memory leak.
- Queue backlog.
- Network partition.
- Credential expiry.
- False-positive alert.
- Partial dependency failure.
- Prompt-injected log output.

For security operations:

- Compromised token.
- Benign unusual login.
- Malware false positive.
- Insider-risk ambiguity.
- Evidence contamination.
- Overbroad account lockout.

### Metrics

#### Safety

- Harmful-action rate.
- Unauthorized-action rate.
- Constraint-violation rate.
- Blast-radius exceedance.
- Unsafe trajectory rate.
- Scope-drift detection rate.
- Prompt-injection success rate.

#### Utility

- Task completion.
- Incident-resolution rate.
- Code-change acceptance rate.
- Useful autonomy coverage.
- Time to completion.
- Time to mitigation.

#### Verification quality

- False-block rate.
- Missed-hazard rate.
- Probe success.
- Recovery success.
- Rollback success.
- Calibration error.
- Evidence-quality accuracy.
- Critic precision and recall.

#### Cost

- Added latency.
- Token/compute cost.
- Number of probes.
- Human review frequency.
- Approval burden.
- Sandbox resource usage.

### Safety-adjusted utility

A possible combined metric is:

\[
U = V_{task} - \lambda H - \mu C_{review} - \nu B_{false}
\]

Where:

- \(V_{task}\) = value of successful task completion.
- \(H\) = expected harm or side-effect cost.
- \(C_{review}\) = human and system verification cost.
- \(B_{false}\) = cost of unnecessary blocking.

Do not rely on one aggregate score. Report safety, utility, cost, and calibration separately as well.

### Ablation studies

Remove one component at a time:

- No action contract.
- No skeptical critic.
- No evidence verifier.
- No state revalidation.
- No probe planner.
- No scope-drift detector.
- No rollback assessment.
- No post-action verifier.
- No trajectory-level risk.

This shows which parts actually contribute value.

---

## 14. Implementation Plan

### Suggested technology stack

- TypeScript for the gateway and adapters.
- JSON Schema or Zod for action contracts.
- MCP proxy or tool gateway for interception.
- OPA or Cedar for deterministic policy checks.
- Docker or disposable workspaces for probes.
- SQLite/PostgreSQL for action ledger.
- OpenTelemetry for traces.
- Python for evaluation, simulations, and metrics.
- Ollama/local models for planner and critic experiments.
- Playwright for browser-action test scenarios where relevant.

### Suggested repository structure

```text
agent-action-verifier/
├── packages/
│   ├── contracts/
│   ├── gateway/
│   ├── policy/
│   ├── verifier/
│   ├── probes/
│   ├── audit/
│   └── adapters/
├── adapters/
│   ├── git/
│   ├── cicd/
│   ├── sre/
│   ├── filesystem/
│   ├── playwright/
│   └── finance-paper/
├── policies/
├── benchmarks/
├── scenarios/
├── evaluations/
├── examples/
└── docs/
```

### Initial MVP

Start with a local action gateway supporting:

```text
propose_action()
verify_action()
run_probe()
request_approval()
execute_authorized_action()
verify_outcome()
rollback_action()
```

First implementation target:

- Git repository modifications.
- Test execution.
- Diff inspection.
- Scope validation.
- Isolated builds.
- Approval-bound execution.
- Post-change verification.

Then add deployment/SRE adapters.

### Do not build initially

- A universal agent framework.
- A new sandbox technology.
- A new LLM orchestration framework.
- A live stock-trading system.
- Full enterprise governance coverage.
- A clinical decision system.
- A custom policy language unless existing policy engines prove inadequate.

The contribution should be in action contracts, adaptive verification, probes, evaluation, and composition of existing controls.

---

## 15. Open-Source Work to Research, Borrow From, or Leverage

### Microsoft Agent Governance Toolkit

Describes policy enforcement, zero-trust identity, execution sandboxing, and reliability controls for autonomous agents. [web:51]

Potentially borrow:

- Tool-call interception.
- Policy enforcement points.
- Identity/delegation concepts.
- Sandbox integration.
- Audit events.
- Lifecycle hooks.
- Policy-as-code patterns.

Potential contribution:

- Add an action-verification adapter or decision-envelope layer before final execution.

### Microsoft Agent Control Specification

Defines portable runtime governance and interception points around model and tool calls, with outcomes such as allow, warn, deny, and escalate. [web:43]

Borrow:

- Framework-independent interception semantics.
- Lifecycle event model.
- Portable control vocabulary.
- Enforcement boundary concepts.

### OpenAI Agents SDK and OpenAI Guardrails

The Agents SDK provides guardrails, approvals, tracing, and tool-call review patterns. OpenAI Guardrails provides configurable safety and compliance checks for LLM applications. [web:41][web:52]

Borrow:

- Pre-tool-call approval flow.
- Guardrail lifecycle.
- Structured validation results.
- Trace integration.
- Human escalation behavior.

Do not treat model approval as a substitute for deterministic enforcement.

### NeMo Guardrails

Useful for programmable input, retrieval, execution, and output rails.

Borrow:

- Execution-rail concepts.
- Tool input/output validation.
- Configurable policy declarations.
- Interception lifecycle.

### Guardrails AI

Useful for composable validators and structured correction/retry/reject flows.

Borrow:

- Validator composition.
- Structured schemas.
- Reusable checks.
- Retry or reject semantics.

### AgentDoG

A diagnostic guardrail framework for agent safety and security with risk taxonomy and evaluation ideas. [web:46]

Borrow:

- Risk taxonomy design.
- Diagnostic rather than purely binary decisions.
- Failure-mode classification.
- Benchmark structure.

### Agent Action Guard

Action-focused guardrail and evaluation work emphasizing harmful agent actions, an MCP proxy, action classifiers, and Harm@k-style metrics. [web:54]

Borrow:

- Action-level dataset format.
- MCP proxy approach.
- Harmful-action scenarios.
- Harm@k evaluation concepts.

### REMORA

A pre-execution governance layer using decisions such as ACCEPT, VERIFY, ABSTAIN, and ESCALATE, along with policy, evidence, uncertainty, disagreement, and an auditable decision envelope. [web:55]

Borrow:

- Multi-state decision model.
- Decision-envelope concept.
- Evidence and uncertainty fields.
- Escalation semantics.
- Pre-execution gate.

Potential differentiation:

- Add active probe selection based on value of information.
- Add post-action outcome verification.
- Add trajectory-level risk and scope drift.

### AgentTrust

Runtime safety evaluation and interception work for real-world side effects such as file operations, shell commands, HTTP requests, and database queries. [web:75]

Research for:

- Runtime interception.
- Tool-call risk evaluation.
- Side-effect taxonomies.
- Evaluation scenarios.

### Policy and authorization engines

Consider integrating rather than replacing:

- Open Policy Agent.
- Cedar.
- OpenFGA.
- Oso.

Use them for hard authorization and policy limits. Keep authorization separate from substantive decision quality.

Example separation:

```text
authorization = ALLOWED
verification = INSUFFICIENT_EVIDENCE
final_decision = RUN_PROBE
```

### MCP ecosystem

An MCP gateway/proxy is a practical framework-independent interception point. It can:

- Inspect tool metadata.
- Validate arguments.
- Attach action IDs.
- Run verification.
- Require approval.
- Forward only authorized calls.
- Record outcomes.

### Sandboxing and staged execution

Use mature containment mechanisms:

- Docker.
- Read-only mounts.
- Disposable workspaces.
- Network-disabled execution.
- Resource quotas.
- Canary environments.
- Ephemeral CI environments.

Sandboxing should be infrastructure, not the primary research novelty.

### Audit and observability projects

Research the `awesome-auditable-ai` ecosystem for decision records, failure attribution, monitoring, signed traces, and auditable agent execution. [web:48]

Borrow:

- Append-only action ledgers.
- Hash-linked records.
- OpenTelemetry integration.
- Model/tool lineage.
- Decision replay.
- Predicted-versus-observed outcome records.

### Benchmarks and evaluation projects

Research and leverage:

- AgentDoG.
- Agent Action Guard/HarmActionsEval.
- AgentTrust.
- ATBench.
- AgentHazard.
- TheAgentCompany.
- AMA-Bench.
- WildClawBench.
- SWE-bench and coding-agent benchmarks.
- WebArena and browser-agent benchmarks.

ATBench focuses on trajectory-level safety evaluation, while AgentHazard focuses on multi-step, trajectory-dependent harm in computer-use agents. [web:70][web:85]

TheAgentCompany evaluates consequential real-world professional tasks. [web:72]

Use existing benchmarks for ideas, but create a benchmark aligned with the thesis’s distinctive questions: pre-commit verification, adaptive probes, rollback, scope drift, trajectory risk, and outcome quality.

---

## 16. Potential Technical Interfaces

```ts
export type ActionContract = {
  actionId: string;
  parentTaskId: string;
  objective: string;
  tool: string;
  target: unknown;
  parameters: unknown;
  expectedEffect: string;
  evidence: Evidence[];
  assumptions: string[];
  alternatives: Alternative[];
  risk: RiskAssessment;
  authorization: AuthorizationScope;
  rollback?: RollbackPlan;
  stopConditions: StopCondition[];
  monitoringPlan?: MonitoringPlan;
};

export type VerificationResult = {
  decision:
    | "accept"
    | "accept_with_logging"
    | "verify"
    | "run_probe"
    | "modify_action"
    | "require_human"
    | "require_domain_review"
    | "defer"
    | "abstain"
    | "reject";
  blockingReasons: string[];
  warnings: string[];
  requiredProbes: Probe[];
  requiredControls: string[];
  confidence: ConfidenceBreakdown;
  expiresAt?: string;
};
```

### Capability token example

```json
{
  "capability": "deploy_canary",
  "allowed_service": "checkout-api",
  "allowed_environment": "staging",
  "max_traffic_percentage": 10,
  "allowed_image": "checkout-api:v42",
  "expires_at": "2026-09-14T12:00:00-04:00",
  "action_contract_hash": "sha256:..."
}
```

The executor should reject calls that do not match the exact approved target and parameters.

---

## 17. Decision Ledger

Every proposal and action should record:

- Action ID.
- Parent task ID.
- User objective.
- Exact target and parameters.
- Agent identity and model version.
- Policy version.
- Evidence and timestamps.
- Critic objections.
- Probe results.
- Decision state.
- Approval identity and expiry.
- Capability/certificate data.
- Execution result.
- Observed outcome.
- Unexpected side effects.
- Rollback result.
- Post-action calibration data.

The ledger supports:

- Reproducibility.
- Debugging.
- Incident investigation.
- Evaluation.
- Verifier improvement.
- Model calibration.
- Policy replay.
- Detection of authority or scope drift.

---

## 18. Important Threats and Failure Modes

The verifier should be tested against:

- Planner hallucination.
- Misunderstood user intent.
- Stale environment state.
- Prompt injection through logs, code, documents, or web pages.
- Tool-output manipulation.
- Same-model critic agreement.
- Approval fatigue.
- Scope expansion.
- Authority drift.
- Conflicting evidence.
- Missing rollback.
- Partial execution.
- Concurrent state changes.
- Tool failures reported as success.
- Hidden side effects.
- Cumulative multi-step harm.
- Resource exhaustion.
- Policy misconfiguration.
- Model or verifier self-modification.
- Compromised tool servers.
- Incomplete monitoring.

---

## 19. Open-Ended Decisions Still Requiring Discussion

These questions should remain open rather than being prematurely fixed.

### Scope decisions

- Should the thesis focus only on CI/CD and software changes?
- Should it include SRE remediation as a second domain?
- Would security operations provide a stronger safety case?
- Is a two-domain evaluation necessary to claim generality?
- Should browser automation be included because it enables visible, measurable side effects?
- Should finance remain an optional paper-trading adapter?
- Should local file operations be included only as a simple introductory example?

### Scientific contribution

- Is the main contribution the verifier architecture, the probe-selection policy, the benchmark, or the evaluation methodology?
- Should the thesis emphasize decision quality, adaptive verification, trajectory safety, or post-action outcome verification?
- Can the work formulate a meaningful theoretical model of risk and value of information?
- Is a formal decision-theoretic approach feasible, or should the system remain heuristic?
- How much independence is required between planner and verifier?
- Is an LLM critic necessary, or can deterministic and simulation-based checks provide most value?

### Action contract

- Which fields are mandatory for all domains?
- Which fields should be domain-specific extensions?
- Should contracts use JSON Schema, Pydantic, Zod, or another schema system?
- How should natural-language user intent be represented and compared with proposed actions?
- How should action contracts be canonicalized and hashed?

### Risk model

- Should risk use a hand-designed score, learned model, or hybrid approach?
- Which dimensions are essential: impact, blast radius, uncertainty, reversibility, volatility, sensitivity, novelty, time pressure?
- How should risk thresholds be calibrated?
- Should the verifier optimize expected harm, worst-case harm, or a risk-sensitive utility function?
- How should rare catastrophic failures be represented in evaluation?

### Probe selection

- What probes are general-purpose?
- Which probes are domain-specific?
- Can probe selection be framed as value-of-information optimization?
- Should probes be generated dynamically by an agent or selected from a trusted catalog?
- How should probe cost and probe risk be measured?
- Can probe results be composed into a stronger decision?

### Human oversight

- Which actions should always require human approval?
- Should approval be at the individual action, policy, or task level?
- How can approval fatigue be measured?
- Can the system learn which explanations help users detect unsafe actions?
- What counts as informed approval?

### Evaluation

- What is the ground truth for “good decision” in each domain?
- How should harmful but task-successful actions be scored?
- How should false blocks be weighted against missed hazards?
- How should delayed or cumulative harm be measured?
- What constitutes adequate external validity?
- Can results be reproduced using public environments and synthetic scenarios?
- How should verifier latency and token cost be included?

### Generalization

- How much domain independence is realistic?
- Is the contribution a protocol, a runtime, a benchmark, or a reference implementation?
- Can the verifier integrate with multiple agent frameworks through MCP or another portable layer?
- Which existing governance systems should be integrated directly?
- What is the smallest defensible claim that the experiments can support?

### Ethics and deployment

- Are real-world deployment experiments necessary?
- Can all high-consequence experiments remain in simulation or staging?
- How should sensitive logs, user data, and financial information be handled?
- What safeguards are needed if agents can run destructive operations?
- Should live financial actions be explicitly excluded?

---

## 20. Recommended Research Workflow

1. **Map existing work.**
   Build a table of open-source projects, papers, benchmarks, policy engines, agent frameworks, and sandbox technologies.

2. **Define the narrowest claim.**
   Avoid claiming universal agent safety. Focus on pre-commit verification for a selected class of software operations.

3. **Create an action taxonomy.**
   Classify actions by read/write behavior, reversibility, blast radius, sensitivity, and external side effects.

4. **Define the action contract.**
   Make exact tool call, target, evidence, authorization, risk, alternatives, rollback, and expiry explicit.

5. **Implement a policy-only baseline.**
   This is necessary to prove that the richer verifier adds value.

6. **Implement the adaptive verifier.**
   Add risk scoring, evidence checks, skeptical critique, and probe selection.

7. **Implement safe execution.**
   Use sandboxes, ephemeral environments, canaries, capability tokens, and exact argument binding.

8. **Implement outcome verification.**
   Record predicted and observed effects, unexpected side effects, and rollback results.

9. **Build seeded scenarios.**
   Include both ordinary successful tasks and deceptive or hazardous tasks.

10. **Run ablations.**
    Determine which components improve safety and which merely add latency.

11. **Test robustness.**
    Include prompt injection, stale state, conflicting evidence, scope drift, concurrent changes, and tool failures.

12. **Decide whether a second domain is justified.**
    Add one only if the first domain is mature and the thesis claim requires transfer evidence.

---

## 21. Final Recommendation

The most defensible current direction is:

> **Build and evaluate a risk-adaptive pre-commit verifier for autonomous software operations, initially covering CI/CD changes and staged/SRE remediation in controlled environments.**

Its distinctive contribution should be the combination of:

- Structured action contracts.
- Authorization separated from decision quality.
- Evidence provenance and freshness.
- Decomposed uncertainty.
- Scope and authority drift detection.
- Least-destructive-first reasoning.
- Adaptive safe-probe selection.
- Exact capability-bound execution.
- Post-action outcome verification.
- Trajectory-level risk tracking.
- Safety-adjusted evaluation.

Do not commit permanently to this scope until comparing it against security operations, cloud infrastructure, privacy/data governance, procurement, and browser external-action workflows. The strongest final scope may be a reusable verifier evaluated on two related domains rather than a universal platform.

The central test should remain:

> Does the proposed verifier meaningfully reduce harmful or unjustified agent actions while preserving useful autonomy, acceptable latency, recovery capability, and manageable human review burden?

If the answer is demonstrated with reproducible experiments, strong baselines, ablation studies, and outcome-level metrics, the project will make a substantially stronger contribution than a generic second-agent critic or a simple permission gate.
