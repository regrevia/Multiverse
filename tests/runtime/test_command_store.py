from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.command_store import LedgerCommandStore
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict


def test_ledger_command_store_preserves_namespace_and_idempotency(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        store = LedgerCommandStore(ledger)
        created = store.create_command(
            namespace="local",
            subject="reviewer",
            operation="run.create",
            idempotency_key="command-1",
            fingerprint="sha256:fingerprint",
            resource_id="run-1",
            command_id="cmd-1",
        )
        assert created["status"] == "accepted"
        assert store.get_command(namespace="other", command_id="cmd-1") is None
        assert store.get_command_by_key(
            namespace="local",
            subject="reviewer",
            operation="run.create",
            idempotency_key="command-1",
        )["id"] == "cmd-1"
        assert store.finish_command(
            namespace="local",
            command_id="cmd-1",
            status="completed",
            resource_version=1,
        )["status"] == "completed"
        assert store.finish_command(
            namespace="local",
            command_id="cmd-1",
            status="completed",
            resource_version=1,
        )["status"] == "completed"
        with pytest.raises(LedgerConflict, match="terminal"):
            store.finish_command(
                namespace="local",
                command_id="cmd-1",
                status="rejected",
                error={"code": "late"},
            )
    finally:
        ledger.close()
