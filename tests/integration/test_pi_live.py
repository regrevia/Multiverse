from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import execute_pi

pytestmark = pytest.mark.integration


def test_real_pi_produces_a_runtime_shaped_artifact(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_PI_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_PI_LIVE=1 to run the authorized local Pi probe")
    if shutil.which("pi") is None:
        pytest.skip("Pi CLI is not installed on this host")
    provider = os.environ.get("MULTIVERSE_PI_PROVIDER", "anthropic")
    auth = subprocess.run(
        ["pi", "auth", "check", "--provider", provider, "--no-refresh", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if auth.returncode != 0:
        pytest.skip("Pi provider readiness check failed")
    if '"status":"ready"' not in auth.stdout:
        pytest.skip("Pi provider credentials are not configured")

    result = execute_pi(
        {"goal": "Write one concise sentence describing a durable workflow runtime."},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
            "expectedVersion": os.environ.get("MULTIVERSE_PI_VERSION", "1.0.1"),
            "systemPrompt": (
                "Return only JSON with a non-empty text field and an empty "
                "artifact_refs array. Do not use tools."
            ),
            "artifactName": "pi-live-deliverable.md",
            "artifactMediaType": "text/markdown",
            "timeoutSeconds": 180,
        },
    )

    assert result.output["text"].strip()
    assert result.output["artifact_refs"] == []
    assert result.generated_artifact is not None
    assert result.generated_artifact.content
    assert result.observations[0]["provider"] == "pi"
