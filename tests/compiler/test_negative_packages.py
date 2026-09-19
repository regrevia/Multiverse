from pathlib import Path

import pytest

from multiverse_workflow.compiler.compiler import compile_package

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("dangling-edge", "INVALID_EDGE"),
        ("same-level-cycle", "GRAPH_CYCLE"),
        ("missing-data-reference", "DATA_REFERENCE_MISSING"),
        ("switch-without-default", "INVALID_SPEC"),
        ("repeat-overflow", "INVALID_SPEC"),
        ("unknown-required-feature", "UNSUPPORTED_FEATURE"),
        ("secret-material", "PACKAGE_SECRET_MATERIAL"),
    ],
)
def test_p0_negative_package_is_rejected(fixture: str, code: str) -> None:
    result = compile_package(ROOT / "tests/fixtures/invalid" / fixture)

    assert not result.ok
    assert result.diagnostics[0].code == code
