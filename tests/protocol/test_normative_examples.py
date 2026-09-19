import json
from pathlib import Path

from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import BindingSet, Workflow, WorkflowPackage

ROOT = Path(__file__).parents[2]


def test_content_delivery_normative_resources_parse() -> None:
    package = load_document(ROOT / "presets/content-delivery/manifest.yaml").value
    workflow = load_document(ROOT / "presets/content-delivery/workflows/delivery.yaml").value
    binding = load_document(ROOT / "examples/bindings/content-local.yaml").value

    assert WorkflowPackage.model_validate(package).kind == "WorkflowPackage"
    assert Workflow.model_validate(workflow).kind == "Workflow"
    assert BindingSet.model_validate(binding).kind == "BindingSet"


def test_content_delivery_json_schemas_and_eval_dataset_exist() -> None:
    package_root = ROOT / "presets/content-delivery"
    for relative_path in (
        "schemas/request.json",
        "schemas/deliverable.json",
        "schemas/verification.json",
        "schemas/review-input.json",
        "schemas/review-output.json",
        "schemas/final-output.json",
    ):
        schema = json.loads((package_root / relative_path).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    cases = (package_root / "evals/cases.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(case)["case_id"] for case in cases] == [
        "basic-delivery",
        "alternative-topic",
    ]


def test_secondary_binding_is_available() -> None:
    binding = load_document(ROOT / "examples/bindings/content-remote.yaml").value

    assert binding["spec"]["slots"]["producer"]["adapter"] == "http_job"
