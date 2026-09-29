# W3-L: Live recording and Post 0 measurements
**Status:** blocked   **Branch:** w3/L
## Built
Nothing yet.
## Decisions
- Scenario (c) is `benign`. `make demo LIVE=1` takes no scenario argument (Makefile is not mine to change), so the trial will use `uv run python -m av.agent.react benign --run-id trial-c`.
## Deviations
None yet.
## Tests
Not run (no code changed).
## Interface requests
None
## Cost / quota
0 hosted calls used (`python -m av.quota` shows total 0).
## Where I stopped
Blocked before step 1. `.env` in this worktree AND in the main checkout has `OPENCODE_GO_API_KEY=` and `OPENCODE_GO_BASE_URL=` both EMPTY (checked by value length only; AV_DATA_DIR is set), and neither is in the process environment. So no hosted call, models listing, or model-ID lookup is possible.
Next: owner fills in both values in `.env`. Then: (1) one models-list call (`GET {base}/models`, counted with `quota.record(1)`), pick the Qwen3-Coder ID, set `AV_HOSTED_MODEL` in `.env`; (2) trial on `benign`; then stop at the gate.
## Handoff
Wave 2 wiring has no stand-ins left, so the live guard is lifted.
