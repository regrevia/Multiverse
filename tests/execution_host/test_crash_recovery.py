from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from multiverse_workflow.runtime.http_job import HttpJobClient

from .conftest import execution_request, wait_final

DRIVER = """import sys,time,threading
from pathlib import Path
from multiverse_workflow.execution_host.backend import ProcessConfig
from multiverse_workflow.execution_host.service import ExecutionHost,create_server
root=Path(sys.argv[1]); stage=sys.argv[2]
def hook(current,ref):
    if current == stage:
        (root / 'barrier').write_text(ref)
        threading.Event().wait()
host=ExecutionHost(root/'host.db',root/'jobs',ProcessConfig((sys.executable,str(root/'job.py'))),
                   hook=hook)
server=create_server(host)
(root/'port').write_text(str(server.server_port))
try:
    server.serve_forever()
finally:
    server.server_close(); host.close()
"""


def await_file(path: Path) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.02)
    raise AssertionError(f"missing process evidence: {path.name}")


def start_host(root: Path, stage: str = "") -> tuple[subprocess.Popen, HttpJobClient]:
    (root / "port").unlink(missing_ok=True)
    process = subprocess.Popen(
        [sys.executable, "-c", DRIVER, str(root), stage],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    port = await_file(root / "port")
    return process, HttpJobClient(f"http://127.0.0.1:{port}", timeout_seconds=2)


def stop_host(process: subprocess.Popen) -> None:
    process.kill()
    process.wait(timeout=5)
    assert process.stderr is not None
    process.stderr.close()


@pytest.mark.parametrize("stage", ["after_intent", "before_launch", "after_launch"])
def test_actual_sigkill_launch_windows_are_unknown_and_never_relaunched(tmp_path, stage):
    # Adopt the crashed host's test children so this fault test leaves no zombies.
    libc = ctypes.CDLL(None, use_errno=True)
    old = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(old), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    marker = tmp_path / "started"
    (tmp_path / "job.py").write_text(f"""import os,time
from pathlib import Path
Path({str(marker)!r}).write_text(str(os.getpid()))
time.sleep(30)
""")
    host, client = start_host(tmp_path, stage)
    child_pid = None
    restarted = None
    try:
        ref = client.submit(execution_request())["executionRef"]
        assert await_file(tmp_path / "barrier") == ref
        if stage in {"before_launch", "after_launch"}:
            assert client.observe(ref)["effectState"] == "possible"
        if stage == "after_launch":
            child_pid = int(await_file(marker))
            # Retain identity evidence before kill; don't signal any recycled PID.
            identity = Path(f"/proc/{child_pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        stop_host(host)
        restarted, recovered = start_host(tmp_path)
        assert recovered.lookup("dispatch-1")["executionRef"] == ref
        observation = recovered.observe(ref)
        assert observation["status"] == "unknown"
        assert observation["executionFinal"] is False
        assert observation["effectState"] == "possible"
        assert recovered.submit(execution_request())["executionRef"] == ref
        assert recovered.observe(ref) == observation
        if child_pid is not None:
            assert int(marker.read_text()) == child_pid
        else:
            assert not marker.exists()
    finally:
        if host.poll() is None:
            stop_host(host)
        if restarted is not None:
            stop_host(restarted)
        if child_pid is not None:
            path = Path(f"/proc/{child_pid}/stat")
            if path.exists() and path.read_text().rsplit(")", 1)[1].split()[19] == identity:
                os.killpg(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
        assert libc.prctl(36, old.value, 0, 0, 0) == 0


def test_terminal_result_and_artifact_survive_real_service_restart(tmp_path):
    (tmp_path / "job.py").write_text("""import json
from pathlib import Path
Path('result.txt').write_text('persistent bytes')
print(json.dumps({'output':{'text':'done'},'artifacts':[
{'path':'result.txt','name':'result.txt','mediaType':'text/plain'}]}))
""")
    process, client = start_host(tmp_path)
    try:
        ref = client.submit(execution_request())["executionRef"]
        observation = wait_final(client, ref)
        assert observation["status"] == "succeeded"
        stop_host(process)
        process, client = start_host(tmp_path)
        assert client.observe(ref) == observation
        assert client.submit(execution_request())["executionRef"] == ref
        metadata = client.fetch_artifacts(ref)
        artifact_id = metadata["artifacts"][0]["artifactId"]
        assert client.fetch_artifact_content(ref, artifact_id) == b"persistent bytes"
    finally:
        if process.poll() is None:
            stop_host(process)
