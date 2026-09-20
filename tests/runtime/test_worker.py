from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from multiverse_workflow.runtime.runner import Runner
from multiverse_workflow.runtime.worker import LocalWorker, WorkerLockError

ROOT = Path(__file__).parents[2]


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def test_worker_once_processes_due_waits_and_returns_idle_cycle(tmp_path: Path) -> None:
    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="test-worker",
    )

    try:
        assert worker.run_once() == []
    finally:
        worker.close()


def test_worker_recovers_stale_claimed_wait_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests(waiting["id"])[0]
    original_drive = runner._drive
    monkeypatch.setattr(
        runner,
        "_drive",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated worker interruption")
        ),
    )
    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        runner.decide(
            request["id"],
            choice="approve",
            comment="Approved.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="worker-recovery",
        )
    monkeypatch.setattr(runner, "_drive", original_drive)
    progress_wait = runner.ledger.get_wait_by_key(
        "local", f"human-progress:{request['id']}"
    )
    assert progress_wait is not None
    due = _timestamp(datetime.now(UTC) - timedelta(seconds=1))
    runner.ledger.update_wait(progress_wait["id"], not_before=due)
    claimed = runner.ledger.claim_wait(
        progress_wait["id"],
        worker_id="crashed-worker",
        now=due,
    )
    assert claimed is not None
    runner.close()

    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="restarted-worker",
        claim_timeout_seconds=0,
    )
    try:
        results = worker.run_once()
        assert results[0]["request_id"] == request["id"]
        ledger = worker.runner.ledger
        assert ledger.get_wait(progress_wait["id"])["status"] == "completed"
        assert ledger.get_run(waiting["id"])["status"] == "succeeded"
    finally:
        worker.close()


def test_worker_lock_allows_only_one_active_worker(tmp_path: Path) -> None:
    first = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="first-worker",
    )
    try:
        with pytest.raises(WorkerLockError, match="worker lock"):
            LocalWorker.from_paths(
                package_dir=ROOT / "presets/content-delivery",
                binding_path=ROOT / "examples/bindings/content-local.yaml",
                database_path=tmp_path / "runtime.db",
                worker_id="second-worker",
            )
    finally:
        first.close()


def test_worker_close_releases_lock(tmp_path: Path) -> None:
    first = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="first-worker",
    )
    first.close()

    second = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="second-worker",
    )
    second.close()
