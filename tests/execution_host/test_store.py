from __future__ import annotations

import json

from multiverse_workflow.execution_host.store import HostStore

from .conftest import execution_request


def test_persisted_events_are_bounded_and_terminal_observation_is_immutable(tmp_path):
    path = tmp_path / "host.db"
    store = HostStore(path)
    row, created = store.submit(execution_request())
    ref = row["id"]
    assert created
    for _ in range(40):
        store.update(ref, "running")
    events = store.events(ref)
    assert len(events) == 32
    assert [event["revision"] for event in events] == list(range(10, 42))
    assert store.events(ref, after=40) == [events[-1]]
    store.update(ref, "succeeded", final=True, output={"text": "done"})
    final = json.loads(store.get(ref)["observation_json"])
    store.update(ref, "failed", final=True, error={"code": "LATE_FAILURE"})
    store.cancel(ref, "late-cancel")
    assert json.loads(store.get(ref)["observation_json"]) == final
    store.close()
    reopened = HostStore(path)
    try:
        assert json.loads(reopened.get(ref)["observation_json"]) == final
        assert reopened.events(ref)[-1] == final
    finally:
        reopened.close()
