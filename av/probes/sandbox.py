"""Run a command against a disposable workspace copy inside a locked-down container.

`docker run --rm --network none --read-only`, tmpfs /tmp, no environment passthrough (no `-e`;
the docker CLI itself gets only PATH/HOME/DOCKER_*), CPU and memory caps, a 60 s timeout, no
capabilities, non-root. The copy is mounted read-only, so nothing the code does can persist
anywhere, and the caller deletes the copy afterwards. Nothing here touches workspace.root.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE = "av-probe:latest"
TIMEOUT_S = 60
CPUS = "1"
MEMORY = "512m"
PIDS = "128"
_DOCKER_DIR = Path(__file__).resolve().parents[2] / "docker"
_DOCKERFILE = _DOCKER_DIR / "probe.Dockerfile"


class SandboxError(RuntimeError):
    """Docker unavailable, image missing, or the run could not be completed (=> defer)."""


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _docker_env() -> dict[str, str]:
    keep = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT")
    return {k: os.environ[k] for k in keep if k in os.environ}


def _docker(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, env=_docker_env()
        )
    except FileNotFoundError as e:
        raise SandboxError("docker is not installed") from e


def image_present() -> bool:
    return _docker(["image", "inspect", IMAGE], 30).returncode == 0


def build_image() -> None:
    """Build the probe image (needs the network once, to pull python:3.12-slim)."""
    p = _docker(["build", "-t", IMAGE, "-f", str(_DOCKERFILE), str(_DOCKER_DIR)], 900)
    if p.returncode != 0:
        raise SandboxError(f"image build failed: {p.stderr[-500:]}")


def run_in_sandbox(copy_root: Path, cmd: list[str], timeout: float = TIMEOUT_S) -> SandboxResult:
    """Run `cmd` in the probe image with `copy_root` mounted read-only at /work."""
    if not image_present():
        raise SandboxError(f"probe image {IMAGE} not built (docker build -t {IMAGE} -f docker/probe.Dockerfile docker)")
    # Copies are created 0700 by the host user; the container runs as nobody, so open them up.
    subprocess.run(["chmod", "-R", "a+rX", str(copy_root)], check=False, capture_output=True)
    name = f"av-probe-{uuid.uuid4().hex[:12]}"
    args = [
        "run", "--rm", "--name", name,
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--cpus", CPUS, "--memory", MEMORY, "--memory-swap", MEMORY, "--pids-limit", PIDS,
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "-v", f"{copy_root}:/work:ro",
        "-w", "/work",
        IMAGE, *cmd,
    ]
    try:
        p = _docker(args, timeout)
    except subprocess.TimeoutExpired:
        _docker(["rm", "-f", name], 30)
        return SandboxResult(exit_code=-1, stdout="", stderr="", timed_out=True)
    if p.returncode == 125:  # docker itself failed (daemon down, bad flags)
        raise SandboxError(f"docker run failed: {p.stderr[-300:]}")
    return SandboxResult(p.returncode, p.stdout, p.stderr)
