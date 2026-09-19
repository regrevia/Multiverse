import pytest
from pydantic import TypeAdapter, ValidationError

from multiverse_workflow.protocol.models import (
    BindingSet,
    Node,
    Predicate,
    ValueExpr,
    Workflow,
    WorkflowPackage,
)


def test_workflow_package_has_strict_top_level_contract() -> None:
    package = WorkflowPackage.model_validate(
        {
            "apiVersion": "multiverse/v0.1",
            "kind": "WorkflowPackage",
            "metadata": {"name": "content-delivery", "version": "0.1.0"},
            "spec": {
                "workflows": {"delivery": "workflows/delivery.yaml"},
                "entrypoints": ["delivery"],
                "requiredFeatures": ["core.call"],
            },
        }
    )

    assert package.metadata.name == "content-delivery"
    assert package.spec.workflows["delivery"] == "workflows/delivery.yaml"


def test_unknown_protocol_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkflowPackage.model_validate(
            {
                "apiVersion": "multiverse/v0.1",
                "kind": "WorkflowPackage",
                "metadata": {"name": "content-delivery", "version": "0.1.0"},
                "spec": {
                    "workflows": {"delivery": "workflows/delivery.yaml"},
                    "entrypoints": ["delivery"],
                    "requiredFeatures": [],
                    "unknown": True,
                },
                "unexpected": True,
            }
        )


def test_value_expr_supports_only_literal_ref_object_and_array() -> None:
    adapter = TypeAdapter(ValueExpr)

    assert adapter.validate_python({"literal": None}).literal is None
    assert adapter.validate_python({"ref": "input#/goal"}).ref == "input#/goal"
    assert adapter.validate_python({"object": {"goal": {"ref": "input#/goal"}}})
    assert adapter.validate_python({"array": [{"literal": "one"}]})

    with pytest.raises(ValidationError):
        adapter.validate_python({"template": "{{ input.goal }}"})


def test_predicate_composition_requires_non_empty_operands() -> None:
    adapter = TypeAdapter(Predicate)

    predicate = adapter.validate_python(
        {
            "all": [
                {
                    "op": "eq",
                    "left": {"ref": "nodes.verify.output#/valid"},
                    "right": {"literal": True},
                }
            ]
        }
    )
    assert predicate.all is not None

    with pytest.raises(ValidationError):
        adapter.validate_python({"any": []})


def test_switch_requires_default_and_repeat_is_bounded() -> None:
    node_adapter = TypeAdapter(Node)
    switch = {
        "type": "switch",
        "cases": [
            {
                "id": "valid",
                "when": {
                    "op": "eq",
                    "left": {"ref": "nodes.verify.output#/valid"},
                    "right": {"literal": True},
                },
                "next": "complete",
            }
        ],
        "default": "invalid",
    }
    assert node_adapter.validate_python(switch).type == "switch"

    with pytest.raises(ValidationError):
        node_adapter.validate_python({"type": "switch", "cases": [], "default": "invalid"})

    with pytest.raises(ValidationError):
        node_adapter.validate_python(
            {
                "type": "repeat",
                "workflow": "repair-round",
                "input": {"ref": "input#"},
                "until": {"any": [{"literal": True}]},
                "feedback": {"ref": "iteration.output#"},
                "maxIterations": 21,
                "next": "complete",
            }
        )


def test_workflow_and_binding_resources_validate() -> None:
    workflow = Workflow.model_validate(
        {
            "apiVersion": "multiverse/v0.1",
            "kind": "Workflow",
            "metadata": {"name": "delivery", "version": "0.1.0"},
            "spec": {
                "inputSchema": "schemas/request.json",
                "outputSchema": "schemas/final-output.json",
                "entry": "produce",
                "nodes": {
                    "produce": {
                        "type": "call",
                        "slot": "producer",
                        "inputSchema": "schemas/request.json",
                        "outputSchema": "schemas/deliverable.json",
                        "input": {"ref": "input#"},
                        "requires": {"capabilities": ["content.produce@1"]},
                        "effects": {"class": "write", "actions": ["content.produce"]},
                        "next": "complete",
                    },
                    "complete": {
                        "type": "end",
                        "outcome": "succeeded",
                        "output": {"ref": "nodes.produce.output#"},
                    },
                },
            },
        }
    )
    assert workflow.spec.nodes["produce"].type == "call"

    binding = BindingSet.model_validate(
        {
            "apiVersion": "multiverse/v0.1",
            "kind": "BindingSet",
            "metadata": {"name": "content-local", "version": "0.1.0"},
            "spec": {
                "slots": {
                    "producer": {
                        "adapter": "builtin",
                        "executorRef": "example.content-fixture.v1",
                        "config": {},
                        "secretRefs": {},
                        "grants": [{"action": "content.produce", "resource": "namespace:demo"}],
                    }
                }
            },
        }
    )
    assert binding.spec.slots["producer"].adapter == "builtin"
