from pathlib import Path

from multiverse_workflow.compiler.references import validate_schema_file


def test_schema_validation_rejects_a_missing_local_fragment(tmp_path: Path) -> None:
    root = tmp_path / "package"
    root.mkdir()
    (root / "root.json").write_text(
        """\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$ref": "child.json#/$defs/missing"
}
""",
        encoding="utf-8",
    )
    (root / "child.json").write_text(
        """\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$defs": {"present": {"type": "string"}}
}
""",
        encoding="utf-8",
    )

    _, diagnostic = validate_schema_file(root / "root.json", root)

    assert diagnostic is not None
    assert diagnostic.code == "SCHEMA_REF_NOT_FOUND"
