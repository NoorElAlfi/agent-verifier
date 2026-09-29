# Progress index

Only merge steps edit this file. Details live in `progress/<wave>-<agent>.md`.

| Wave | Agent | Status | Notes |
|---|---|---|---|
| 1 | W1 | done | Scaffold, SHARED interfaces, decide(), fakes. [progress/w1.md](progress/w1.md) |
| 2 | R | done | Citations checked: 16/16 numbers found (3 with caveats); 2 non-numeric claims NOT FOUND; spec wording fixes listed. Prior-art table (9 systems). REMORA verdict: "REMORA (run)", decision function only (BUSL-1.1: call it, don't vendor it). [progress/w2-R.md](progress/w2-R.md) |
| 2 | A | done | OPA policy engine + `policies/authz.rego` (2 s timeout → defer), append-only SQLite hash-chain ledger + `python -m av.ledger verify`, hash-bound executor (refused / stale). M6, M7, M8 tested. [progress/w2-A.md](progress/w2-A.md) |
| 2 | C | done | Probe image `av-probe` (196 MB), Docker sandbox (`--network none`, read-only, no env, caps, 60 s), probes `run_tests`/`diff`/`secret_scan`, `make probe-image`, `make clean` (probe-labelled resources only). M3b tested. [progress/w2-C.md](progress/w2-C.md) |
| 2 | B | done | Tiering + PROBE_CATALOG, ScopeDriftCheck, TaintStoreImpl + ProvenanceCheck ("new material only" rule), OutcomeCheck. M2, M3, M4-unit tested; 7 strict-xfail known limitations. Owner kept the provenance reading (Deviation 1: substring-only overlap in ordinary files is logged, not blocked; now an xfail limitation). [progress/w2-B.md](progress/w2-B.md) |
| 2 | D | done | MCP gateway (exactly 6 tools), Inspect ReAct agent with a quota-counted `av-hosted` provider, replay, 3 synthetic scenarios, sample repo with a real bug, `make demo` / `make demo LIVE=1`. M5 tested. [progress/w2-D.md](progress/w2-D.md) |
| 2 | merge | done | Merged R, A, C, B, D. Real components wired in `av/gateway/wiring.py` (stand-ins removed). `make demo`: scope_drift blocked (scope_drift), injection blocked (provenance), benign accept, hosted calls: 0. [progress/w2-merge.md](progress/w2-merge.md) |
