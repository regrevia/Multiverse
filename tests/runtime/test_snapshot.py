from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.runtime.snapshot import export_sqlite_snapshot


def test_sqlite_snapshot_is_deterministic_and_contains_no_row_values(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.db"
    ledger = Ledger(database)
    try:
        ledger.create_queued_run(
            namespace="local",
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"entry": "produce"},
            input_value={"secret": "do-not-export"},
            deadline_at="2099-01-01T00:00:00Z",
            entry_node_id="produce",
            run_id="run-snapshot",
        )
    finally:
        ledger.close()

    first = export_sqlite_snapshot(database)
    second = export_sqlite_snapshot(database)
    assert first == second
    assert first["schemaVersion"] == "multiverse.sqlite-snapshot/v0.2"
    assert first["tables"]["runs"]["rowCount"] == 1
    serialized = json.dumps(first, ensure_ascii=False)
    assert "do-not-export" not in serialized
    assert "run-snapshot" not in serialized


def test_sqlite_snapshot_rejects_missing_database(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="database"):
        export_sqlite_snapshot(tmp_path / "missing.db")


def test_sqlite_snapshot_summarizes_blob_without_exporting_bytes(tmp_path: Path) -> None:
    database = tmp_path / "blob.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE data (id TEXT PRIMARY KEY, payload BLOB)")
        connection.execute(
            "INSERT INTO data VALUES (?, ?)",
            ("blob-1", b"private-bytes"),
        )
    snapshot = export_sqlite_snapshot(database)
    assert snapshot["tables"]["data"]["rowCount"] == 1
    assert "private-bytes" not in json.dumps(snapshot)
    assert snapshot["tables"]["data"]["contentDigest"].startswith("sha256:")
    assert snapshot["tables"]["data"]["contentDigest"] == (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "id": "blob-1",
                    "payload": {
                        "kind": "blob",
                        "size": len(b"private-bytes"),
                        "digest": "sha256:"
                        + hashlib.sha256(b"private-bytes").hexdigest(),
                    }
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        ).hexdigest()
    )


def test_sqlite_snapshot_error_does_not_expose_absolute_path(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.db"
    database.write_bytes(b"not sqlite")
    with pytest.raises(ValueError, match="unreadable") as error:
        export_sqlite_snapshot(database)
    assert str(database) not in str(error.value)
