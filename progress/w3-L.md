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
1 hosted call used (the models listing; OpenAI-compatible `GET /models` worked, so no Inspect custom-provider switch is needed for the endpoint itself). No trial run.
Models listed: deepseek-v4-flash, deepseek-v4-flash-vision-exp, deepseek-flash, deepseek-v4.1-flash, deepseek-v4-pro, glm-5.2, glm-5.3, glm-5.3-flash, grok-4.6, grok-4.7, muse-spark-1.2/1.3-contributor, gpt-5.6-luna, gpt-6-luna, hy3, hy4-preview, kimi-k2.7-code, kimi-k3, mimo-v2.5, mimo-v2.6-flash, mimo-v2.5-pro, mimo-v2.6-pro, minimax-m2.7, minimax-m3, space-bunny-free, longcat-2.0, longcat-2.5-preview-free, qwen3.8-max, qwen3.8-flash, qwen3.7-plus.
## Where I stopped
Blocked at step 1: there is NO Qwen3-Coder model ID in the listing (only qwen3.8-max, qwen3.8-flash, qwen3.7-plus). Per instructions I did not set AV_HOSTED_MODEL. Owner must choose the model (candidates: qwen3.7-plus or qwen3.8-flash as the closest Qwen; kimi-k2.7-code as a code-tuned one) and set AV_HOSTED_MODEL in .env, or say so and I set it. Then run step 2 (trial on benign).
## Handoff
Wave 2 wiring has no stand-ins left, so the live guard is lifted.
