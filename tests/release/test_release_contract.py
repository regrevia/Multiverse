"""Release bookkeeping tests; these never certify product/platform acceptance."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
SPEC = ROOT / "docs/spec/MULTIVERSE_SPEC.md"
LEDGER = ROOT / "docs/release/ACCEPTANCE.json"
ID_PATTERN = r"(?:AC|LH|SUP|RDI|CMP|PORT|G|V1)-\d+"
LAYERS = {"static", "contract", "integration", "real_execution", "human"}


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def definitions() -> dict[str, tuple[str, str, str, str | None]]:
    result = {}
    anchor = ""
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        match = re.match(r'<a id="([^"]+)"', line)
        if match:
            anchor = match[1]
        match = re.match(rf"^\| ({ID_PATTERN}) \|(.+)\|$", line)
        if not match:
            continue
        identifier = match[1]
        assert identifier not in result, f"duplicate normative ID: {identifier}"
        cells = [cell.strip() for cell in match[2].split("|")]
        owner = cells[-1] if identifier.startswith("V1-") else None
        requirement = " | ".join(cells[1:-1] if owner else cells[1:])
        result[identifier] = (cells[0], requirement, anchor, owner)
    return result


# These complete criteria span real execution/deployment boundaries. Catalog/preflight
# coverage alone cannot close them, even if declared contributors are accidentally empty.
SIGNOFF_SCOPE = {
    "RDI-01": {"W01", "W02", "W03", "W04", "W05A", "W05B"},
    "RDI-02": {"W01", "W13", "W16", "W24"},
}


def validate_signoff_scope(record: dict[str, Any], owner_closure: set[str]) -> None:
    required = SIGNOFF_SCOPE.get(record["id"], set())
    assert required <= owner_closure, "complete criterion exceeds owner dependency scope"
    assert required <= {record["owner"], *record["contributors"]}, (
        "required execution/deployment evidence contributors are missing"
    )


def validate_traceability(data: dict[str, Any]) -> None:
    normative = definitions()
    records = data["records"] + data["release_gates"]
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids)), "duplicate acceptance ID"
    assert set(ids) == set(normative), "missing or extra acceptance ID"
    assert Counter(item.split("-")[0] for item in ids) == {
        "G": 19,
        "AC": 49,
        "LH": 14,
        "SUP": 28,
        "RDI": 64,
        "CMP": 40,
        "PORT": 8,
        "V1": 16,
    }
    plan = (ROOT / "工作包规划.md").read_text(encoding="utf-8").split("## 附录A：", 1)[1]
    owner_rows = re.findall(rf"^\| ({ID_PATTERN}) \|.*?\[(W\d+[AB]?)\]", plan, re.M)
    owners = dict(owner_rows)
    assert len(owners) == len(owner_rows) == 222
    packages = read_json("docs/development/STATE.json")["work_packages"]
    dependencies = {package["id"]: package["depends_on"] for package in packages}

    def closure(owner: str, visiting: frozenset[str] = frozenset()) -> set[str]:
        assert owner not in visiting, "dependency cycle"
        return {owner}.union(*(closure(dep, visiting | {owner}) for dep in dependencies[owner]))

    assert data["schema_version"] == "multiverse.acceptance/v0.1"
    assert data["spec_revision"] == "2.2.0"
    assert data["target_release"] == "1.0.0"
    for record in records:
        identifier = record["id"]
        title, requirement, anchor, gate_owner = normative[identifier]
        assert record["title"] == title
        assert record["requirement"] == requirement
        assert record["spec_ref"] == f"docs/spec/MULTIVERSE_SPEC.md#{anchor}"
        assert record["owner"] == (gate_owner or owners[identifier])
        assert record["mandatory"] is True, "mandatory criteria cannot leave the denominator"
        assert set(record["contributors"]) <= closure(record["owner"]) - {record["owner"]}
        validate_signoff_scope(record, closure(record["owner"]))
        layers = record["required_evidence_layers"]
        assert layers and len(layers) == len(set(layers)) and set(layers) <= LAYERS
        assert record["test_paths"]
        assert all((ROOT / path).is_file() for path in record["test_paths"])
        assert record["status"] in {"pending", "failed", "passed", "blocked"}
        evidence = record["evidence"]
        for item in evidence:
            assert item["layer"] in LAYERS
            assert item["result"] in {"passed", "failed", "blocked"}
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", item["artifact_digest"])
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", item["snapshot"])
            assert item["path"] and (ROOT / item["path"]).is_file()
        if record["status"] == "passed":
            assert evidence, "passed needs evidence"
            assert all(item["result"] == "passed" for item in evidence)
            assert set(layers) <= {item["layer"] for item in evidence}
            assert len({item["snapshot"] for item in evidence}) == 1
            assert len({item["artifact_digest"] for item in evidence}) == 1
        if record["status"] == "failed":
            assert any(item["result"] == "failed" for item in evidence)
        if record["status"] == "blocked":
            assert record.get("blocker"), "blocked requires an explicit external condition"


def test_all_normative_ids_owners_and_evidence_contracts() -> None:
    validate_traceability(read_json("docs/release/ACCEPTANCE.json"))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "optional", "passed", "owner"])
def test_tracking_rejects_false_completion_or_lost_requirements(mutation: str) -> None:
    data = read_json("docs/release/ACCEPTANCE.json")
    if mutation == "missing":
        data["records"].pop()
    elif mutation == "duplicate":
        data["records"].append(copy.deepcopy(data["records"][0]))
    elif mutation == "optional":
        data["records"][0]["mandatory"] = False
    elif mutation == "passed":
        data["records"][0]["status"] = "passed"
    else:
        data["records"][0]["contributors"] = ["W29"]
    with pytest.raises(AssertionError):
        validate_traceability(data)


def test_future_compatibility_design_is_explicit_and_not_claimed_as_executed() -> None:
    scenarios = read_json("docs/release/ACCEPTANCE.json")["future_compatibility_scenarios"]
    assert {case["id"] for case in scenarios} == {
        "COMPAT-IMPORT",
        "COMPAT-CLIENT",
        "COMPAT-EVENTS",
    }
    for case in scenarios:
        assert case["owner"] in {"W20", "W24", "W25"}
        assert case["status"] == "pending"
        assert case["test_target"].startswith("tests/conformance/test_")
        assert len(case["setup"]) >= 1
        assert len(case["actions"]) >= 3
        assert len(case["assertions"]) >= 3
        assert {"contract", "integration", "real_execution"} <= set(
            case["required_evidence_layers"]
        )


def profile(name: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "profileVersion": "multiverse.deployment-profile/v0.1",
        "profile": name,
        "database": "postgresql17" if name == "team" else "sqlite",
        "scheduler": "single-active",
        "identity": "same-organization" if name == "team" else "single-user",
        "network": "external-denied" if name == "offline" else "policy-controlled",
        "isolation": "enforced" if name == "team" else "trusted-local",
        "optionalCapabilities": [],
    }
    if name == "offline":
        result.update(
            localModelRef="local-resource:model-v1", resourceManifestDigest="sha256:" + "a" * 64
        )
    return result


@pytest.mark.parametrize("name", ["personal", "team", "offline"])
def test_profile_schema_accepts_declared_targets_only(name: str) -> None:
    schema = read_json("schemas/deployment-profile.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(profile(name))


@pytest.mark.parametrize(
    "name,field,value",
    [
        ("team", "database", "sqlite"),
        ("team", "identity", "single-user"),
        ("team", "isolation", "trusted-local"),
        ("personal", "database", "postgresql17"),
        ("personal", "identity", "same-organization"),
        ("offline", "network", "policy-controlled"),
        ("offline", "optionalCapabilities", ["feishu"]),
        ("offline", "optionalCapabilities", ["connector"]),
        ("offline", "localModelRef", "https://example.com/model"),
        ("offline", "resourceManifestDigest", "latest"),
        ("personal", "scheduler", "multi-active"),
        ("personal", "profileVersion", "multiverse.deployment-profile/v9"),
        ("personal", "profile", "enterprise"),
        ("personal", "secret", "inline-secret"),
        ("personal", "localModelRef", "local-resource:model-v1"),
        ("personal", "optionalCapabilities", ["latent", "latent"]),
    ],
)
def test_profile_schema_rejects_incompatible_or_ambiguous_declarations(
    name: str,
    field: str,
    value: Any,
) -> None:
    data = profile(name)
    data[field] = value
    validator = Draft202012Validator(read_json("schemas/deployment-profile.schema.json"))
    assert list(validator.iter_errors(data))


@pytest.mark.parametrize("field", ["localModelRef", "resourceManifestDigest"])
def test_offline_requires_fixed_resource_references(field: str) -> None:
    data = profile("offline")
    del data[field]
    validator = Draft202012Validator(read_json("schemas/deployment-profile.schema.json"))
    assert list(validator.iter_errors(data))


def test_personal_can_explicitly_request_enforced_isolation() -> None:
    data = profile("personal")
    data["isolation"] = "enforced"
    Draft202012Validator(read_json("schemas/deployment-profile.schema.json")).validate(data)


@pytest.mark.parametrize("field", ["localModelRef", "resourceManifestDigest"])
@pytest.mark.parametrize("control", ["\n", "\r", "\r\n", "\t", "\x00", "\x1f", "\u2028", "\u2029"])
def test_profile_identifiers_reject_trailing_control_characters(field: str, control: str) -> None:
    data = profile("offline")
    data[field] += control
    validator = Draft202012Validator(read_json("schemas/deployment-profile.schema.json"))
    assert list(validator.iter_errors(data))


@pytest.mark.parametrize("identifier", ["RDI-01", "RDI-02"])
def test_complete_execution_and_rebinding_cannot_be_signed_off_by_catalog_only(
    identifier: str,
) -> None:
    record = {"id": identifier, "owner": "W01", "contributors": []}
    with pytest.raises(AssertionError, match="owner dependency scope"):
        validate_signoff_scope(record, {"W00", "W01"})


@pytest.mark.parametrize("identifier", ["RDI-01", "RDI-02"])
def test_complete_execution_and_rebinding_require_explicit_evidence_contributors(
    identifier: str,
) -> None:
    records = read_json("docs/release/ACCEPTANCE.json")["records"]
    record = next(item for item in records if item["id"] == identifier)
    record["contributors"] = []
    with pytest.raises(AssertionError, match="contributors are missing"):
        validate_signoff_scope(record, SIGNOFF_SCOPE[identifier] | {record["owner"]})
