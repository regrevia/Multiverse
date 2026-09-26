"""Local Git integration tests: no external services or real remotes."""

import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/milestones.py"
spec = importlib.util.spec_from_file_location("milestones", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Gate = module.Gate


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-b", "dev")
    git(tmp_path, "config", "user.name", "Gate Test")
    git(tmp_path, "config", "user.email", "gate@example.invalid")
    (tmp_path / "app.py").write_text("print('baseline')\n")
    state = {
        "work_packages": [
            {"id": "W00", "status": "pending", "depends_on": [], "report": "reports/W00/REPORT.md"},
            {"id": "W01", "status": "pending", "depends_on": ["W00"]},
            {"id": "W02", "status": "pending", "depends_on": []},
        ],
    }
    save(tmp_path / "docs/development/STATE.json", state)
    git(tmp_path, "add", "app.py", "docs")
    git(tmp_path, "commit", "-m", "baseline")
    return tmp_path


def update(repo, index=0, **fields):
    path = repo / "docs/development/STATE.json"
    state = json.loads(path.read_text())
    state["work_packages"][index].update(fields)
    save(path, state)


def evidence(repo):
    update(repo, status="reviewing")
    snapshot = Gate(repo).snapshot()
    data = {
        "package_id": "W00",
        "snapshot": snapshot,
        "required_tests": ["pytest"],
        "tests": [
            {
                "id": "pytest",
                "command": "pytest -q",
                "cwd": ".",
                "tool_versions": {"pytest": "8"},
                "started_at": "2026-09-26T00:00:00Z",
                "exit_code": 0,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "log_ref": "docs/development/reports/W00/records.txt#test",
                "snapshot_digest": snapshot["digest"],
            }
        ],
        "acceptance": [
            {
                "id": "A1",
                "status": "passed",
                "evidence_ref": "docs/development/reports/W00/records.txt#acceptance",
            }
        ],
        "reviews": [
            {
                "task_id": "review-123",
                "tool": "collaboration.spawn_agent",
                "record_ref": "docs/development/reports/W00/records.txt#approval",
                "scope": ["app.py"],
                "reviewer_role": "independent",
                "verdict": "approved",
                "limitations": [],
                "snapshot_digest": snapshot["digest"],
            }
        ],
    }
    folder = repo / "docs/development/reports/W00"
    save(folder / "EVIDENCE.json", data)
    (folder / "records.txt").write_text("Test/log/approval fixture receipts\n")
    (folder / "REPORT.md").write_text("# W00 actual acceptance report\n")
    return data


def write_evidence(repo, data):
    save(repo / "docs/development/reports/W00/EVIDENCE.json", data)


def completed(repo, receipt=True):
    evidence(repo)
    git(repo, "add", "docs")
    git(repo, "commit", "-m", "implementation")
    commit = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/dev", commit)
    update(repo, status="completed", implementation_commit=commit)
    git(repo, "add", "docs/development/STATE.json")
    git(repo, "commit", "-m", "completion receipt")
    if receipt:
        git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
    return commit


def test_resume_active(repo):
    update(repo, status="testing")
    assert Gate(repo).next() == {"ok": True, "package_id": "W00", "action": "resume"}


def test_dependencies_not_pushed_and_independent_ready(repo):
    update(repo, status="blocked")
    assert Gate(repo).next()["package_id"] == "W02"


@pytest.mark.parametrize("fault", ["review", "snapshot", "test", "live", "untracked", "mode"])
def test_pre_push_rejects_missing_or_stale_evidence(repo, fault):
    data = evidence(repo)
    assert Gate(repo).check("W00")["ok"]
    if fault == "review":
        data["reviews"] = []
    elif fault == "snapshot":
        (repo / "app.py").write_text("changed\n")
    elif fault == "test":
        data["tests"][0]["exit_code"] = 1
    elif fault == "live":
        data["tests"][0].update(live=True, skipped=1)
    elif fault == "untracked":
        (repo / "new.py").write_text("new\n")
    else:
        (repo / "app.py").chmod(0o755)
    write_evidence(repo, data)
    assert not Gate(repo).check("W00")["ok"]


def test_implementation_push_failure_prioritized(repo):
    update(repo, status="push_pending", implementation_commit=git(repo, "rev-parse", "HEAD"))
    assert Gate(repo).next()["action"] == "retry_implementation_push"
    assert not Gate(repo).check("W00", "remote")["ok"]


def test_receipt_pending_then_verified_remote_ancestor(repo):
    completed(repo, receipt=False)
    assert Gate(repo).next()["action"] == "reconcile_remote_receipt"
    assert not Gate(repo).check("W00")["ok"]
    git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
    assert Gate(repo).check("W00")["ok"]
    assert Gate(repo).next()["package_id"] == "W01"
    # Remote can advance; implementation need not equal branch tip.
    (repo / "later.py").write_text("later\n")
    git(repo, "add", "later.py")
    git(repo, "commit", "-m", "later independent work")
    git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
    assert Gate(repo).check("W00")["ok"]


def test_remote_report_tampering_rejected(repo):
    completed(repo)
    (repo / "docs/development/reports/W00/REPORT.md").write_text("different conclusions\n")
    assert not Gate(repo).check("W00")["ok"]


def background(repo, **overrides):
    fields = {
        "source_commit": git(repo, "rev-parse", "HEAD"),
        "artifact_digests": {"image": "sha256:abc"},
        "isolated_environment": {
            "workspace": str(repo.parent / "isolated"),
            "database": "isolated.sqlite",
            "ports": [9012],
        },
        "task_id": "actual-background-task",
        "log_ref": "local-log://soak",
        "checkpoint": "started",
        "next_check_at": "2099-01-01T00:00:00Z",
        "resume_command": "resume actual-background-task",
    }
    fields.update(overrides)
    update(repo, status="waiting_external", background_validation=fields)


def test_waiting_external_due_and_independent_ready(repo):
    background(repo)
    gate = Gate(repo, now=datetime(2026, 9, 26, tzinfo=UTC))
    assert gate.next()["package_id"] == "W02"  # W01 remains locked.
    background(repo, next_check_at="2026-09-25T00:00:00Z")
    assert Gate(repo).next()["action"] == "resume_external"


@pytest.mark.parametrize("field", ["isolated_environment", "resume_command", "log_ref", "task_id"])
def test_waiting_external_missing_isolation_or_recovery_refused(repo, field):
    background(repo, **{field: None})
    assert not Gate(repo).next()["ok"]


def test_waiting_external_same_workspace_refused(repo):
    background(repo, isolated_environment={"workspace": str(repo), "database": "x", "ports": [1]})
    assert not Gate(repo).next()["ok"]


def test_plan_cycles_and_unknown_status(repo):
    update(repo, depends_on=["W01"], status="invented")
    assert len(Gate(repo).plan_errors()) >= 2


def test_cli_json_and_exit_codes(repo, capsys):
    assert module.main(["--repo", str(repo), "check-plan"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert module.main(["--repo", str(repo), "check", "W00"]) == 1
    assert not json.loads(capsys.readouterr().out)["ok"]
    assert module.main(["--repo", str(repo), "check", "missing"]) == 2
    assert not json.loads(capsys.readouterr().out)["ok"]


def test_injected_state_and_report(repo):
    data = evidence(repo)
    # State stays in repo; all snapshot paths remain repo-relative.
    state = json.loads((repo / "docs/development/STATE.json").read_text())
    save(repo / "docs/development/custom.json", state)
    gate = Gate(repo, "docs/development/custom.json")
    data["snapshot"] = gate.snapshot()
    data["tests"][0]["snapshot_digest"] = data["snapshot"]["digest"]
    data["reviews"][0]["snapshot_digest"] = data["snapshot"]["digest"]
    write_evidence(repo, data)
    gate = Gate(repo, "docs/development/custom.json", "docs/development/reports/W00/EVIDENCE.json")
    assert gate.check("W00")["ok"]


def test_missing_and_uncommitted_reference_rejected(repo):
    data = evidence(repo)
    data["reviews"][0]["record_ref"] = "docs/development/reports/W00/missing.txt"
    write_evidence(repo, data)
    assert not Gate(repo).check("W00")["ok"]
    completed(repo)
    (repo / "docs/development/reports/W00/records.txt").write_text("changed receipt")
    assert not Gate(repo).check("W00")["ok"]


@pytest.mark.parametrize(
    "fault", ["missing_log", "stale_snapshot", "missing_command", "bad_counts"]
)
def test_nonrequired_test_records_are_fully_validated(repo, fault):
    data = evidence(repo)
    extra = dict(data["tests"][0], id="extra")
    data["tests"].append(extra)
    write_evidence(repo, data)
    assert Gate(repo).check("W00")["ok"]
    if fault == "missing_log":
        extra["log_ref"] = "docs/development/reports/W00/missing.txt"
    elif fault == "stale_snapshot":
        extra["snapshot_digest"] = "stale"
    elif fault == "missing_command":
        del extra["command"]
    else:
        extra["passed"] = -1
    write_evidence(repo, data)
    assert not Gate(repo).check("W00")["ok"]


@pytest.mark.parametrize("missing_from", ["implementation", "remote"])
def test_nonrequired_log_must_be_preserved_in_git_history(repo, missing_from):
    data = evidence(repo)
    relative = "docs/development/reports/W00/extra-log.txt"
    extra_path = repo / relative
    extra_path.write_text("Actual extra test log fixture\n")
    data["tests"].append(dict(data["tests"][0], id="extra", log_ref=relative))
    write_evidence(repo, data)
    assert Gate(repo).check("W00")["ok"]
    git(repo, "add", "docs")
    if missing_from == "implementation":
        git(repo, "reset", "HEAD", "--", relative)
    git(repo, "commit", "-m", "implementation")
    commit = git(repo, "rev-parse", "HEAD")
    update(repo, status="completed", implementation_commit=commit)
    git(repo, "add", "docs")
    if missing_from == "remote":
        git(repo, "rm", "--cached", relative)
    git(repo, "commit", "-m", "receipt with inconsistent log")
    git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
    result = Gate(repo).check("W00")
    assert not result["ok"]
    assert "evidence reference not preserved in implementation and remote" in result["errors"]


def test_required_record_cannot_be_omitted(repo):
    data = evidence(repo)
    data["required_tests"].append("missing-required")
    write_evidence(repo, data)
    result = Gate(repo).check("W00")
    assert "missing-required: required test record missing" in result["errors"]
