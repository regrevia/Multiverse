from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
class ExecutionResult:
    output: Any | None = None
    human_request: HumanRequestSpec | None = None


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
