import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from typer.testing import CliRunner

from multiverse_workflow.cli.main import app
from multiverse_workflow.compiler import preflight as preflight_module
from multiverse_workflow.compiler.preflight import preflight_package
from multiverse_workflow.protocol.models import BindingSet
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
LOCAL = ROOT / "examples/bindings/content-local.yaml"
REMOTE = ROOT / "examples/bindings/content-remote.yaml"


def test_static_valid_remote_binding_reports_all_registry_gaps() -> None:
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            str(PACKAGE),
            "--binding",
            str(REMOTE),
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert {d["code"] for d in report["diagnostics"]} == {
        "EXECUTOR_NOT_INSTALLED",
        "EXECUTOR_UNAVAILABLE",
        "EXECUTOR_UNVERIFIED",
        "EXECUTOR_CONFIG_INVALID",
    }
    for diagnostic in report["diagnostics"]:
        slot = diagnostic["details"]["slot"]
        node = {"producer": "produce", "critic": "critique"}[slot]
        assert diagnostic["pointer"] == (
            f"/spec/slots/{slot}/config/baseUrl"
            if diagnostic["code"] == "EXECUTOR_CONFIG_INVALID"
            else f"/spec/slots/{slot}/executorRef"
        )
        assert diagnostic["details"]["nodeId"] == node
        assert diagnostic["details"]["source"]["pointer"] == f"/spec/nodes/{node}"
        assert diagnostic["suggestion"]


def test_local_preflight_is_deterministic_and_does_not_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import multiverse_workflow.runtime.executors as executors
    from multiverse_workflow.runtime.runner import Runner

    def forbid(*args: object, **kwargs: object) -> None:
        pytest.fail("preflight must not execute work or construct a Runner")

    monkeypatch.setattr(executors, "execute_builtin", forbid)
    monkeypatch.setattr(executors, "execute_local_process", forbid)
    monkeypatch.setattr(Runner, "__init__", forbid)
    monkeypatch.chdir(tmp_path)
    command = ["preflight", str(PACKAGE), "--binding", str(LOCAL), "--json"]
    first = CliRunner().invoke(app, command)
    second = CliRunner().invoke(app, command)
    assert first.exit_code == second.exit_code == 0, first.output
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["ok"] is True
    assert report["scope"] == "local-registry"
    assert "authorization" in report["notChecked"]
    assert "sandbox-enforcement" in report["notChecked"]
    assert report["planDigests"]["delivery"].startswith("sha256:")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "package,binding",
    [
        (ROOT / "missing-package", LOCAL),
        (PACKAGE, ROOT / "missing-binding.yaml"),
        (ROOT / "tests/fixtures/invalid/dangling-edge", LOCAL),
    ],
)
def test_invalid_inputs_return_machine_readable_diagnostics(package: Path, binding: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            str(package),
            "--binding",
            str(binding),
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert report["planDigests"] == {}
    assert "executor-registry" in report["notChecked"]
    assert report["diagnostics"]


def test_registry_snapshot_can_report_only_unverified_without_claiming_other_gaps() -> None:
    registry = ExecutorRegistry(
        [
            replace(d, verified=False) if d.executor_ref == "example.content-fixture.v1" else d
            for d in local_executor_registry().descriptors()
        ]
    )
    report = preflight_package(PACKAGE, binding_path=LOCAL, executor_registry=registry)
    assert {d.code for d in report.diagnostics} == {"EXECUTOR_UNVERIFIED"}
    assert {d.details["nodeId"] for d in report.diagnostics} == {"produce", "critique"}


def test_binding_changes_between_compile_and_preflight_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.protocol.loader import LoadedDocument

    original_load = preflight_module.load_document

    def changed_load(path: Path) -> LoadedDocument:
        document = original_load(path)
        binding = BindingSet.model_validate(document.value)
        binding.spec.slots["producer"].config["changed"] = True
        return LoadedDocument(
            path=document.path,
            value=binding.model_dump(mode="json", by_alias=True),
        )

    monkeypatch.setattr(preflight_module, "load_document", changed_load)
    report = preflight_package(PACKAGE, binding_path=LOCAL)
    assert not report.ok
    assert report.diagnostics[0].code == "BINDING_CHANGED_DURING_PREFLIGHT"


def test_local_process_catalog_does_not_claim_a_sandbox() -> None:
    descriptor = local_executor_registry().resolve("local.process.v1")
    assert descriptor is not None
    assert descriptor.as_catalog_entry()["permissionLevel"] == "trusted_local"


def test_capability_mismatch_points_to_existing_binding_field(tmp_path: Path) -> None:
    yaml = YAML()
    binding = yaml.load(LOCAL)
    binding["spec"]["slots"]["producer"]["executorRef"] = "builtin.nonempty-deliverable.v1"
    binding_path = tmp_path / "binding.yaml"
    yaml.dump(binding, binding_path)
    report = preflight_package(PACKAGE, binding_path=binding_path)
    diagnostic = next(d for d in report.diagnostics if d.code == "CAPABILITY_MISMATCH")
    assert diagnostic.file == str(binding_path)
    value = binding
    for part in diagnostic.pointer.lstrip("/").split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    assert value == "builtin.nonempty-deliverable.v1"
    assert diagnostic.details["requiredCapability"] == "content.produce@1"
    assert diagnostic.suggestion


def test_preflight_checks_non_entrypoint_workflows(tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    yaml = YAML()
    manifest_path = package / "manifest.yaml"
    manifest = yaml.load(manifest_path)
    # An additional child workflow is not an entrypoint, but still needs checking.
    workflow = yaml.load(package / "workflows/delivery.yaml")
    workflow["metadata"]["name"] = "child"
    yaml.dump(workflow, package / "workflows/child.yaml")
    manifest["spec"]["workflows"]["child"] = "workflows/child.yaml"
    yaml.dump(manifest, manifest_path)
    report = preflight_package(package, binding_path=REMOTE)
    assert not report.ok
    assert set(report.plan_digests) == {"delivery", "child"}
    assert {d.details["workflowId"] for d in report.diagnostics} == {"delivery", "child"}


def test_remote_preflight_does_not_connect_to_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def forbid(*args: object, **kwargs: object) -> None:
        pytest.fail("preflight must not contact external services")

    monkeypatch.setattr(socket.socket, "connect", forbid)
    assert not preflight_package(PACKAGE, binding_path=REMOTE).ok


@pytest.mark.parametrize(
    "package,binding",
    [
        (PACKAGE, LOCAL),
        (PACKAGE, REMOTE),
        (ROOT / "missing-package", LOCAL),
    ],
)
def test_preflight_report_matches_schema(package: Path, binding: Path) -> None:
    schema = json.loads((ROOT / "schemas/preflight-report.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    payload = preflight_package(package, binding_path=binding).as_dict()
    validator.validate(payload)
    payload["ok"] = not payload["ok"]
    assert list(validator.iter_errors(payload))
