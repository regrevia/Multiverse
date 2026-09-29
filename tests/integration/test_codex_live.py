from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import execute_codex

pytestmark = pytest.mark.integration


def test_real_codex_produces_a_runtime_shaped_artifact(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex probe")
    codex = shutil.which("codex")
    if codex is None:
        pytest.fail("codex executable is required for the live W03 probe")
    home_dir = Path(os.environ.get("HOME", str(tmp_path))).resolve()

    result = execute_codex(
        {"goal": "Write one concise sentence describing a durable workflow runtime."},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(home_dir),
            "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
            "systemPrompt": (
                "Return only JSON with a non-empty text field and an empty "
                "artifact_refs array. Do not use tools."
            ),
            "artifactName": "codex-live-deliverable.md",
            "artifactMediaType": "text/markdown",
            "timeoutSeconds": 180,
        },
    )

    assert result.output["text"].strip()
    assert result.output["artifact_refs"] == []
    assert result.generated_artifact is not None
    assert result.generated_artifact.content
    assert result.observations
    assert result.observations[0]["threadId"]
    assert result.observations[0]["turnId"]
