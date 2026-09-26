import hashlib
import json
import shutil
from pathlib import Path

import pytest

from multiverse_workflow.compiler.preflight import preflight_package
from multiverse_workflow.runtime.catalog import CatalogError, load_executor_registry
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry

ROOT = Path(__file__).parents[2]


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    target = tmp_path / "catalog"
    shutil.copytree(ROOT / "examples/executor-catalog", target)
    return target


def manifest(directory: Path) -> dict:
    return json.loads((directory / "executor-registration.json").read_text())


def save(directory: Path, value: dict) -> None:
    (directory / "executor-registration.json").write_text(json.dumps(value))


def test_default_and_directory_catalog(directory: Path) -> None:
    assert (
        load_executor_registry().capability_catalog()
        == local_executor_registry().capability_catalog()
    )
    registry = load_executor_registry(directory)
    assert registry.resolve("local.process.v1") is not None
    assert preflight_package(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        executor_registry=registry,
    ).ok
    entry = registry.capability_catalog()[0]
    entry["configSchema"].clear()
    assert registry.capability_catalog()[0]["configSchema"]


@pytest.mark.parametrize(
    "change",
    [
        {"adapter": "python"},
        {"executorVersion": "latest"},
        {"contractVersion": "future"},
        {"verified": "yes"},
        {"configSchemaRef": "../outside.json"},
        {"configSchemaDigest": "sha256:" + "0" * 64},
        {"unexpected": "secret"},
        {"supportsCancel": True},
        {"permissionLevel": "enforced"},
    ],
)
def test_invalid_registration(directory: Path, change: dict) -> None:
    value = manifest(directory)
    entry = next(e for e in value["executors"] if e["adapter"] == "local_process")
    entry.update(change)
    save(directory, value)
    with pytest.raises(CatalogError):
        load_executor_registry(directory)


def test_verification_requires_versioned_evidence(directory: Path) -> None:
    value = manifest(directory)
    del value["executors"][0]["verificationEvidence"]
    save(directory, value)
    with pytest.raises(CatalogError, match="evidence"):
        load_executor_registry(directory)


@pytest.mark.parametrize("reference", ["http://example.test/secret", "file:///etc/passwd", "#/x"])
def test_schema_references_cannot_read_external_resources(directory: Path, reference: str) -> None:
    value = manifest(directory)
    entry = value["executors"][0]
    raw = json.dumps({"$ref": reference}).encode()
    (directory / entry["configSchemaRef"]).write_bytes(raw)
    entry["configSchemaDigest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    save(directory, value)
    with pytest.raises(CatalogError, match="references"):
        load_executor_registry(directory)


def test_schema_symlink_escape(directory: Path, tmp_path: Path) -> None:
    entry = manifest(directory)["executors"][0]
    original = directory / entry["configSchemaRef"]
    outside = tmp_path / "outside.json"
    original.rename(outside)
    original.symlink_to(outside)
    with pytest.raises(CatalogError, match="outside"):
        load_executor_registry(directory)


@pytest.mark.parametrize("revoke", ["delete", "change"])
def test_catalog_revocation_blocks_frozen_snapshot(directory: Path, revoke: str) -> None:
    registry = load_executor_registry(directory).snapshot()
    path = directory / "executor-registration.json"
    if revoke == "delete":
        path.unlink()
    else:
        path.write_text(path.read_text() + "\n")
    report = preflight_package(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        executor_registry=registry,
    )
    assert {d.code for d in report.diagnostics} == {"EXECUTOR_CATALOG_REVOKED"}
    assert "executor-config" not in report.as_dict()["checked"]
    assert "executor-config" in report.as_dict()["notChecked"]
    assert "executor-registry" in report.as_dict()["checked"]


@pytest.mark.parametrize(
    "config,field",
    [
        ({"command": []}, "/command"),
        ({"command": ["ok", 1]}, "/command/1"),
        ({"command": ["ok"], "timeoutSeconds": 0}, "/timeoutSeconds"),
        ({"command": ["ok"], "timeoutSeconds": True}, "/timeoutSeconds"),
        ({"command": ["ok"], "secret": "do-not-print"}, "/secret"),
        ({"command": ["ok"], "verified": True}, "/verified"),
    ],
)
def test_config_diagnostics_are_precise_and_redacted(config: dict, field: str) -> None:
    from multiverse_workflow.protocol.loader import load_document
    from multiverse_workflow.protocol.models import BindingSet

    binding = BindingSet.model_validate(
        load_document(ROOT / "examples/bindings/content-local.yaml").value
    )
    slot = binding.spec.slots["producer"]
    slot.executor_ref = "local.process.v1"
    slot.adapter = "local_process"
    slot.config = config
    issues = local_executor_registry().preflight(
        nodes={
            "n": {
                "type": "call",
                "definition": {"slot": "producer", "requires": {"capabilities": []}},
            }
        },
        binding=binding,
    )
    assert any(i.config_pointer == field for i in issues)
    assert "do-not-print" not in repr(issues)


def test_custom_schema_cannot_bypass_backend_whitelist(directory: Path) -> None:
    value = manifest(directory)
    entry = value["executors"][0]
    raw = b"{}"
    (directory / entry["configSchemaRef"]).write_bytes(raw)
    entry["configSchemaDigest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    save(directory, value)
    from jsonschema import Draft202012Validator

    descriptor = load_executor_registry(directory).resolve(entry["executorRef"])
    assert descriptor is not None
    assert not Draft202012Validator(descriptor.config_schema()).is_valid({"unknown": True})


def test_unknown_bundled_executor_rejected(directory: Path) -> None:
    value = manifest(directory)
    value["executors"][0]["executorRef"] = "unknown.builtin.v1"
    save(directory, value)
    with pytest.raises(CatalogError):
        load_executor_registry(directory)


def test_empty_catalog_replaces_defaults(directory: Path) -> None:
    value = manifest(directory)
    value["executors"] = []
    save(directory, value)
    assert load_executor_registry(directory).descriptors() == ()
    assert ExecutorRegistry([]).capability_catalog() == []


def test_config_missing_and_pattern_fields_have_accurate_paths() -> None:
    from dataclasses import replace

    from multiverse_workflow.protocol.loader import load_document
    from multiverse_workflow.protocol.models import BindingSet

    descriptor = local_executor_registry().resolve("local.process.v1")
    assert descriptor is not None
    descriptor = replace(
        descriptor,
        config_schema_json=json.dumps(
            {
                "required": ["cwd", "timeoutSeconds"],
                "patternProperties": {"^command$": {}},
                "additionalProperties": False,
            }
        ),
    )
    binding = BindingSet.model_validate(
        load_document(ROOT / "examples/bindings/content-local.yaml").value
    )
    slot = binding.spec.slots["producer"]
    slot.executor_ref = descriptor.executor_ref
    slot.adapter = descriptor.adapter
    slot.config = {"command": ["echo"], "extra": "redacted"}
    issues = ExecutorRegistry([descriptor]).preflight(
        nodes={
            "n": {
                "type": "call",
                "definition": {"slot": "producer", "requires": {"capabilities": []}},
            }
        },
        binding=binding,
    )
    assert {i.config_pointer for i in issues} == {"/cwd", "/timeoutSeconds", "/extra"}
    assert len(issues) == 3


def test_registration_schema_published_copy_matches_runtime() -> None:
    from multiverse_workflow.runtime.catalog import registration_schema

    assert json.loads((ROOT / "schemas/executor-registration.schema.json").read_text()) == (
        registration_schema()
    )


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "adapter,reference,config",
    [
        ("local_process", "local.process.v1", {"command": ["echo"]}),
        ("http_job", "example.remote-content.v1", {"baseUrl": "http://127.0.0.1:1234"}),
        ("builtin", "builtin.ollama-deliverable.v1", {"model": "example"}),
    ],
)
def test_yaml_nonfinite_timeout_rejected_by_preflight(
    tmp_path: Path,
    number: float,
    adapter: str,
    reference: str,
    config: dict,
) -> None:
    from ruamel.yaml import YAML
    from typer.testing import CliRunner

    from multiverse_workflow.cli.main import app

    yaml = YAML()
    binding = yaml.load(ROOT / "examples/bindings/content-local.yaml")
    producer = binding["spec"]["slots"]["producer"]
    producer.update(
        {
            "adapter": adapter,
            "executorRef": reference,
            "config": {**config, "timeoutSeconds": number},
        }
    )
    target = tmp_path / "binding.yaml"
    yaml.dump(binding, target)
    assert any(token in target.read_text() for token in (".nan", ".inf"))
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(target),
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["planDigests"] == {}
    assert "executor-config" in report["notChecked"]
    assert len(report["diagnostics"]) == 1
    diagnostic = report["diagnostics"][0]
    assert diagnostic["code"] == "NON_FINITE_NUMBER"
    assert diagnostic["pointer"] == "/spec/slots/producer/config/timeoutSeconds"
    assert ".nan" not in result.stdout
    assert ".inf" not in result.stdout


def test_existing_manual_input_binding_passes_catalog_preflight(directory: Path) -> None:
    for registry in (local_executor_registry(), load_executor_registry(directory)):
        report = preflight_package(
            ROOT / "presets/manual-input",
            binding_path=ROOT / "examples/bindings/manual-input-local.yaml",
            executor_registry=registry,
        )
        assert report.ok, report.as_dict()


@pytest.mark.parametrize(
    "config,valid",
    [
        ({"requestType": "input", "choices": []}, True),
        ({"requestType": "input", "choices": [], "requireCommentFor": ["reject"]}, True),
        ({"requestType": "review"}, False),
        ({"requestType": "approval"}, False),
        ({"choices": ["approve"]}, False),
        ({"requireCommentFor": "reject"}, False),
    ],
)
def test_human_input_config_preserves_only_supported_and_legacy_shapes(
    config: dict, valid: bool
) -> None:
    from jsonschema import Draft202012Validator

    from multiverse_workflow.runtime.executors import execute_builtin

    descriptor = local_executor_registry().resolve("builtin.human-input.v1")
    assert descriptor is not None
    assert Draft202012Validator(descriptor.config_schema()).is_valid(config) is valid
    if valid:
        request = execute_builtin(descriptor.executor_ref, {}, config).human_request
        assert request is not None
        assert request.request_type == "input"
        assert request.choices == []


@pytest.mark.parametrize("number", ["1e999", "-1e999"])
@pytest.mark.parametrize("location", ["schema", "manifest"])
def test_catalog_cli_rejects_nested_overflow_numbers(
    directory: Path,
    number: str,
    location: str,
) -> None:
    from typer.testing import CliRunner

    from multiverse_workflow.cli.main import app

    value = manifest(directory)
    if location == "schema":
        entry = value["executors"][0]
        raw = ('{"properties":{"nested":{"minimum":' + number + "}}}").encode()
        (directory / entry["configSchemaRef"]).write_bytes(raw)
        entry["configSchemaDigest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        save(directory, value)
    else:
        save(directory, value)
        path = directory / "executor-registration.json"
        path.write_text(path.read_text().replace('"installed": true', '"installed": ' + number, 1))
    result = CliRunner().invoke(app, ["capabilities", "--registry", str(directory), "--json"])
    assert result.exit_code == 2, result.output
    assert "CATALOG_INVALID" in result.stdout
    json.loads(result.stdout, parse_constant=lambda _: pytest.fail("non-JSON numeric value"))
    assert number not in result.stdout


def test_local_process_preserves_whitespace_arguments(directory: Path) -> None:
    import sys

    from jsonschema import Draft202012Validator

    from multiverse_workflow.runtime.executors import execute_local_process

    config = {
        "command": [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1]))", " "]
    }
    for registry in (local_executor_registry(), load_executor_registry(directory)):
        descriptor = registry.resolve("local.process.v1")
        assert descriptor is not None
        Draft202012Validator(descriptor.config_schema()).validate(config)
    assert execute_local_process({}, config).output == " "


@pytest.mark.parametrize("field", ["executorRef", "executorVersion", "capabilities"])
@pytest.mark.parametrize("suffix", ["\n", "\r", "\u0000", "\u2028"])
def test_catalog_rejects_trailing_control_characters(
    directory: Path, field: str, suffix: str
) -> None:
    value = manifest(directory)
    entry = next(e for e in value["executors"] if e["adapter"] == "local_process")
    if field == "capabilities":
        entry[field][0] += suffix
    else:
        entry[field] += suffix
    save(directory, value)
    with pytest.raises(CatalogError):
        load_executor_registry(directory)


def test_unresolved_executor_does_not_claim_config_checked(tmp_path: Path) -> None:
    from ruamel.yaml import YAML

    yaml = YAML()
    value = yaml.load(ROOT / "examples/bindings/content-local.yaml")
    value["spec"]["slots"]["producer"]["executorRef"] = "missing.executor"
    path = tmp_path / "binding.yaml"
    yaml.dump(value, path)
    report = preflight_package(ROOT / "presets/content-delivery", binding_path=path).as_dict()
    assert not report["ok"]
    assert "executor-config" not in report["checked"]
    assert "executor-config" in report["notChecked"]


def test_registry_config_phase_incomplete_for_unresolved_slots() -> None:
    from multiverse_workflow.protocol.loader import load_document
    from multiverse_workflow.protocol.models import BindingSet

    binding = BindingSet.model_validate(
        load_document(ROOT / "examples/bindings/content-local.yaml").value
    )
    nodes = {
        "n": {"type": "call", "definition": {"slot": "producer", "requires": {"capabilities": []}}}
    }
    assert not ExecutorRegistry([]).preflight_result(nodes=nodes, binding=binding).config_checked
    del binding.spec.slots["producer"]
    assert (
        not local_executor_registry().preflight_result(nodes=nodes, binding=binding).config_checked
    )
