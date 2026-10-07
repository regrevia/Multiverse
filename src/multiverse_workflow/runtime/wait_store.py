from __future__ import annotations

from typing import Any, Protocol

from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.storage.repository import PostgresLedgerRepository


class WaitStore(Protocol):
    """Scoped durable wait operations used by the scheduler boundary."""

    def list_due_waits(
        self, *, namespace: str, now: str, limit: int
    ) -> list[dict[str, Any]]: ...

    def claim_wait(
        self, *, namespace: str, wait_id: str, worker_id: str, now: str
    ) -> dict[str, Any] | None: ...

    def complete_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]: ...

    def release_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]: ...

    def reschedule_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
        not_before: str,
    ) -> dict[str, Any]: ...

    def requeue_stale_waits(
        self, *, namespace: str, older_than: str, now: str
    ) -> int: ...

    def list_queued_runs(
        self, *, namespace: str, limit: int
    ) -> list[dict[str, Any]]: ...

    def get_wait_by_key(
        self, *, namespace: str, wait_key: str
    ) -> dict[str, Any] | None: ...


class LedgerWaitStore:
    """Adapt the existing SQLite Ledger to the scoped scheduler contract."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def list_due_waits(
        self, *, namespace: str, now: str, limit: int
    ) -> list[dict[str, Any]]:
        return self._ledger.list_due_waits(namespace=namespace, now=now, limit=limit)

    def claim_wait(
        self, *, namespace: str, wait_id: str, worker_id: str, now: str
    ) -> dict[str, Any] | None:
        wait = self._ledger.get_wait(wait_id)
        if wait is None or wait["namespace"] != namespace:
            return None
        return self._ledger.claim_wait(wait_id, worker_id=worker_id, now=now)

    def complete_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]:
        return self._ledger.complete_wait_owned(
            wait_id,
            namespace=namespace,
            worker_id=worker_id,
        )

    def release_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]:
        return self._ledger.release_wait_owned(
            wait_id,
            namespace=namespace,
            worker_id=worker_id,
        )

    def reschedule_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
        not_before: str,
    ) -> dict[str, Any]:
        return self._ledger.reschedule_wait_owned(
            wait_id,
            namespace=namespace,
            worker_id=worker_id,
            not_before=not_before,
        )

    def requeue_stale_waits(
        self, *, namespace: str, older_than: str, now: str
    ) -> int:
        return self._ledger.requeue_stale_waits(
            namespace=namespace,
            older_than=older_than,
            now=now,
        )

    def list_queued_runs(
        self, *, namespace: str, limit: int
    ) -> list[dict[str, Any]]:
        return self._ledger.list_queued_runs(namespace=namespace, limit=limit)

    def get_wait_by_key(
        self, *, namespace: str, wait_key: str
    ) -> dict[str, Any] | None:
        wait = self._ledger.get_wait_by_key(namespace, wait_key)
        if wait is None:
            return None
        return wait if wait["namespace"] == namespace else None

class PostgresWaitStore:
    """Adapt the PostgreSQL Repository to the same scheduler contract."""

    def __init__(self, repository: PostgresLedgerRepository) -> None:
        self._repository = repository

    def list_due_waits(
        self, *, namespace: str, now: str, limit: int
    ) -> list[dict[str, Any]]:
        return self._repository.list_due_wait_records(
            namespace=namespace,
            now=now,
            limit=limit,
        )

    def claim_wait(
        self, *, namespace: str, wait_id: str, worker_id: str, now: str
    ) -> dict[str, Any] | None:
        return self._repository.claim_wait(
            namespace=namespace,
            wait_id=wait_id,
            worker_id=worker_id,
            now=now,
        )

    def complete_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]:
        return self._repository.complete_wait(
            namespace=namespace,
            wait_id=wait_id,
            worker_id=worker_id,
        )

    def release_wait(
        self, *, namespace: str, wait_id: str, worker_id: str
    ) -> dict[str, Any]:
        return self._repository.release_wait(
            namespace=namespace,
            wait_id=wait_id,
            worker_id=worker_id,
        )

    def reschedule_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
        not_before: str,
    ) -> dict[str, Any]:
        return self._repository.reschedule_wait(
            namespace=namespace,
            wait_id=wait_id,
            worker_id=worker_id,
            not_before=not_before,
        )

    def requeue_stale_waits(
        self, *, namespace: str, older_than: str, now: str
    ) -> int:
        return self._repository.requeue_stale_waits(
            namespace=namespace,
            older_than=older_than,
            now=now,
        )

    def list_queued_runs(
        self, *, namespace: str, limit: int
    ) -> list[dict[str, Any]]:
        return self._repository.list_queued_runs(namespace=namespace, limit=limit)

    def get_wait_by_key(
        self, *, namespace: str, wait_key: str
    ) -> dict[str, Any] | None:
        return self._repository.get_wait_by_key(
            namespace=namespace,
            wait_key=wait_key,
        )
