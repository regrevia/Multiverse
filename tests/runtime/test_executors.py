from __future__ import annotations

import sys

import pytest

from multiverse_workflow.runtime import executors
from multiverse_workflow.runtime.claude import ClaudeResult
from multiverse_workflow.runtime.codex import CodexResult
from multiverse_workflow.runtime.executors import (
    ExecutorCancelledError,
    ExecutorError,
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
            assert kwargs["approval_policy"] == "on-request"
            assert kwargs["sandbox_mode"] == "read-only"

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
            "approvalPolicy": "on-request",
            "sandboxMode": "read-only",
            "systemPrompt": "Return the deliverable.",
            "artifactName": "deliverable.md",
            "artifactMediaType": "text/markdown",
        },
    )

    assert result.output == {"text": "real-shaped output", "artifact_refs": []}
    assert result.generated_artifact is not None
    assert result.generated_artifact.content == b"real-shaped output"
    assert result.observations == [{"threadId": "thread-1", "turnId": "turn-1"}]


def test_claude_executor_registers_agent_artifact(monkeypatch, tmp_path) -> None:
    class FakeClaude:
        def __init__(self, **kwargs):
            assert kwargs["permission_mode"] == "dontAsk"

        def run(self, **kwargs):
            return ClaudeResult(
                output={"text": "claude-shaped output", "artifact_refs": []},
                observation={
                    "provider": "claude",
                    "protocol": "print-json",
                    "sessionId": "session-1",
                    "status": "completed",
                },
            )

    monkeypatch.setattr(executors, "ClaudeCli", FakeClaude)
    result = executors.execute_claude(
        {"goal": "write a release note"},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(tmp_path),
            "expectedVersion": "fixture",
            "artifactName": "claude.md",
            "artifactMediaType": "text/markdown",
        },
    )

    assert result.output == {"text": "claude-shaped output", "artifact_refs": []}
    assert result.generated_artifact is not None
    assert result.generated_artifact.content == b"claude-shaped output"
    assert result.observations[0]["provider"] == "claude"


def test_claude_executor_can_inherit_cc_switch_runtime_config(
    monkeypatch, tmp_path
) -> None:
    class FakeClaude:
        def __init__(self, **kwargs):
            assert kwargs["environment"] == {
                "ANTHROPIC_BASE_URL": "https://example.test"
            }
            assert kwargs["model"] == "mapped-sonnet"

        def run(self, **kwargs):
            return ClaudeResult(
                output={"text": "cc-switch output", "artifact_refs":[]},
                observation={"provider": "claude", "protocol": "print-json"},
            )

    monkeypatch.setattr(executors, "ClaudeCli", FakeClaude)
    monkeypatch.setattr(
        executors,
        "load_cc_switch_claude_config",
        lambda **_: type(
            "Config",
            (),
            {
                "environment": {"ANTHROPIC_BASE_URL": "https://example.test"},
                "model": "mapped-sonnet",
                "metadata": {
                    "source": "cc-switch",
                    "profileId": "profile-1",
                    "profileName": "current",
                    "modelAlias": "claude-sonnet-5",
                },
            },
        )(),
    )
    result = executors.execute_claude(
        {"goal": "write"},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(tmp_path),
            "expectedVersion": "2.1.197",
            "configSource": "cc-switch",
        },
    )
    assert result.output["text"] == "cc-switch output"
    assert result.observations[0]["configSource"]["profileId"] == "profile-1"


def test_claude_version_mismatch_is_a_known_executor_failure(monkeypatch, tmp_path) -> None:
    class MismatchClaude:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise executors.ClaudeVersionMismatchError("version mismatch")

    monkeypatch.setattr(executors, "ClaudeCli", MismatchClaude)
    with pytest.raises(ExecutorError, match="version mismatch"):
        executors.execute_claude(
            {"goal": "write"},
            {
                "cwd": str(tmp_path),
                "workspaceRoot": str(tmp_path),
                "homeDir": str(tmp_path),
                "expectedVersion": "2.1.197",
            },
        )


def test_claude_launch_os_error_is_a_known_executor_failure(monkeypatch, tmp_path) -> None:
    class MissingClaude:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise OSError("missing executable")

    monkeypatch.setattr(executors, "ClaudeCli", MissingClaude)
    with pytest.raises(ExecutorError, match="missing executable"):
        executors.execute_claude(
            {"goal": "write"},
            {
                "cwd": str(tmp_path),
                "workspaceRoot": str(tmp_path),
                "homeDir": str(tmp_path),
                "expectedVersion": "2.1.197",
            },
        )


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


def test_codex_binding_controls_approval_policy_and_sandbox(monkeypatch, tmp_path) -> None:
    class PolicyCodex:
        def __init__(self, **kwargs):
            assert kwargs["approval_policy"] == "on-request"
            assert kwargs["sandbox_mode"] == "read-only"

        def run(self, **kwargs):
            return CodexResult(
                output={"text": "approved workflow", "artifact_refs": []},
                observation={"threadId": "thread-1", "turnId": "turn-1"},
            )

    monkeypatch.setattr(executors, "CodexAppServer", PolicyCodex)
    result = execute_codex(
        {"goal": "write a file after approval"},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(tmp_path),
            "model": "gpt-5.5",
            "approvalPolicy": "on-request",
            "sandboxMode": "read-only",
        },
    )
    assert result.output["text"] == "approved workflow"


def test_claude_executor_passes_explicit_native_session_options(monkeypatch, tmp_path) -> None:
    class PersistentClaude:
        def __init__(self, **kwargs):
            assert kwargs["session_persistence"] is True
            assert kwargs["resume_session_id"] == "session-1"
            assert kwargs["fork_session"] is True

        def run(self, **kwargs):
            return ClaudeResult(
                output={"text": "continued", "artifact_refs": []},
                observation={
                    "provider": "claude",
                    "protocol": "json",
                    "sessionId": "session-2",
                    "status": "completed",
                },
            )

    monkeypatch.setattr(executors, "ClaudeCli", PersistentClaude)
    result = executors.execute_claude(
        {"goal": "continue"},
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(tmp_path),
            "expectedVersion": "fixture",
            "sessionPersistence": True,
            "resumeSessionId": "session-1",
            "forkSession": True,
        },
    )

    assert result.observations[0]["sessionId"] == "session-2"
