from __future__ import annotations

import sys

import pytest

from multiverse_workflow.runtime import executors
from multiverse_workflow.runtime.codex import CodexResult
from multiverse_workflow.runtime.executors import (
    ExecutorCancelledError,
    ExecutorUnknownError,
    execute_codex,
    execute_local_process,
)


def test_local_process_round_trips_json() -> None:
    result = execute_local_process(
        {"value": 2},
        {
            "command": [
                sys.executable,
                "-c",
                (
                    "import json, sys; "
                    "value=json.load(sys.stdin)['value']; "
                    "print(json.dumps({'value': value * 2}))"
                ),
            ]
        },
    )

    assert result.output == {"value": 4}


def test_codex_executor_registers_agent_artifact(monkeypatch, tmp_path) -> None:
    class FakeCodex:
        def __init__(self, **kwargs):
            assert kwargs["model"] == "gpt-5.5"

        def run(self, **kwargs):
            assert kwargs["cwd"] == tmp_path
            return CodexResult(
                output={"text": "real-shaped output", "artifact_refs": []},
                observation={"threadId": "thread-1", "turnId": "turn-1"},
            )

    monkeypatch.setattr(executors, "CodexAppServer", FakeCodex)
    result = execute_codex(
        {"goal": "write a release note"},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(tmp_path),
            "model": "gpt-5.5",
            "systemPrompt": "Return the deliverable.",
            "artifactName": "deliverable.md",
            "artifactMediaType": "text/markdown",
        },
    )

    assert result.output == {"text": "real-shaped output", "artifact_refs": []}
    assert result.generated_artifact is not None
    assert result.generated_artifact.content == b"real-shaped output"
    assert result.observations == [{"threadId": "thread-1", "turnId": "turn-1"}]


def test_codex_transport_loss_is_unknown_not_retryable(monkeypatch, tmp_path) -> None:
    class LostCodex:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise executors.CodexProtocolError("connection closed")

    monkeypatch.setattr(executors, "CodexAppServer", LostCodex)
    with pytest.raises(ExecutorUnknownError, match="unknown"):
        execute_codex(
            {"goal": "write"},
            {
                "cwd": str(tmp_path),
                "workspaceRoot": str(tmp_path),
                "homeDir": str(tmp_path),
                "model": "gpt-5.5",
            },
        )


def test_codex_confirmed_interrupt_is_cancelled(monkeypatch, tmp_path) -> None:
    class InterruptedCodex:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise executors.CodexInterruptedError("confirmed")

    monkeypatch.setattr(executors, "CodexAppServer", InterruptedCodex)
    with pytest.raises(ExecutorCancelledError, match="interrupted"):
        execute_codex(
            {
                "goal": "write",
            },
            {
                "cwd": str(tmp_path),
                "workspaceRoot": str(tmp_path),
                "homeDir": str(tmp_path),
                "model": "gpt-5.5",
            },
        )
