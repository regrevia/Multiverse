from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


class HostConflict(RuntimeError):
    pass


class HostStore:
    """One live host owns a database; all read/modify/write operations serialize."""

    def __init__(self, database: Path) -> None:
        database = database.resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = database.with_suffix(database.suffix + ".lock").open("a+b")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            raise HostConflict("execution host database already has an owner") from None
        self._mutex = threading.RLock()
        self._db = sqlite3.connect(database, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY, dispatch_key TEXT UNIQUE NOT NULL,
                request_digest TEXT NOT NULL, request_json TEXT NOT NULL,
                phase TEXT NOT NULL, native_json TEXT, observation_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL DEFAULT '[]', cancel_requested INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                execution_id TEXT NOT NULL, cursor INTEGER NOT NULL, observation_json TEXT NOT NULL,
                PRIMARY KEY (execution_id, cursor)
            );
            CREATE TABLE IF NOT EXISTS cancellations (
                command_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL
            );
        """)
        # No monitor remains authoritative after a host restart. Do not relaunch.
        for row in self._db.execute("SELECT id FROM executions WHERE phase != 'final'").fetchall():
            self.update(
                row["id"],
                "unknown",
                final=False,
                error={
                    "code": "HOST_RECOVERY_UNKNOWN",
                    "message": "Native outcome needs reconciliation",
                },
                phase="unknown",
            )

    def close(self) -> None:
        with self._mutex:
            self._db.close()
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._lock_file.close()

    def submit(self, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        encoded = canonical(request)
        request_digest = digest(encoded.encode())
        with self._mutex, self._db:
            existing = self._db.execute(
                "SELECT * FROM executions WHERE dispatch_key=?", (request["dispatchKey"],)
            ).fetchone()
            if existing:
                if existing["request_digest"] != request_digest:
                    raise HostConflict("dispatchKey already has a different request")
                return dict(existing), False
            # Expiry prevents new work, not durable reconciliation of an old identity.
            # Keep lookup, conflict detection and this creation guard under one lock.
            deadline = datetime.fromisoformat(request["deadlineAt"].replace("Z", "+00:00"))
            if deadline.tzinfo is None or deadline <= datetime.now(UTC):
                raise ValueError("new execution deadline must be unexpired")
            ref = "exec-" + uuid.uuid4().hex
            observation = self._observation(ref, 1, "accepted", False, "none")
            self._db.execute(
                """INSERT INTO executions
                (id, dispatch_key, request_digest, request_json, phase, observation_json)
                VALUES (?, ?, ?, ?, 'intent', ?)""",
                (ref, request["dispatchKey"], request_digest, encoded, canonical(observation)),
            )
            self._event(ref, observation)
            return self.get(ref), True

    def get(self, ref: str) -> dict[str, Any]:
        with self._mutex:
            row = self._db.execute("SELECT * FROM executions WHERE id=?", (ref,)).fetchone()
            if row is None:
                raise KeyError(ref)
            return dict(row)

    def lookup(self, key: str) -> dict[str, Any]:
        with self._mutex:
            row = self._db.execute(
                "SELECT id FROM executions WHERE dispatch_key=?", (key,)
            ).fetchone()
            return (
                {"status": "found", "executionRef": row["id"], "dispatchKey": key}
                if row
                else {"status": "not_created", "dispatchKey": key}
            )

    def launch_intent(self, ref: str) -> None:
        with self._mutex, self._db:
            # Publishing possible effects is part of the durable pre-launch intent.
            # Observers must not see effectState=none once native launch may happen.
            self.update(ref, "accepted", phase="launching")

    def associate(self, ref: str, native: dict[str, Any]) -> None:
        with self._mutex, self._db:
            self._db.execute(
                "UPDATE executions SET native_json=? WHERE id=?", (canonical(native), ref)
            )
            self.update(ref, "running", phase="running")

    def cancel(self, ref: str, command: str) -> None:
        with self._mutex, self._db:
            self.get(ref)
            old = self._db.execute(
                "SELECT execution_id FROM cancellations WHERE command_id=?", (command,)
            ).fetchone()
            if old and old[0] != ref:
                raise HostConflict("cancel command belongs to another execution")
            self._db.execute("INSERT OR IGNORE INTO cancellations VALUES (?, ?)", (command, ref))
            self._db.execute("UPDATE executions SET cancel_requested=1 WHERE id=?", (ref,))

    def update(
        self,
        ref: str,
        status: str,
        *,
        final: bool = False,
        phase: str | None = None,
        output: Any = None,
        error: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._mutex, self._db:
            row = self.get(ref)
            old = json.loads(row["observation_json"])
            if old["executionFinal"]:
                return
            observation = self._observation(ref, old["revision"] + 1, status, final, "possible")
            if status == "succeeded":
                observation["effectState"] = "confirmed"
                observation["output"] = output
            if error:
                observation["error"] = error
            if artifacts:
                observation["artifacts"] = artifacts
            self._db.execute(
                """UPDATE executions SET phase=?, observation_json=?, artifacts_json=?
                WHERE id=?""",
                (
                    "final" if final else phase or status,
                    canonical(observation),
                    canonical(artifacts or []),
                    ref,
                ),
            )
            self._event(ref, observation)

    def events(self, ref: str, after: int = 0) -> list[dict[str, Any]]:
        with self._mutex:
            self.get(ref)
            return [
                json.loads(row[0])
                for row in self._db.execute(
                    "SELECT observation_json FROM events WHERE execution_id=? AND cursor>? "
                    "ORDER BY cursor LIMIT 32",
                    (ref, after),
                ).fetchall()
            ]

    def _event(self, ref: str, observation: dict[str, Any]) -> None:
        self._db.execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            (ref, observation["revision"], canonical(observation)),
        )
        self._db.execute(
            "DELETE FROM events WHERE execution_id=? AND cursor<=?",
            (ref, observation["revision"] - 32),
        )

    @staticmethod
    def _observation(
        ref: str, revision: int, status: str, final: bool, effect: str
    ) -> dict[str, Any]:
        return {
            "executionRef": ref,
            "revision": revision,
            "status": status,
            "observedAt": datetime.now(UTC).isoformat(),
            "executionFinal": final,
            "effectState": effect,
            "cursor": revision,
        }


def strict_json(content: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(content, object_pairs_hook=unique)
    canonical(value)  # Reject NaN, Infinity and exponent overflow at every depth.
    return value
