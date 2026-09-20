from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """A local Ollama request could not produce a structured deliverable."""


@dataclass(frozen=True)
class OllamaDeliverable:
    output: dict[str, Any]
    observation: dict[str, object]


def generate_deliverable(
    input_value: dict[str, Any],
    config: dict[str, Any],
    *,
    opener: Callable[..., Any] = urlopen,
) -> OllamaDeliverable:
    goal = input_value.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise OllamaError("ollama deliverable requires a non-empty goal")
    model = config.get("model")
    if not isinstance(model, str) or not model:
        raise OllamaError("ollama config requires a model")
    system_prompt = config.get("systemPrompt", "Return only the requested JSON object.")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise OllamaError("ollama systemPrompt must be a non-empty string")
    endpoint = config.get("endpoint", "http://127.0.0.1:11434/api/chat")
    if not isinstance(endpoint, str) or not endpoint.startswith("http://127.0.0.1:"):
        raise OllamaError("ollama endpoint must use localhost HTTP")
    timeout_seconds = config.get("timeoutSeconds", 120)
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 600:
        raise OllamaError("ollama timeoutSeconds must be an integer from 1 to 600")
    payload = {
        "model": model,
        "stream": False,
        "format": {
            "type": "object",
            "required": ["text", "artifact_refs"],
            "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
                "artifact_refs": {"type": "array", "items": {"type": "string"}},
            },
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Goal: {goal}"},
        ],
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            response_value = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaError(f"ollama request failed: {exc}") from exc
    if not isinstance(response_value, dict):
        raise OllamaError("ollama response must be an object")
    message = response_value.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise OllamaError("ollama response is missing message content")
    try:
        output = json.loads(message["content"])
    except json.JSONDecodeError as exc:
        raise OllamaError("ollama response content is not JSON") from exc
    if not isinstance(output, dict):
        raise OllamaError("ollama response content must be a JSON object")
    text = output.get("text")
    if not isinstance(text, str) or not text.strip():
        raise OllamaError("ollama response requires a non-empty text field")
    artifact_refs = output.get("artifact_refs", [])
    if artifact_refs != []:
        raise OllamaError("ollama response must not provide artifact references")
    encoded_output = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return OllamaDeliverable(
        output=output,
        observation={
            "model": response_value.get("model", model),
            "promptTokens": response_value.get("prompt_eval_count"),
            "completionTokens": response_value.get("eval_count"),
            "outputDigest": f"sha256:{hashlib.sha256(encoded_output.encode()).hexdigest()}",
        },
    )
