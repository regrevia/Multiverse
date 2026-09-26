"""Persistent local runtime primitives."""

from typing import TYPE_CHECKING, Any

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict

if TYPE_CHECKING:
    from multiverse_workflow.runtime.worker import LocalWorker, WorkerLockError

__all__ = ["Ledger", "LedgerConflict", "LocalWorker", "WorkerLockError"]


def __getattr__(name: str) -> Any:
    # Worker imports the compiler through Runner; keep registry imports independent.
    if name in {"LocalWorker", "WorkerLockError"}:
        from multiverse_workflow.runtime import worker

        return getattr(worker, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
