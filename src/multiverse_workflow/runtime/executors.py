from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from multiverse_workflow.runtime.codex import (
    CodexAppServer,
    CodexInterruptedError,
    CodexOutputLimitError,
    CodexProtocolError,
    CodexRunCancelled,
    CodexTurnFailed,
)
from multiverse_workflow.runtime.ollama import OllamaError, generate_deliverable


class ExecutorError(RuntimeError):
    """A local executor cannot produce a valid protocol result."""


class ExecutorUnknownError(ExecutorError):
    """The executor may have accepted work, but its result is not knowable."""


class ExecutorCancelledError(ExecutorError):
    """The executor confirmed that the active work was cooperatively stopped."""

    def __init__(self, message: str, *, code: str = "EXECUTOR_CANCELLED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HumanRequestSpec:
    request_type: str
    title: str
    instructions: str
    choices: list[str]
    authorized_subjects: list[str]


@dataclass(frozen=True)
class GeneratedArtifact:
    name: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class ExecutionResult:
    output: Any | None = None
    human_request: HumanRequestSpec | None = None
    observations: list[dict[str, object]] | None = None
    generated_artifact: GeneratedArtifact | None = None


def execute_local_process(input_value: Any, config: dict[str, Any]) -> ExecutionResult:
    """Run a configured JSON-in/JSON-out process as one workflow node."""
    command = config.get("command")
    if not (
        isinstance(command, list)
        and command
        and all(isinstance(part, str) and part for part in command)
    ):
        raise ExecutorError("local_process config.command must be a non-empty string array")
    timeout = config.get("timeoutSeconds", 60)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ExecutorError("local_process timeoutSeconds must be positive")
    cwd = config.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
        raise ExecutorError("local_process cwd must be a non-empty string")
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(input_value, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExecutorError(f"local_process failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise ExecutorError(f"local_process failed: {detail}")
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ExecutorError("local_process stdout must contain one JSON value") from exc
    return ExecutionResult(output=output)


def execute_codex(
    input_value: Any,
    config: dict[str, Any],
    *,
    on_server_request: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
    on_server_response: Callable[[str, dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ExecutionResult:
    if not isinstance(input_value, dict) or not isinstance(input_value.get("goal"), str):
        raise ExecutorError("codex deliverable requires a goal string")
    cwd = config.get("cwd")
    workspace_root = config.get("workspaceRoot")
    home_dir = config.get("homeDir")
    model = config.get("model")
    prompt = config.get("systemPrompt", "Return a concise JSON deliverable.")
    approval_policy = config.get("approvalPolicy", "never")
    sandbox_mode = config.get("sandboxMode", "workspace-write")
    max_output_bytes = config.get("maxOutputBytes", 262144)
    if not isinstance(cwd, str) or not cwd.strip():
        raise ExecutorError("codex cwd must be a non-empty string")
    if not isinstance(workspace_root, str) or not workspace_root.strip():
        raise ExecutorError("codex workspaceRoot must be a non-empty string")
    if not isinstance(home_dir, str) or not home_dir.strip():
        raise ExecutorError("codex homeDir must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ExecutorError("codex model must be a non-empty string")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ExecutorError("codex systemPrompt must be a non-empty string")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "artifact_refs"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "artifact_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 0},
        },
    }
    request = (
        f"{prompt}\n"
        f"Structured task input: {json.dumps(input_value, ensure_ascii=False, sort_keys=True)}\n"
        "Return only JSON matching the supplied output schema."
    )
    command_value = config.get("command")
    command = (
        tuple(command_value)
        if isinstance(command_value, list) and all(isinstance(part, str) for part in command_value)
        else ("codex", "app-server", "--stdio")
    )
    cwd_path = Path(cwd).resolve()
    workspace_path = Path(workspace_root).resolve()
    home_path = Path(home_dir).resolve()
    if not cwd_path.is_relative_to(workspace_path):
        raise ExecutorError("codex cwd must be inside workspaceRoot")
    if not home_path.is_dir():
        raise ExecutorError("codex homeDir must be an existing directory")
    try:
        result = CodexAppServer(
            command=command,
            model=model,
            timeout_seconds=float(config.get("timeoutSeconds", 180)),
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            max_output_bytes=max_output_bytes,
        ).run(
            prompt=request,
            cwd=cwd_path,
            home_dir=home_path,
            output_schema=schema,
            on_server_request=on_server_request,
            on_server_response=on_server_response,
            should_stop=should_stop,
        )
    except CodexInterruptedError as exc:
        raise ExecutorCancelledError(
            f"codex turn interrupted: {exc}",
            code=(
                "RUN_CANCELLED"
                if exc.cancelled
                else "DEADLINE_EXCEEDED"
                if exc.deadline
                else "EXECUTOR_CANCELLED"
            ),
        ) from exc
    except CodexRunCancelled as exc:
        raise ExecutorCancelledError(str(exc), code="RUN_CANCELLED") from exc
    except CodexTurnFailed as exc:
        raise ExecutorError(f"codex turn failed: {exc}") from exc
    except CodexOutputLimitError as exc:
        raise ExecutorError(f"codex output limit exceeded: {exc}") from exc
    except CodexProtocolError as exc:
        raise ExecutorUnknownError(f"codex result is unknown: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise ExecutorError(f"codex execution failed: {exc}") from exc
    output = result.output
    text = output.get("text")
    artifact_refs = output.get("artifact_refs")
    if not isinstance(text, str) or not text.strip() or artifact_refs != []:
        raise ExecutorError("codex output must contain non-empty text and no artifact references")
    artifact_name = config.get("artifactName", "codex-deliverable.md")
    media_type = config.get("artifactMediaType", "text/markdown")
    if not isinstance(artifact_name, str) or not isinstance(media_type, str):
        raise ExecutorError("codex artifact metadata must be strings")
    return ExecutionResult(
        output=output,
        observations=[result.observation],
        generated_artifact=GeneratedArtifact(
            name=artifact_name,
            media_type=media_type,
            content=text.encode("utf-8"),
        ),
    )


def execute_builtin(
    executor_ref: str,
    input_value: Any,
    config: dict[str, Any],
) -> ExecutionResult:
    if executor_ref == "example.content-fixture.v1":
        if not isinstance(input_value, dict) or not isinstance(input_value.get("goal"), str):
            raise ExecutorError("content producer requires a goal string")
        candidate = input_value.get("deliverable")
        if candidate is not None:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("text"), str):
                raise ExecutorError("content critic requires a deliverable text field")
            return ExecutionResult(
                output={
                    "text": f"Review of: {candidate['text']}",
                    "artifact_refs": [],
                }
            )
        return ExecutionResult(
            output={
                "text": f"Deliverable for: {input_value['goal']}",
                "artifact_refs": [],
            }
        )

    if executor_ref == "builtin.nonempty-deliverable.v1":
        values: dict[str, Any]
        if (
            isinstance(input_value, dict)
            and isinstance(input_value.get("deliverable"), dict)
            and isinstance(input_value.get("agentReview"), dict)
        ):
            values = {
                "deliverable": input_value["deliverable"],
                "agent review": input_value["agentReview"],
            }
        else:
            values = {"deliverable": input_value}
        findings = [
            f"{name} must have non-empty text and an artifact_refs array"
            for name, value in values.items()
            if not (
                isinstance(value, dict)
                and isinstance(value.get("text"), str)
                and bool(value["text"].strip())
                and isinstance(value.get("artifact_refs"), list)
            )
        ]
        return ExecutionResult(
            output={
                "valid": not findings,
                "findings": findings,
            }
        )

    if executor_ref == "builtin.ollama-deliverable.v1":
        if not isinstance(input_value, dict):
            raise ExecutorError("ollama deliverable requires an object input")
        try:
            result = generate_deliverable(input_value, config)
        except OllamaError as exc:
            raise ExecutorError(str(exc)) from exc
        artifact_name = config.get("artifactName", "deliverable.md")
        artifact_media_type = config.get("artifactMediaType", "text/markdown")
        artifact_max_bytes = config.get("artifactMaxBytes", 400_000)
        if not isinstance(artifact_name, str) or not artifact_name.strip():
            raise ExecutorError("ollama artifactName must be a non-empty string")
        if not isinstance(artifact_media_type, str) or not artifact_media_type.strip():
            raise ExecutorError("ollama artifactMediaType must be a non-empty string")
        if not isinstance(artifact_max_bytes, int) or not 1 <= artifact_max_bytes <= 10_000_000:
            raise ExecutorError(
                "ollama artifactMaxBytes must be an integer from 1 to 10000000"
            )
        content = result.output["text"].encode("utf-8")
        if len(content) > artifact_max_bytes:
            raise ExecutorError("ollama artifact exceeds configured size limit")
        return ExecutionResult(
            output=result.output,
            observations=[result.observation],
            generated_artifact=GeneratedArtifact(
                name=artifact_name,
                media_type=artifact_media_type,
                content=content,
            ),
        )

    if executor_ref == "builtin.human-review.v1":
        choices = config.get("choices", ["approve", "reject"])
        authorized_subjects = config.get("authorizedSubjects", ["example-reviewer"])
        if not (
            isinstance(choices, list)
            and all(isinstance(choice, str) for choice in choices)
            and isinstance(authorized_subjects, list)
            and all(isinstance(subject, str) for subject in authorized_subjects)
        ):
            raise ExecutorError(
                "human binding choices and authorizedSubjects must be string arrays"
            )
        return ExecutionResult(
            human_request=HumanRequestSpec(
                request_type=str(config.get("requestType", "review")),
                title=str(config.get("title", "Human review")),
                instructions=str(config.get("instructions", "Review the submitted output.")),
                choices=choices,
                authorized_subjects=authorized_subjects,
            )
        )

    if executor_ref == "builtin.human-input.v1":
        authorized_subjects = config.get("authorizedSubjects", ["example-editor"])
        if not (
            isinstance(authorized_subjects, list)
            and all(isinstance(subject, str) for subject in authorized_subjects)
        ):
            raise ExecutorError("human input authorizedSubjects must be a string array")
        return ExecutionResult(
            human_request=HumanRequestSpec(
                request_type="input",
                title=str(config.get("title", "Human input")),
                instructions=str(
                    config.get("instructions", "Complete the task and submit the result.")
                ),
                choices=[],
                authorized_subjects=authorized_subjects,
            )
        )

    raise ExecutorError(f"unsupported builtin executor: {executor_ref}")
