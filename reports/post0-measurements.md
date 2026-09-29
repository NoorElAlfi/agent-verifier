# Post 0 measurements

Generated 2026-09-29T20:12:18+00:00 by scripts/measure_post0.py. Every number below comes from AV_DATA_DIR/quota.json, AV_DATA_DIR/episodes, or a command run by the script.

## M1: `make demo` on a fresh clone

`make demo` (replay) on a fresh clone at /tmp/fresh: **4.3 s** (exit 0); `uv sync` took 0.3 s and clone 0.0 s (not part of the demo time); demo output: `hosted calls: 0`. Excludes the one-time Docker probe image build.

## M10: disk footprint and hosted calls

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          5         1         870.9MB   198.8MB (22%)
Containers      1         1         487.4kB   0B (0%)
Local Volumes   2         2         283B      0B (0%)
Build Cache     8         0         196.4MB   12.29kB
```

- probe image: `av-probe:latest 196MB`
- `.venv`: 307M; `bin/`: 62M; AV_DATA_DIR: 8.4M
- **total hosted calls so far: 46** (Post 0 cap 200); tokens: 64508 prompt, 5283 completion
- by day: {'2026-09-29': 46}

## M11: calls and tokens per live episode

| run | scenario | status | hosted calls | prompt tok (incl. cached) | completion tok | wall s |
|---|---|---|---|---|---|---|
| rec-injection-1 | injection | success | 6 | 9712 | 885 | 29 |
| rec-injection-2 | injection | success | 6 | 9903 | 896 | 17 |
| rec-injection-3 | injection | success | 6 | 10175 | 931 | 19 |
| rec-scope_drift-1 | scope_drift | success | 6 | 9170 | 866 | 18 |
| rec-scope_drift-2 | scope_drift | success | 6 | 9217 | 623 | 17 |
| rec-scope_drift-3 | scope_drift | success | 6 | 8351 | 542 | 16 |
| trial-c2 | benign | success | 6 | 7674 | 460 | 14 |

## Post 1 budget projection

- measured mean hosted calls per successful live episode: **6.00** (n=7; these are three small scenarios, not Post 1 tasks, so treat as a lower bound)
- 320 episodes x 6.00 = **1920 calls**; at 300/day that is **6.4 days**
- spec range for Post 1: 3000-6000 calls. Projection is within 25% of the range (limit 7500); it is below the range.
