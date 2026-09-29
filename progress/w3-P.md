# W3-P: Post 0 draft, README, architecture, frozen eval plan
**Status:** done (placeholders left for L's results)   **Branch:** w3/P

## Built
- `blog/post-0.md`: Post 0 draft, "Which pre-commit checks actually earn their cost?" 2,496 words by `wc -w` (which counts table pipes and URLs; about 2,300 words of prose). Sections: problem, what exists, design (trust boundary first), demo, frozen plan, not done yet, what's next.
- `docs/post1-eval-plan.md`: the frozen Post 1 plan from the spec's "Post 1 bar", with an "Open before the tag" list.
- `docs/architecture.md`: Mermaid data-flow diagram, trust-boundary table, decision table, tier/probe table, module map.
- `README.md`: pitch, quickstart (WSL + Docker, `make setup`, `make probe-image`, `make demo`), a condensed Mermaid diagram, design notes, roadmap.

## Decisions
- **Numbers in the post:** only VERIFIED or VERIFIED-WITH-CAVEAT rows of `blog/citations.md`, in R's corrected wording: 93% (A3); 0.4% FPR on real traffic n=10,000 and 17% FNR on real overeager n=52, called out as different populations (A4); 81.0% (CI 73.8–87.4%) on AmPermBench, a stress test that the authors say isn't comparable to the 17% (A1); 93/253 = 36.8% "never evaluated by the classifier, by design", not "bypassed" (A2); AgentHazard 73.63% (A5); Bounded Autonomy 23/25 with its two escaped mutations (A7). GRADE's replay/rollback is credited to the `auditable` repo (C1); AGT verdicts are allow/warn/deny/escalate/transform (B3); REMORA is "research software with a paper in the repo, BUSL-1.1" (B1). The different-family critic is presented as a design choice to be measured (C3). SHADE-Arena, Ctrl-Z and CaMeL's numbers weren't needed and aren't quoted.
- **Demo text** comes from a `make demo` run in this worktree (synthetic fixtures) and the ledger reason strings (`~/av-data/ledgers/replay-20260929T192338/*.db`). Its wall time is **not** quoted; M1 is L's measurement.
- **Known limitations:** all 8 strict xfails (7 from B, plus the owner's Deviation 1 xfail) appear in "Not done yet", along with the merge's unverified items (sandbox cap enforcement, concurrent ledger writers, OPA latency) and the false-block sources B listed.
- **Differentiation sentence:** one sentence covering REMORA and auto mode, built from `docs/prior-art.md`'s two sentences.
- **Eval plan:** metric definitions (harm rate, completion, false blocks, and so on) and "paired bootstrap over tasks" are my operationalisation of the spec's list. The spec names the metrics but doesn't define them. Proposed defaults for two open items (the REMORA state mapping, and which tasks the primary comparison uses) are written as **proposals** under "Open before the tag", not as settled plan.
- README quickstart includes `make probe-image`: without the image every run_tests probe defers (w2-merge handoff).

## Deviations
None from PLAN. Spec conflicts are flagged, not resolved:
1. **Spec wording vs citations** (spec Context and reading list): "81% FNR on DevOps scope escalation", "36.8% bypassed", "0.4% / 17%" as one classifier result, GRADE replay/rollback, AGT "allow/block/redact/ask". The post uses R's corrected wording; the spec text itself is the owner's to fix.
2. **Tainted params → reject** (spec defaults table) vs the implemented rule (substring-only overlap in an ordinary file is logged; owner decided KEEP). The post and README describe the implemented behaviour and list it as a known miss.
3. **Primary comparison vs tuning:** the spec runs all 6 conditions on all ~40 tasks, but tuning uses the dev split, so a primary number over all 40 tasks mixes tuned-on and held-out tasks. It's listed as open item 2 in the eval plan with a proposed resolution; the owner decides before `post1-frozen`.
4. **Condition 5 label:** the spec says "REMORA-style"; per R's verdict the plan says "REMORA (run, decision function only)", and notes the "REMORA-style (reimplemented)" fallback isn't needed.

## Tests
No code changed. `uv run pytest -q`: 427 passed, 8 xfailed. `make demo` (replay): benign accept, injection blocked (provenance), scope_drift blocked (scope drift), hosted calls: 0.

## Interface requests
None.

## Cost / quota
0 hosted calls, 0 Ollama calls.

## Handoff
Placeholders for the Wave 3 merge to fill from L's files (`reports/post0-measurements.md`, `progress/w3-L.md`, the `proposals.jsonl` headers):

| Placeholder | Where | Fill with |
|---|---|---|
| `{{BUDGET}}` | post-0.md, post1-eval-plan.md §7 | measured calls/tokens per episode and the 320-episode projection (days at 300/day; whether >25% over 3k–6k) |
| `{{FIXTURE_ORIGINS}}` | post-0.md (×2), README.md | per scenario: recorded (model, date) or synthetic (and why) |
| `{{M1_DEMO_TIME}}` | post-0.md, README.md | fresh-clone `make demo` wall time |
| `{{MODEL}}` | post-0.md | hosted model used live |
| `{{LIVE_EPISODE_COST}}` | post-0.md | M11: calls and tokens for one live episode |
| `{{DEMO_GIF}}` | post-0.md | owner's asciinema/GIF |
| `{{REPO_URL}}` | post-0.md, README.md | public GitHub URL (owner) |

- If L re-records a fixture and the model behaves differently (for example it never edits CI), rewrite the matching demo bullet in post-0.md and the README scenario table. Both describe the current synthetic fixtures.
- After filling, re-check post-0.md's length (≤ 2,500 words; it's at 2,496 by `wc -w` before filling, so trim if a placeholder fills long).
- Before `post1-frozen`: close the four "Open before the tag" items in `docs/post1-eval-plan.md`.
