from __future__ import annotations

import select
import signal
import subprocess
import sys
from pathlib import Path

from multiverse_workflow.runtime.http_job import HttpJobClient

from .conftest import execution_request, wait_final

ROOT = Path(__file__).parents[2]


def test_real_cli_runs_operator_program_and_shuts_down(tmp_path):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "multiverse_workflow.execution_host",
            "--trusted-loopback",
            "--database",
            str(tmp_path / "host.db"),
            "--root",
            str(tmp_path / "jobs"),
            "--port",
            "0",
            "--capability",
            "content.produce@1",
            "--",
            sys.executable,
            str(ROOT / "examples/execution-host/deterministic_program.py"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert select.select([process.stdout], [], [], 5)[0]
        line = process.stdout.readline().decode().strip()
        assert line.startswith("Trusted loopback execution host: ")
        client = HttpJobClient(line.split(": ", 1)[1], timeout_seconds=2)
        ref = client.submit(execution_request())["executionRef"]
        result = wait_final(client, ref)
        assert result["status"] == "succeeded"
        assert len(result["artifacts"]) == 1
        assert client.fetch_artifact_content(ref, result["artifacts"][0]["artifactId"])
        process.send_signal(signal.SIGINT)
        process.wait(timeout=5)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        assert process.stderr is not None
        errors = process.stderr.read().decode()
        process.stdout.close()
        process.stderr.close()
    assert not errors
