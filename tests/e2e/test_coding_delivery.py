from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import execute_codex

pytestmark = pytest.mark.integration


def test_real_coding_delivery_probe_reaches_runtime_shaped_output(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex probe")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery probe")

    result = execute_codex(
        {
            "goal": (
                "Prepare a concise release note for Multiverse. "
                "Return a useful human-reviewable deliverable."
            )
        },
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
            "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
            "systemPrompt": (
                "Act as the producer node for a human-reviewed delivery workflow. "
                "Return only JSON with non-empty text and an empty artifact_refs array."
            ),
            "artifactName": "coding-delivery-probe.md",
            "artifactMediaType": "text/markdown",
            "timeoutSeconds": 180,
        },
    )

    assert result.generated_artifact is not None
    assert result.output["artifact_refs"] == []
    assert result.observations
