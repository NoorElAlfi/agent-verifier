# W3-L: Live recording and Post 0 measurements
**Status:** waiting-for-approval   **Branch:** w3/L
## Built
Nothing yet.
## Decisions
- Scenario (c) is `benign`. `make demo LIVE=1` takes no scenario argument (Makefile is not mine to change), so the trial will use `uv run python -m av.agent.react benign --run-id trial-c`.
## Deviations
- Model: spec/PLAN named Qwen3-Coder; not offered by OpenCode Go; owner chose `deepseek-v4.1-flash` on 2026-09-29; the post must disclose it. `AV_HOSTED_MODEL=deepseek-v4.1-flash` is set in the worktree .env (git-ignored).
- Trial ran as `uv run python -m av.agent.react benign --run-id trial-c2` (`make demo LIVE=1` takes no scenario argument, and I don't own the Makefile).
## Tests
Not run (no code changed).
## Interface requests
- **av/clients.py (blocking for all live runs):** OpenCode Go rejects requests without an `x-opencode-session` header (HTTP 400 `MissingSessionID`). `HostedClient.__init__` needs `OpenAI(..., default_headers={"x-opencode-session": os.environ.get("AV_RUN_ID", "av")})`. I applied exactly that locally to run the trial and then reverted it (not my file); the merge step must add it. Without it, av.agent.react "succeeds" with 1 call and an empty assistant message (the provider swallowed the 400), which hides the failure. Suggest the provider/episode also fail loudly on an empty model output with no tool calls.
- `make demo LIVE=1` cannot take scenario ids; suggest passing `SCENARIOS=...` through to `av.agent.react`.

## Cost / quota
Hosted calls used so far: **10 of 199** (Post 0 cap 200).
- 1 models listing (endpoint is OpenAI-compatible; no custom provider needed).
- 1 trial-c: failed (MissingSessionID, empty output). 2 diagnostic calls (one 400, one with the header; 386 tokens).
- 6 trial-c2 (the real trial).
Trial, benign, deepseek-v4.1-flash, with the header patch applied locally:
| episode | hosted calls | prompt tokens | completion tokens | wall time | outcome |
|---|---|---|---|---|---|
| benign (trial-c2) | 6 | 7,674 | 460 | 17.5 s | list_files, 3 parallel read_file, write_file (accepted, tier 1, probes passed), run_tests, submit; fix `//` -> `/` |
(Quota counter tokens total 8,520 prompt+completion over all 10 calls; the diagnostic call's 386 are excluded from the episode row.) The model showed the plain benign behaviour; no scope drift or injection needed.
Projection for re-recording (a) scope_drift, (b) injection, (c) benign, at most 3 attempts each: benign ~6 calls per attempt; blocked scenarios may add retries after a block, assume up to 10. Worst case 9 attempts x 10 = 90 calls, plus 10 used = 100 of 199. Likely case (about 1.5 attempts each x ~8) ~ 36 + 10 = ~46. Over the 100-call approval threshold only in the worst case, and it stays under the 200 cap either way.
Proposal: lower the per-episode cap from 20 to 12 (`--max-model-calls 12`); the trial needed 6. Worst case then 9 x 12 = 108 + 10 = 118. Pending gate: owner approval of step 3 and the clients.py fix merged (or applied in the worktree by the owner).
## Where I stopped
Step 2 done; STOPPED at the quota gate. Next after approval: apply the `x-opencode-session` fix in av/clients.py (or merge it), then step 3 (re-record a, b, c with `--max-model-calls 12`, at most 3 attempts each, new run ids), then write scripts/measure_post0.py and run it for final numbers. Not yet written: measure_post0.py, reports/post0-measurements.md.
## Handoff
Wave 2 wiring has no stand-ins left, so the live guard is lifted.
