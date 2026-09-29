"""M3b: sandbox containment, using the real probe image. Run with `pytest -m docker`.

Build the image once: docker build -t av-probe:latest -f docker/probe.Dockerfile docker
Each hostile "proposed test" asserts that the escape FAILED inside the container, so the probe
passes only if the sandbox held; the host is then checked independently.
"""

import os
import shutil
from pathlib import Path

import pytest

import av.probes.sandbox as sb
from av.contracts import ContractBuilder
from av.probes import RunTestsProbe
from tests.fakes import FakeTaintStore, fake_tier

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module", autouse=True)
def _need_image():
    if shutil.which("docker") is None or not sb.image_present():
        pytest.skip("docker or the av-probe image is unavailable")


def propose(task, name, body):
    return ContractBuilder(tier_fn=fake_tier({"write_file": 2})).build(
        "write_file", {"path": f"tests/{name}.py", "content": body}, task, FakeTaintStore()
    )


def run(task, workspace, name, body):
    before = workspace.snapshot_hashes()
    r = RunTestsProbe().run(propose(task, name, body), workspace)
    assert workspace.snapshot_hashes() == before, "real workspace changed"
    return r


def test_good_change_passes_and_bad_change_fails(task, workspace):
    good = "from calc.ops import add\n\ndef test_ok():\n    assert add(1, 1) == 2\n"
    assert run(task, workspace, "test_good", good).passed
    bad = "def test_bad():\n    assert False\n"
    r = run(task, workspace, "test_bad", bad)
    assert not r.passed and r.error is None


def test_network_is_blocked(task, workspace):
    body = (
        "import socket, pytest\n\n"
        "def test_no_network():\n"
        "    s = socket.socket(); s.settimeout(3)\n"
        "    with pytest.raises(OSError):\n"
        "        s.connect(('1.1.1.1', 80))\n"
    )
    r = run(task, workspace, "test_net", body)
    assert r.passed, r.details


def test_writes_outside_are_blocked_and_host_untouched(task, workspace):
    marker = f"av_probe_marker_{os.getpid()}"
    body = (
        "import pytest\n\n"
        "@pytest.mark.parametrize('p', ['/etc/%(m)s', '../%(m)s', '/work/%(m)s', '/%(m)s'])\n"
        "def test_no_write(p):\n"
        "    with pytest.raises(OSError):\n"
        "        open(p, 'w').write('x')\n"
    ) % {"m": marker}
    r = run(task, workspace, "test_write", body)
    assert r.passed, r.details
    assert not Path("/etc", marker).exists()
    assert not (workspace.root.parent / marker).exists()
    assert not (workspace.root / marker).exists()


def test_host_env_secret_is_not_visible(task, workspace, monkeypatch):
    monkeypatch.setenv("AV_TEST_SECRET", "hunter2-do-not-leak")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "hunter2-do-not-leak")
    body = (
        "import os\n\n"
        "def test_env_clean():\n"
        "    assert 'hunter2' not in repr(dict(os.environ))\n"
        "    assert 'AV_TEST_SECRET' not in os.environ and 'OPENCODE_GO_API_KEY' not in os.environ\n"
    )
    r = run(task, workspace, "test_env", body)
    assert r.passed, r.details
    assert "hunter2" not in r.model_dump_json()


def test_timeout_is_an_error_and_container_is_removed(task, workspace, monkeypatch):
    monkeypatch.setattr("av.probes.probes.run_in_sandbox", lambda c, cmd: sb.run_in_sandbox(c, cmd, timeout=5))
    body = "import time\n\ndef test_hang():\n    time.sleep(120)\n"
    r = run(task, workspace, "test_hang", body)
    assert r.error and "timed out" in r.error and not r.passed
    ps = sb._docker(["ps", "-aq", "--filter", "name=av-probe-"], 30)
    assert ps.stdout.strip() == ""
