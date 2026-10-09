"""Config shapes implemented by the bundled adapters (no executable extensions)."""

from __future__ import annotations

from typing import Any


def executor_config_schema(adapter: str, executor_ref: str) -> dict[str, Any]:
    text = {"type": "string", "minLength": 1, "pattern": r"\S"}
    strings = {"type": "array", "items": {"type": "string"}}
    properties: dict[str, Any] = {}
    required: list[str] = []
    if adapter == "local_process":
        properties = {
            "command": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0},
            "cwd": text,
        }
        required = ["command"]
    elif adapter == "http_job":
        properties = {
            "baseUrl": {"type": "string", "pattern": r"^https?://[^\s/?#]+(?:/[^\s?#]*)?$"},
            "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0},
        }
        required = ["baseUrl"]
    elif adapter == "codex":
        properties = {
            "cwd": text,
            "workspaceRoot": text,
            "homeDir": text,
            "interactionAuthorizedSubjects": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": text,
            },
            "model": text,
            "systemPrompt": text,
            "approvalPolicy": {"enum": ["never", "on-request", "untrusted"]},
            "sandboxMode": {
                "enum": ["read-only", "workspace-write", "danger-full-access"]
            },
            "command": {"type": "array", "minItems": 1, "items": text},
            "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
            "maxOutputBytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
            "sessionMode": {"enum": ["new", "resume", "fork"]},
            "nativeSessionId": text,
            "artifactName": text,
            "artifactMediaType": text,
        }
        required = [
            "cwd",
            "workspaceRoot",
            "homeDir",
            "model",
            "interactionAuthorizedSubjects",
        ]
    elif adapter == "claude":
        properties = {
            "cwd": text,
            "workspaceRoot": text,
            "homeDir": text,
            "model": text,
            "expectedVersion": text,
            "configSource": {"enum": ["cc-switch"]},
            "ccSwitchDatabase": text,
            "ccSwitchProfileId": text,
            "ccSwitchModelAlias": text,
            "systemPrompt": text,
            "permissionMode": {
                "enum": ["default", "dontAsk", "plan", "acceptEdits"]
            },
            "outputFormat": {"enum": ["json", "stream-json"]},
            "sessionPersistence": {"type": "boolean"},
            "sessionId": {"type": "string", "format": "uuid"},
            "resumeSessionId": {"type": "string", "format": "uuid"},
            "forkSession": {"type": "boolean"},
            "command": {"type": "array", "minItems": 1, "items": text},
            "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
            "maxOutputBytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
            "artifactName": text,
            "artifactMediaType": text,
        }
        required = ["cwd", "workspaceRoot", "homeDir", "expectedVersion"]
    elif adapter == "pi":
        properties = {
            "cwd": text,
            "workspaceRoot": text,
            "homeDir": text,
            "model": text,
            "expectedVersion": text,
            "systemPrompt": text,
            "command": {"type": "array", "minItems": 1, "items": text},
            "timeoutSeconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600},
            "maxOutputBytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
            "artifactName": text,
            "artifactMediaType": text,
        }
        required = ["cwd", "workspaceRoot", "homeDir", "expectedVersion"]
    elif executor_ref == "builtin.ollama-deliverable.v1":
        properties = {
            "model": text,
            "systemPrompt": text,
            "endpoint": {"type": "string", "pattern": r"^http://127\.0\.0\.1:"},
            "timeoutSeconds": {"type": "integer", "minimum": 1, "maximum": 600},
            "artifactName": text,
            "artifactMediaType": text,
            "artifactMaxBytes": {"type": "integer", "minimum": 1, "maximum": 10_000_000},
        }
        required = ["model"]
    elif adapter == "human":
        properties = {
            "title": {"type": "string"},
            "instructions": {"type": "string"},
            "authorizedSubjects": strings,
        }
        if executor_ref == "builtin.human-review.v1":
            properties.update(
                {
                    "requestType": {"enum": ["review", "approval"]},
                    "choices": strings,
                    "requireCommentFor": strings,
                }
            )
        elif executor_ref == "builtin.human-input.v1":
            properties.update(
                {
                    "requestType": {"const": "input"},
                    "choices": {"type": "array", "maxItems": 0},
                    "requireCommentFor": {
                        **strings,
                        "deprecated": True,
                        "description": "Legacy compatibility only; ignored for input requests.",
                    },
                }
            )
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if adapter == "claude":
        schema["allOf"] = [
            {
                "if": {
                    "required": ["sessionId"],
                },
                "then": {
                    "properties": {"sessionPersistence": {"const": True}},
                    "required": ["sessionPersistence"],
                },
            },
            {
                "if": {
                    "required": ["resumeSessionId"],
                },
                "then": {
                    "properties": {"sessionPersistence": {"const": True}},
                    "required": ["sessionPersistence"],
                },
            },
            {
                "if": {
                    "properties": {"forkSession": {"const": True}},
                    "required": ["forkSession"],
                },
                "then": {"required": ["resumeSessionId"]},
            },
            {
                "if": {"required": ["sessionId", "resumeSessionId"]},
                "then": {"not": {}},
            },
        ]
    return schema
