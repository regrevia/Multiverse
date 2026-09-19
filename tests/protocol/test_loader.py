from pathlib import Path

import pytest

from multiverse_workflow.protocol.diagnostics import DiagnosticError
from multiverse_workflow.protocol.loader import load_document


def test_loads_json_compatible_yaml(tmp_path: Path) -> None:
    path = tmp_path / "resource.yaml"
    path.write_text(
        "apiVersion: multiverse/v0.1\nkind: Workflow\nspec:\n  enabled: true\n",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.value["kind"] == "Workflow"
    assert document.value["spec"]["enabled"] is True


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        (
            "duplicate.yaml",
            "metadata:\n  name: first\n  name: second\n",
            "DUPLICATE_KEY",
        ),
        ("alias.yaml", "base: &base {value: 1}\ncopy: *base\n", "YAML_ALIAS_FORBIDDEN"),
        ("tag.yaml", "value: !custom 1\n", "YAML_TAG_FORBIDDEN"),
        ("date.yaml", "date: 2026-09-19\n", "NON_JSON_TYPE"),
        ("nan.yaml", "value: .nan\n", "NON_FINITE_NUMBER"),
        ("large.yaml", "value: 9007199254740992\n", "INTEGER_OUT_OF_RANGE"),
        ("merge.yaml", "base: {value: 1}\nmerged:\n  <<: {other: 2}\n", "YAML_MERGE_FORBIDDEN"),
    ],
)
def test_rejects_non_protocol_yaml(
    tmp_path: Path,
    name: str,
    content: str,
    code: str,
) -> None:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")

    with pytest.raises(DiagnosticError) as exc_info:
        load_document(path)

    assert exc_info.value.diagnostic.code == code


def test_reports_json_pointer_for_duplicate_nested_key(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("spec:\n  nodes:\n    produce: {}\n    produce: {}\n", encoding="utf-8")

    with pytest.raises(DiagnosticError) as exc_info:
        load_document(path)

    assert exc_info.value.diagnostic.pointer == "/spec/nodes/produce"
