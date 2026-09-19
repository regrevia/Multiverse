import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]


def test_value_expr_schema_accepts_the_four_expression_forms() -> None:
    schema = json.loads((ROOT / "schemas/value-expr.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    for value in (
        {"literal": True},
        {"ref": "input#/goal"},
        {"object": {"goal": {"ref": "input#/goal"}}},
        {"array": [{"literal": "one"}]},
    ):
        assert list(validator.iter_errors(value)) == []


def test_value_expr_schema_rejects_expression_extensions() -> None:
    schema = json.loads((ROOT / "schemas/value-expr.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors = list(validator.iter_errors({"template": "{{ input.goal }}"}))

    assert errors


def test_resource_schemas_reject_unknown_top_level_fields() -> None:
    schema = json.loads((ROOT / "schemas/workflow-package.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    package = {
        "apiVersion": "multiverse/v0.1",
        "kind": "WorkflowPackage",
        "metadata": {"name": "content-delivery", "version": "0.1.0"},
        "spec": {
            "workflows": {"delivery": "workflows/delivery.yaml"},
            "entrypoints": ["delivery"],
            "requiredFeatures": [],
            "unknown": True,
        },
    }

    assert list(validator.iter_errors(package))
