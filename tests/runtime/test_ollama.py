import json

import pytest

from multiverse_workflow.runtime import executors
from multiverse_workflow.runtime.ollama import OllamaDeliverable, generate_deliverable


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_generate_deliverable_uses_ollama_json_chat_and_records_usage() -> None:
    captured: dict[str, object] = {}

    def opener(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "model": "qwen3.5:9b",
                "done": True,
                "message": {
                    "content": json.dumps(
                        {"text": "A real model produced this.", "artifact_refs": []}
                    )
                },
                "prompt_eval_count": 21,
                "eval_count": 34,
            }
        )

    result = generate_deliverable(
        {"goal": "write a release note"},
        {"model": "qwen3.5:9b", "systemPrompt": "Return a deliverable JSON object."},
        opener=opener,
    )

    request = captured["request"]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    payload = json.loads(request.data)
    assert payload["model"] == "qwen3.5:9b"
    assert payload["stream"] is False
    assert payload["format"]["required"] == ["text", "artifact_refs"]
    assert result.output == {"text": "A real model produced this.", "artifact_refs": []}
    assert result.observation["model"] == "qwen3.5:9b"
    assert result.observation["promptTokens"] == 21
    assert result.observation["completionTokens"] == 34
    assert result.observation["outputDigest"].startswith("sha256:")


def test_ollama_builtin_returns_the_model_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executors,
        "generate_deliverable",
        lambda *_: OllamaDeliverable(
            output={"text": "A real model produced this.", "artifact_refs": []},
            observation={"model": "qwen3.5:9b", "outputDigest": "sha256:example"},
        ),
    )

    result = executors.execute_builtin(
        "builtin.ollama-deliverable.v1",
        {"goal": "write a release note"},
        {"model": "qwen3.5:9b"},
    )

    assert result.output == {"text": "A real model produced this.", "artifact_refs": []}
    assert result.observations == [
        {"model": "qwen3.5:9b", "outputDigest": "sha256:example"}
    ]
