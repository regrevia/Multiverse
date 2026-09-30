from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import ExecutorError, execute_claude

pytestmark = pytest.mark.integration


def test_real_claude_produces_a_runtime_shaped_artifact(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CLAUDE_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CLAUDE_LIVE=1 to run the authorized local Claude probe")
    if shutil.which("claude") is None:
        pytest.fail("claude executable is required for the live W05A probe")

    try:
        result = execute_claude(
            {"goal": "Write one concise sentence describing a durable workflow runtime."},
            {
                "cwd": str(tmp_path),
                "workspaceRoot": str(tmp_path),
                "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
                "model": os.environ.get("MULTIVERSE_CLAUDE_MODEL", "sonnet"),
                "expectedVersion": os.environ.get("MULTIVERSE_CLAUDE_VERSION", "2.1.197"),
                "systemPrompt": (
                    "Return only JSON with a non-empty text field and an empty "
                    "artifact_refs array. Do not use tools."
                ),
                "artifactName": "claude-live-deliverable.md",
                "artifactMediaType": "text/markdown",
                "timeoutSeconds": 180,
                "permissionMode": "dontAsk",
            },
        )
    except ExecutorError as exc:
        if "Not logged in" in str(exc) or "/login" in str(exc):
            pytest.skip("Claude Code is installed but not authenticated: run /login")
        raise

    assert result.output["text"].strip()
    assert result.output["artifact_refs"] == []
    assert result.generated_artifact is not None
    assert result.generated_artifact.content
    assert result.observations
    assert result.observations[0]["provider"] == "claude"
