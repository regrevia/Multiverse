from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.storage.repository import PostgresLedgerRepository


class CommandStoreConflict(LedgerConflict):
    """The command key or terminal transition conflicts with persisted state."""


class CommandStore(Protocol):
    """Durable command receipt operations shared by local and service storage."""

    def create_command(
        self,
        *,
        namespace: str,
        subject: str,
        operation: str,
        idempotency_key: str,
        fingerprint: str,
        resource_id: str,
        command_id: str,
    ) -> dict[str, Any]: ...

    def get_command(
        self, *, namespace: str, command_id: str
    ) -> dict[str, Any] | None: ...

    def get_command_by_key(
        self,
        *,
        namespace: str,
        subject: str,
        operation: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None: ...

    def list_commands_by_key(
        self, *, namespace: str, idempotency_key: str
    ) -> list[dict[str, Any]]: ...

    def finish_command(
        self,
        *,
        namespace: str,
        command_id: str,
        status: str,
        resource_version: int | None = None,
        error: Any = None,
    ) -> dict[str, Any]: ...

    def assert_bound_to(self, ledger: Ledger) -> None: ...


class LedgerCommandStore:
    """Adapter for the existing SQLite Ledger command receipt methods."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def assert_bound_to(self, ledger: Ledger) -> None:
        if self._ledger is not ledger:
            raise ValueError("CommandStore must be bound to the Runtime Ledger")

    def create_command(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._ledger.create_command(**kwargs)
        except sqlite3.IntegrityError as exc:
            raise CommandStoreConflict("command idempotency conflict") from exc

    def get_command(
        self, *, namespace: str, command_id: str
    ) -> dict[str, Any] | None:
        command = self._ledger.get_command(command_id)
        if command is None or command["namespace"] != namespace:
            return None
        return command

    def get_command_by_key(
        self,
        *,
        namespace: str,
        subject: str,
        operation: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return self._ledger.get_command_by_key(
            idempotency_key,
            namespace=namespace,
            subject=subject,
            operation=operation,
        )

    def list_commands_by_key(
        self, *, namespace: str, idempotency_key: str
    ) -> list[dict[str, Any]]:
        return self._ledger.list_commands_by_key(
            idempotency_key,
            namespace=namespace,
        )

    def finish_command(self, **kwargs: Any) -> dict[str, Any]:
        namespace = str(kwargs.pop("namespace"))
        command_id = str(kwargs["command_id"])
        command = self.get_command(namespace=namespace, command_id=command_id)
        if command is None:
            raise KeyError(f"command not found: {command_id}")
        return self._ledger.finish_command(**kwargs)


class PostgresCommandStore:
    """Adapter for the PostgreSQL command receipt repository methods."""

    def __init__(self, repository: PostgresLedgerRepository) -> None:
        self._repository = repository

    def assert_bound_to(self, ledger: Ledger) -> None:
        raise ValueError(
            "PostgresCommandStore cannot be mixed with the SQLite Runtime Ledger"
        )

    def create_command(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._repository.create_command(**kwargs)
        except IntegrityError as exc:
            raise CommandStoreConflict("command idempotency conflict") from exc

    def get_command(
        self, *, namespace: str, command_id: str
    ) -> dict[str, Any] | None:
        return self._repository.get_command(namespace, command_id)

    def get_command_by_key(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._repository.get_command_by_key(**kwargs)

    def list_commands_by_key(
        self, *, namespace: str, idempotency_key: str
    ) -> list[dict[str, Any]]:
        return self._repository.list_commands_by_key(
            namespace=namespace,
            idempotency_key=idempotency_key,
        )

    def finish_command(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._repository.finish_command(**kwargs)
        except IntegrityError as exc:
            raise CommandStoreConflict("command transition conflict") from exc
