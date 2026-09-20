from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from multiverse_workflow.runtime.ollama import OllamaError, generate_deliverable


class ExecutorError(RuntimeError):
    """A local executor cannot produce a valid protocol result."""


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


def execute_builtin(
    executor_ref: str,
    input_value: Any,
    config: dict[str, Any],
) -> ExecutionResult:
    if executor_ref == "example.content-fixture.v1":
        if not isinstance(input_value, dict) or not isinstance(input_value.get("goal"), str):
            raise ExecutorError("content producer requires a goal string")
        return ExecutionResult(
            output={
                "text": f"Deliverable for: {input_value['goal']}",
                "artifact_refs": [],
            }
        )

    if executor_ref == "builtin.nonempty-deliverable.v1":
        valid = (
            isinstance(input_value, dict)
            and isinstance(input_value.get("text"), str)
            and bool(input_value["text"].strip())
            and isinstance(input_value.get("artifact_refs"), list)
        )
        return ExecutionResult(
            output={
                "valid": valid,
                "findings": (
                    []
                    if valid
                    else ["text must be non-empty and artifact_refs must be an array"]
                ),
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
