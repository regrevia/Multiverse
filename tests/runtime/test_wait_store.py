from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.wait_store import LedgerWaitStore


def test_ledger_wait_store_exposes_scoped_worker_contract(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        created = ledger.create_queued_run(
            namespace="local",
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"entry": "produce"},
            input_value={"goal": "write"},
            deadline_at="2099-01-01T00:00:00Z",
            entry_node_id="produce",
            run_id="run-wait-store",
        )
        store = LedgerWaitStore(ledger)
        waits = store.list_due_waits(
            namespace="local",
            now="9999-01-01T00:00:00Z",
            limit=10,
        )
        assert waits[0]["run_id"] == created["id"]
        claimed = store.claim_wait(
            namespace="local",
            wait_id=waits[0]["id"],
            worker_id="worker-1",
            now="9999-01-01T00:00:00Z",
        )
        assert claimed is not None
        assert store.complete_wait(
            namespace="local",
            wait_id=claimed["id"],
            worker_id="worker-1",
        )["status"] == "completed"
    finally:
        ledger.close()


def test_wait_store_preserves_namespace_for_queue_recovery(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        ledger.create_queued_run(
            namespace="local",
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"entry": "produce"},
            input_value={"goal": "write"},
            deadline_at="2099-01-01T00:00:00Z",
            entry_node_id="produce",
            run_id="run-wait-store-recovery",
        )
        store = LedgerWaitStore(ledger)
        assert store.list_queued_runs(namespace="local", limit=10)
        assert store.list_queued_runs(namespace="other", limit=10) == []
        assert store.get_wait_by_key(
            namespace="local",
            wait_key="run-start:run-wait-store-recovery",
        ) is not None
        assert store.get_wait_by_key(
            namespace="other",
            wait_key="run-start:run-wait-store-recovery",
        ) is None
    finally:
        ledger.close()


def test_sqlite_wait_store_fences_stale_worker_updates(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        ledger.create_queued_run(
            namespace="local",
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"entry": "produce"},
            input_value={"goal": "write"},
            deadline_at="2099-01-01T00:00:00Z",
            entry_node_id="produce",
            run_id="run-wait-fencing",
        )
        store = LedgerWaitStore(ledger)
        wait_id = store.list_due_waits(
            namespace="local",
            now="9999-01-01T00:00:00Z",
            limit=10,
        )[0]["id"]
        assert store.claim_wait(
            namespace="local",
            wait_id=wait_id,
            worker_id="worker-old",
            now="9999-01-01T00:00:00Z",
        )
        assert (
            store.requeue_stale_waits(
                namespace="local",
                older_than="9999-01-01T00:00:01Z",
                now="9999-01-01T00:00:02Z",
            )
            == 1
        )
        assert store.claim_wait(
            namespace="local",
            wait_id=wait_id,
            worker_id="worker-new",
            now="9999-01-01T00:00:03Z",
        )
        with pytest.raises(LedgerConflict, match="another worker"):
            store.complete_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-old",
            )
        with pytest.raises(LedgerConflict, match="another worker"):
            store.release_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-old",
            )
        with pytest.raises(LedgerConflict, match="another worker"):
            store.reschedule_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-old",
                not_before="9999-01-01T00:00:04Z",
            )
        assert store.reschedule_wait(
            namespace="local",
            wait_id=wait_id,
            worker_id="worker-new",
            not_before="9999-01-01T00:00:04Z",
        )["status"] == "pending"
    finally:
        ledger.close()
