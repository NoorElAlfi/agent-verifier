# W2-R: Prior art and citations
**Status:** done   **Branch:** w2/R

## Built
- `blog/citations.md`: every number and attributed claim in the spec's reading list, with URL, verbatim quote, location and a verdict.
- `docs/prior-art.md`: 9-system comparison table, the one-sentence differences from REMORA and from auto mode, and the REMORA runnability check with exact steps.
- `progress/w2-R.md`: this file.

## Decisions
- Quotes come from arXiv abstract pages (fetched as raw page metadata), the Permission Gate HTML (sections 1, 3, 5.2), the Anthropic post (Table 1) and READMEs. The WebFetch summaries were only used to find pages, never quoted.
- "Not stated" in the table means the sources read don't say; it is not a claim the feature is absent. Only abstracts and READMEs were read for most systems, not full papers.
- REMORA verdict: "REMORA (run, decision function only)". Fallback wording "REMORA-style (reimplemented)" is kept in prior-art.md in case the owner wants the simpler label.

## Deviations
None. (The REMORA check took about 3 minutes of its 30-minute box.)

## Tests
No code. Counts: 16 numeric claims: 13 VERIFIED, 3 VERIFIED-WITH-CAVEAT, 0 NOT FOUND. Non-numeric: 2 NOT FOUND (C1, C4), 5 with caveats. Unverified: full-paper reads for everything except the Permission Gate paper; AMA-Bench confirmed via search results only; SREGym absence claim not checked.

## Interface requests
None.

## Cost / quota
0 hosted calls, no API keys used. Throwaway REMORA dir deleted (`/home/noorelalfi/.claude/jobs/6300cd62/tmp/remora`).

## Handoff
Spec fixes for the merge step or the owner (also in `blog/citations.md`):
1. Spec line 22 and reading list: "81% FNR on DevOps scope escalation" should say it is a stress test (AmPermBench, deliberately ambiguous), not comparable to Anthropic's 17%. "36.8% bypassed via file edits" should say "outside the classifier's scope (Tier 2, by design)".
2. "0.4% FPR / 17% FNR": different populations (real traffic n=10,000 vs real overeager n=52); state both.
3. GRADE link: the arXiv paper (2606.22741) is a dependency-graph failure-prediction paper; replay and rollback are in the `yzhao062/auditable` repo. Cite the repo for that claim.
4. REMORA: it does have a paper in the repo, so "Research software, not a paper" is inexact; license is BUSL-1.1.
5. AGT/ACS verdicts are allow/warn/deny/escalate/transform, not allow/block/redact/ask.
6. "Ask the World Before Acting" is EnvProbe (heuristic scoring), not a VoI method; VoI is background.
7. Self-Attribution / Correlated Errors do not show a different-family verifier fixes anything; frame it as a design choice to be measured.
8. Post 1 needs a written mapping from REMORA's ABSTAIN/VERIFY/ESCALATE to our outcomes before `post1-frozen`.
