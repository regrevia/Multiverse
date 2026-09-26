"""Explicit, operator-owned registration directories; never imports plugins."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from multiverse_workflow.runtime.registry import (
    AdapterKind,
    ExecutorDescriptor,
    ExecutorRegistry,
    local_executor_registry,
)


class CatalogError(ValueError):
    """A trusted directory is malformed or no longer matches its frozen snapshot."""


def _read(root: Path, relative: str) -> bytes:
    if Path(relative).is_absolute():
        raise CatalogError("catalog file references must be relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise CatalogError("catalog file is missing or outside the registration directory")
    try:
        return path.read_bytes()
    except OSError:
        raise CatalogError("catalog file cannot be read") from None


def _json(raw: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CatalogError("duplicate catalog JSON key")
            result[key] = value
        return result

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return value

    try:
        return json.loads(
            raw,
            object_pairs_hook=unique,
            parse_float=finite_float,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeDecodeError):
        raise CatalogError("invalid catalog JSON") from None


def registration_schema() -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    props: dict[str, Any] = {
        "executorRef": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*(?![\s\S])"},
        "adapter": {"enum": ["builtin", "local_process", "http_job", "human"]},
        "contractVersion": {"const": "multiverse/v0.1"},
        "executorVersion": {
            "type": "string",
            "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?![\s\S])",
        },
        "capabilities": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "pattern": r"^[a-z][a-z0-9_.-]*@[1-9][0-9]*(?![\s\S])"},
        },
        "observabilityLevel": {"enum": ["structured", "external"]},
        "permissionLevel": {"enum": ["enforced", "trusted_local", "advisory"]},
        "configSchemaRef": text,
        "configSchemaDigest": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}(?![\\s\\S])"},
    }
    props.update(
        {
            key: {"type": "boolean"}
            for key in (
                "supportsCancel",
                "supportsIdempotency",
                "supportsRecoveryQuery",
                "installed",
                "available",
                "verified",
            )
        }
    )
    required = list(props)
    props["verificationEvidence"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "reference", "environment", "executorVersion", "cases"],
        "properties": {
            "kind": {"const": "operator-attestation"},
            "reference": text,
            "environment": text,
            "executorVersion": props["executorVersion"],
            "cases": {"type": "array", "minItems": 1, "items": text},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["catalogVersion", "executors"],
        "properties": {
            "catalogVersion": {"const": "multiverse.executor-catalog/v0.1"},
            "executors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": required,
                    "properties": props,
                },
            },
        },
    }


def _check_schema(value: Any) -> None:
    # W01 deliberately supports self-contained schemas without reference resolution.
    if isinstance(value, dict):
        if any(key in value for key in ("$ref", "$dynamicRef", "$id")):
            raise CatalogError("config Schema references and identifiers are not supported")
        for child in value.values():
            _check_schema(child)
    elif isinstance(value, list):
        for child in value:
            _check_schema(child)


def load_executor_registry(path: Path | None = None) -> ExecutorRegistry:
    if path is None:
        return local_executor_registry()
    root = path.resolve()
    raw = _read(root, "executor-registration.json")
    document = _json(raw)
    if not Draft202012Validator(registration_schema()).is_valid(document):
        raise CatalogError("invalid executor registration shape or version")
    descriptors = []
    fingerprints = {"executor-registration.json": hashlib.sha256(raw).hexdigest()}
    defaults = local_executor_registry()
    for entry in document["executors"]:
        adapter = entry["adapter"]
        reference = entry["executorRef"]
        builtin = defaults.resolve(reference)
        if adapter in {"builtin", "human"} and (builtin is None or builtin.adapter != adapter):
            raise CatalogError("unsupported bundled executor reference")
        if builtin is not None and builtin.adapter != adapter:
            raise CatalogError("bundled executor adapter cannot be replaced")
        if adapter == "local_process" and (
            entry["permissionLevel"] != "trusted_local"
            or any(
                entry[key]
                for key in ("supportsCancel", "supportsIdempotency", "supportsRecoveryQuery")
            )
        ):
            raise CatalogError("local_process cannot claim isolation or recovery guarantees")
        if builtin is not None and adapter in {"builtin", "human"}:
            if not set(entry["capabilities"]).issubset(builtin.capabilities):
                raise CatalogError("bundled executor cannot add unsupported capabilities")
            for key, supported in (
                ("supportsCancel", builtin.supports_cancel),
                ("supportsIdempotency", builtin.supports_idempotency),
                ("supportsRecoveryQuery", builtin.supports_recovery_query),
            ):
                if entry[key] and not supported:
                    raise CatalogError("bundled executor cannot add unsupported guarantees")
        evidence = entry.get("verificationEvidence")
        if entry["verified"] and (not evidence or not entry["installed"] or not entry["available"]):
            raise CatalogError(
                "verified registration requires installation, availability and evidence"
            )
        if evidence and evidence["executorVersion"] != entry["executorVersion"]:
            raise CatalogError("verification evidence version mismatch")
        schema_raw = _read(root, entry["configSchemaRef"])
        digest = hashlib.sha256(schema_raw).hexdigest()
        if entry["configSchemaDigest"] != "sha256:" + digest:
            raise CatalogError("config Schema digest mismatch")
        schema = _json(schema_raw)
        _check_schema(schema)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            raise CatalogError("invalid config Schema") from None
        fingerprints[entry["configSchemaRef"]] = digest
        descriptors.append(
            ExecutorDescriptor(
                executor_ref=reference,
                adapter=cast(AdapterKind, adapter),
                capabilities=frozenset(entry["capabilities"]),
                contract_version=entry["contractVersion"],
                executor_version=entry["executorVersion"],
                supports_cancel=entry["supportsCancel"],
                supports_idempotency=entry["supportsIdempotency"],
                supports_recovery_query=entry["supportsRecoveryQuery"],
                observability_level=entry["observabilityLevel"],
                permission_level=entry["permissionLevel"],
                installed=entry["installed"],
                available=entry["available"],
                verified=entry["verified"],
                config_schema_json=json.dumps(schema),
                config_schema_ref=entry["configSchemaRef"],
                config_schema_digest=entry["configSchemaDigest"],
                verification_evidence_json=json.dumps(evidence) if evidence else None,
            )
        )

    def validate_snapshot() -> None:
        for relative, digest in fingerprints.items():
            if hashlib.sha256(_read(root, relative)).hexdigest() != digest:
                raise CatalogError(
                    "registration snapshot changed; reload explicitly before new work"
                )

    try:
        return ExecutorRegistry(descriptors, snapshot_validator=validate_snapshot)
    except ValueError:
        raise CatalogError("duplicate executor references") from None
