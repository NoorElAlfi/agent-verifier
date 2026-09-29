# W2-C: Probes and sandbox
**Status:** done   **Branch:** w2/C

## Built
- `docker/probe.Dockerfile`: python:3.12-slim + pytest 8.3.4 only. Image `av-probe:latest`.
- `av/probes/sandbox.py`: `run_in_sandbox(copy_root, cmd, timeout=60)`, `build_image()`, `image_present()`, `SandboxError`.
- `av/probes/probes.py`: `RunTestsProbe` (name `run_tests`), `DiffProbe` (`diff`), `SecretScanProbe` (`secret_scan`); `av/probes/__init__.py` exports them.
- `tests/test_probes.py` (9 offline tests, docker mocked), `tests/test_probes_docker.py` (5 tests, `pytest.mark.docker`, marker already registered in pyproject).
- Makefile (add-only): `clean`, `probe-image`. `pyproject.toml` (add-only): `detect-secrets>=1.5.0` (uv.lock updated locally; the merge step re-runs `uv lock`).

## Decisions
- Container flags: `--rm --network none --read-only --tmpfs /tmp --cpus 1 --memory 512m (swap equal) --pids-limit 128 --cap-drop ALL --no-new-privileges --user 65534`, copy mounted read-only at /work. No `-e` at all, so the container env is only the image's own; the docker CLI process gets only PATH/HOME/DOCKER_*. Tests run with `python -B -m pytest -p no:cacheprovider` because nothing is writable. The copy is chmod a+rX so the non-root user can read it (it is disposable).
- Timeout: `subprocess` timeout 60 s, then `docker rm -f <name>`; probe returns `error="probe timed out"` (=> defer). Docker missing, image missing, or `docker run` exit 125 also give `error` (=> defer). pytest exit 1 (failures) or 5 (no tests) gives `passed=False` with no error (=> reject); other exit codes are errors.
- DiffProbe and SecretScanProbe don't need Docker: diff reads the real file read-only via a path-escape-guarded resolver; secret scan writes the proposed content to a temp dir outside the workspace. Both are informational/pure and never write to workspace.root. Findings from secret_scan report line and type only, never the value.
- SecretScanProbe uses detect-secrets `scan_file` on a temp file, not `scan_line`: `scan_line`'s eager entropy mode flagged ordinary code (`    return 1`).
- `make clean` does NOT run a global `docker volume prune` (would touch other projects, rule 15). It prunes only volumes labelled `av.probe=1` (the probes create none: bind mount + tmpfs only), removes leftover `av-probe-*` containers, and removes `av-probe:latest`. It leaves the pulled `python:3.12-slim` base image (shared) alone; remove it manually with `docker rmi python:3.12-slim` if wanted.
- Probes don't check `contract.risk_tier`; which probes run per tier is B's catalog.

## Deviations
- PLAN step 5 says "any dangling volumes": narrowed to probe-labelled volumes, for the reason above.

## Tests
- `uv run pytest -q`: 136 passed (121 W1 + 9 offline probe + 5 docker; the docker tests skip if the image is absent). `uv run pytest -q -m docker`: 5 passed (~8 s).
- M3b: socket.connect to 1.1.1.1 fails in the sandbox; writes to /etc, ../, /work and / fail and no marker appears on the host or in the workspace; host env secrets (also OPENCODE_GO_API_KEY) are not visible in the container; real workspace hash unchanged in every case; a hanging test hits the timeout, gives an error and leaves no container.
- Unverified: memory/CPU cap enforcement (flags asserted in an offline test, not stressed); behaviour on non-WSL Docker hosts.

## Interface requests
None. (For B/D: probe names are `run_tests`, `diff`, `secret_scan`. Wire as `probes={p.name: p for p in (RunTestsProbe(), DiffProbe(), SecretScanProbe())}`. Build the image once with `make probe-image`. Note RunTestsProbe with `error` set defers, so a machine without the image defers every tier that lists run_tests.)

## Cost / quota
0 hosted calls, 0 Ollama calls.

## Handoff
- Image `av-probe:latest`: 196 MB (docker inspect .Size = 196,088,032 B), < 300 MB target.
- M10 disk footprint: probe image 196 MB, plus ~196 MB Docker build cache (base layers, shared with the image), plus `.venv` growth from detect-secrets (small; whole worktree .venv is 49 MB). Total new well under 0.5 GB, against the 5 GB pre-Post-0 budget. `docker system df` after the build: images 871 MB total across all projects, not attributable to this project.
- Each RunTestsProbe run takes about 1-2 s (docker start plus pytest on the sample repo); the 5 docker tests take ~8 s total.
