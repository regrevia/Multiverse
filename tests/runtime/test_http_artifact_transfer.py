from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
from test_http_job_runtime import _registry, _remote_package, _RuntimeJobHandler

from multiverse_workflow.runtime.http_job import (
    HttpJobClient,
    HttpJobError,
    HttpJobTransportError,
)
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.runner import Runner

CONTENT = b"real artifact bytes\x00\xff"
EXECUTION = "remote-execution-1"


def metadata(**changes: Any) -> dict[str, Any]:
    return {
        "artifactId": "file-1",
        "version": 1,
        "executionRef": EXECUTION,
        "namespace": "local",
        "name": "result.bin",
        "mediaType": "application/octet-stream",
        "sizeBytes": len(CONTENT),
        "digest": "sha256:" + hashlib.sha256(CONTENT).hexdigest(),
        **changes,
    }


class ArtifactHandler(_RuntimeJobHandler):
    items: list[dict[str, Any]] = []
    content = CONTENT
    fetched: list[str] = []
    redirect_hits = 0
    redirect = False
    content_redirect = False
    drop_content = False
    envelope_changes: dict[str, Any] = {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/redirect-target":
            self.__class__.redirect_hits += 1
            self._json(200, {})
            return
        if "/artifacts" not in self.path:
            return super().do_GET()
        self.fetched.append(self.path)
        if self.drop_content and self.path.endswith("/content"):
            self.close_connection = True
            return
        if self.redirect or (self.content_redirect and self.path.endswith("/content")):
            self.send_response(302)
            self.send_header("Location", "/redirect-target")
            self.end_headers()
        elif self.path.endswith("/artifacts"):
            self._json(
                200,
                {
                    "executionRef": EXECUTION,
                    "namespace": "local",
                    "artifacts": self.items,
                    **self.envelope_changes,
                },
            )
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(self.content)


@pytest.fixture
def artifact_server() -> Iterator[str]:
    ArtifactHandler.items = [metadata()]
    ArtifactHandler.content = CONTENT
    ArtifactHandler.fetched = []
    ArtifactHandler.redirect_hits = 0
    ArtifactHandler.redirect = False
    ArtifactHandler.content_redirect = False
    ArtifactHandler.drop_content = False
    ArtifactHandler.envelope_changes = {}
    ArtifactHandler.observations = {}
    ArtifactHandler.submit_count = 0
    ArtifactHandler.requests = []
    ArtifactHandler.created_dispatch_keys = set()
    ArtifactHandler.drop_submit_response = False
    ArtifactHandler.create_execution = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArtifactHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def prepare(tmp_path: Path, url: str) -> tuple[Runner, dict[str, Any], dict[str, Any]]:
    package, binding = _remote_package(tmp_path, url)
    runner = Runner(
        package,
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )
    run = runner.start({"goal": "artifact transfer"})
    runner.sweep(worker_id="test")
    attempt = runner.ledger.list_attempts(run["id"])[0]
    ArtifactHandler.observations[EXECUTION] = {
        "executionRef": EXECUTION,
        "revision": 2,
        "status": "succeeded",
        "observedAt": "2026-09-26T00:00:00Z",
        "executionFinal": True,
        "effectState": "confirmed",
        "output": {"text": "deliverable", "artifact_refs": []},
        "artifacts": [metadata()],
    }
    return runner, run, attempt


def test_tcp_bytes_import_and_reopen_after_registration_before_attempt_finish(
    tmp_path: Path,
    artifact_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)

    def crash(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated process exit after registration")

    monkeypatch.setattr(runner.ledger, "finish_attempt", crash)
    with pytest.raises(RuntimeError, match="simulated process exit"):
        runner.sweep(worker_id="test")
    artifacts = runner.ledger.list_artifacts(run["id"])
    assert len(artifacts) == 1
    assert Path(artifacts[0]["storage_ref"]).read_bytes() == CONTENT
    saved = runner.ledger.get_attempt(attempt["id"])
    assert saved is not None and saved["status"] == "submitted"
    assert json.loads(saved["observation_json"])["output"]["artifact_refs"] == []
    runner.ledger.close()

    # A fresh SQLite connection and Runner replay the original immutable observation.
    reopened = Runner(
        tmp_path / "content-remote",
        binding_path=tmp_path / "content-remote.yaml",
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )
    reopened.sweep(worker_id="restarted")
    assert reopened.ledger.list_artifacts(run["id"]) == artifacts
    finished = reopened.ledger.get_attempt(attempt["id"])
    assert finished is not None and finished["status"] == "succeeded"
    assert json.loads(finished["output_json"])["artifact_refs"] == [artifacts[0]["id"]]
    assert json.loads(finished["observation_json"])["output"]["artifact_refs"] == []
    reopened.ledger.validate_artifact_refs(run["id"], [artifacts[0]["id"]])
    assert finished["external_ref"] == EXECUTION
    assert reopened.ledger.register_external_artifacts(
        attempt_id=attempt["id"],
        execution_ref=EXECUTION,
        artifacts=[(metadata(), CONTENT)],
    ) == [artifacts[0]["id"]]
    assert ArtifactHandler.submit_count == 1
    reopened.ledger.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", "other"),
        ("executionRef", "other"),
        ("version", True),
        ("version", 2),
        ("sizeBytes", True),
        ("sizeBytes", -1),
        ("sizeBytes", 1_048_577),
        ("artifactId", ".."),
        ("artifactId", "%2fetc"),
        ("artifactId", "x/y"),
        ("digest", "sha256:" + "g" * 64),
        ("name", ""),
        ("mediaType", "\n"),
        ("metadataURL", "http://example.invalid/secret"),
    ],
)
def test_metadata_rejected_before_content_fetch(
    artifact_server: str,
    field: str,
    value: Any,
) -> None:
    item = metadata(**{field: value})
    ArtifactHandler.items = [item]
    with pytest.raises(HttpJobError):
        HttpJobClient(artifact_server).download_artifacts(EXECUTION, "local", [item])
    assert ArtifactHandler.fetched == []


@pytest.mark.parametrize(
    "mode",
    [
        "digest",
        "size",
        "oversized",
        "namespace",
        "execution",
        "changed",
        "redirect",
        "content_redirect",
        "metadata_limit",
    ],
)
def test_tcp_corrupt_or_misdirected_transfer_is_rejected(artifact_server: str, mode: str) -> None:
    if mode == "digest":
        ArtifactHandler.content = b"x" * len(CONTENT)
    elif mode == "size":
        ArtifactHandler.content = b"short"
    elif mode == "oversized":
        ArtifactHandler.content = b"x" * 1_048_577
    elif mode in {"namespace", "execution"}:
        ArtifactHandler.envelope_changes = {
            "namespace" if mode == "namespace" else "executionRef": "wrong"
        }
    elif mode == "changed":
        ArtifactHandler.items = [metadata(name="changed")]
    elif mode == "content_redirect":
        ArtifactHandler.content_redirect = True
    elif mode == "metadata_limit":
        ArtifactHandler.envelope_changes = {"padding": "x" * 200_001}
    else:
        ArtifactHandler.redirect = True
    with pytest.raises(HttpJobError):
        HttpJobClient(artifact_server).download_artifacts(EXECUTION, "local", [metadata()])
    assert ArtifactHandler.redirect_hits == 0


@pytest.mark.parametrize(
    "items",
    [
        [metadata()] * 9,
        [metadata(artifactId=f"item-{i}", sizeBytes=1_048_576) for i in range(5)],
        [metadata(), metadata()],
    ],
)
def test_batch_limits_reject_before_fetch(
    artifact_server: str, items: list[dict[str, Any]]
) -> None:
    with pytest.raises(HttpJobError):
        HttpJobClient(artifact_server).download_artifacts(EXECUTION, "local", items)
    assert ArtifactHandler.fetched == []


@pytest.mark.parametrize("absent", [True, False])
def test_old_executor_without_artifacts_needs_no_new_endpoint(
    tmp_path: Path,
    artifact_server: str,
    absent: bool,
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    if absent:
        del ArtifactHandler.observations[EXECUTION]["artifacts"]
    else:
        ArtifactHandler.observations[EXECUTION]["artifacts"] = []
    runner.sweep(worker_id="test")
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "succeeded"
    assert runner.ledger.list_artifacts(run["id"]) == []
    assert ArtifactHandler.fetched == []
    runner.ledger.close()


def test_bad_batch_never_registers_first_valid_item(tmp_path: Path, artifact_server: str) -> None:
    runner, run, _ = prepare(tmp_path, artifact_server)
    items = [metadata(), metadata(artifactId="file-2", digest="sha256:" + "0" * 64)]
    ArtifactHandler.items = items
    ArtifactHandler.observations[EXECUTION]["artifacts"] = items
    runner.sweep(worker_id="test")
    assert runner.ledger.get_run(run["id"])["status"] == "blocked"
    assert runner.ledger.list_artifacts(run["id"]) == []
    runner.ledger.close()


def test_source_conflict_and_wrong_attempt_cannot_import(
    tmp_path: Path, artifact_server: str
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    observation = ArtifactHandler.observations[EXECUTION]
    runner.ledger.record_external_observation(attempt["id"], observation=observation)
    refs = runner.ledger.register_external_artifacts(
        attempt_id=attempt["id"], execution_ref=EXECUTION, artifacts=[(metadata(), CONTENT)]
    )
    runner.ledger.close()
    ledger = Ledger(tmp_path / "runtime.db")
    assert (
        ledger.register_external_artifacts(
            attempt_id=attempt["id"], execution_ref=EXECUTION, artifacts=[(metadata(), CONTENT)]
        )
        == refs
    )
    changed = metadata(name="conflicting-name")
    ledger.record_external_observation(
        attempt["id"], observation={**observation, "revision": 3, "artifacts": [changed]}
    )
    with pytest.raises(LedgerConflict, match="metadata conflict"):
        ledger.register_external_artifacts(
            attempt_id=attempt["id"], execution_ref=EXECUTION, artifacts=[(changed, CONTENT)]
        )
    with pytest.raises(LedgerConflict, match="does not match"):
        ledger.register_external_artifacts(
            attempt_id=attempt["id"], execution_ref="different", artifacts=[(metadata(), CONTENT)]
        )
    assert len(ledger.list_artifacts(run["id"])) == 1
    ledger.close()


def test_business_refs_cannot_replace_import(tmp_path: Path, artifact_server: str) -> None:
    runner, run, _ = prepare(tmp_path, artifact_server)
    ArtifactHandler.observations[EXECUTION]["output"]["artifact_refs"] = ["host-path"]
    runner.sweep(worker_id="test")
    assert runner.ledger.get_run(run["id"])["status"] == "blocked"
    assert runner.ledger.list_artifacts(run["id"]) == []
    runner.ledger.close()


def test_ledger_batch_transaction_rolls_back_ready_rows_and_sources(
    tmp_path: Path,
    artifact_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    items = [metadata(), metadata(artifactId="file-2")]
    runner.ledger.record_external_observation(
        attempt["id"],
        observation={**ArtifactHandler.observations[EXECUTION], "artifacts": items},
    )
    original_event = runner.ledger._event
    count = 0

    def crash_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("process interrupted during batch")
        return original_event(*args, **kwargs)

    monkeypatch.setattr(runner.ledger, "_event", crash_second)
    with pytest.raises(RuntimeError, match="during batch"):
        runner.ledger.register_external_artifacts(
            attempt_id=attempt["id"],
            execution_ref=EXECUTION,
            artifacts=[(item, CONTENT) for item in items],
        )
    runner.ledger.close()
    reopened = Ledger(tmp_path / "runtime.db")
    assert reopened.list_artifacts(run["id"]) == []
    refs = reopened.register_external_artifacts(
        attempt_id=attempt["id"],
        execution_ref=EXECUTION,
        artifacts=[(item, CONTENT) for item in items],
    )
    assert len(refs) == len(set(refs)) == 2
    assert len(reopened.list_artifacts(run["id"])) == 2
    assert (
        reopened.register_external_artifacts(
            attempt_id=attempt["id"],
            execution_ref=EXECUTION,
            artifacts=[(item, CONTENT) for item in items],
        )
        == refs
    )
    reopened.close()


def test_downloaded_artifact_cannot_be_referenced_by_another_run(
    tmp_path: Path,
    artifact_server: str,
) -> None:
    runner, run, _ = prepare(tmp_path, artifact_server)
    runner.sweep(worker_id="test")
    artifacts = runner.ledger.list_artifacts(run["id"])
    other = runner.start({"goal": "unrelated run"})
    with pytest.raises(LedgerConflict, match="not authorized"):
        runner.ledger.validate_artifact_refs(other["id"], [artifacts[0]["id"]])
    runner.ledger.close()


def test_artifact_import_after_cancel_does_not_dispatch_downstream(
    tmp_path: Path,
    artifact_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    original_download = HttpJobClient.download_artifacts

    def cancel_during_download(*args: Any, **kwargs: Any) -> Any:
        downloaded = original_download(*args, **kwargs)
        current = runner.ledger.get_run(run["id"])
        runner.cancel(run["id"], expected_version=current["version"], reason="cancel race")
        return downloaded

    monkeypatch.setattr(HttpJobClient, "download_artifacts", cancel_during_download)
    runner.sweep(worker_id="test")
    assert ArtifactHandler.submit_count == 1
    assert len(runner.ledger.list_attempts(run["id"])) == 1
    assert len(runner.ledger.list_invocations(run["id"])) == 1
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "succeeded"
    assert runner.ledger.get_run(run["id"])["control_mode"] == "cancel"
    assert runner.ledger.get_run(run["id"])["status"] == "cancelled"
    wait = runner.ledger.get_wait_by_key("local", f"external-observe:{attempt['id']}")
    assert wait["status"] == "cancelled"
    runner.ledger.close()


@pytest.mark.parametrize("failure", ["digest", "namespace", "schema"])
def test_bad_artifact_result_persistently_blocks_without_blind_retry(
    tmp_path: Path,
    artifact_server: str,
    failure: str,
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    if failure == "digest":
        ArtifactHandler.content = b"x" * len(CONTENT)
    elif failure == "namespace":
        ArtifactHandler.envelope_changes = {"namespace": "untrusted"}
    else:
        ArtifactHandler.observations[EXECUTION]["output"]["text"] = 123
    runner.sweep(worker_id="test")
    failed = runner.ledger.get_run(run["id"])
    assert failed["status"] == "blocked"
    assert json.loads(failed["error_json"])["code"] == "EXECUTOR_PROTOCOL_VIOLATION"
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "submitted"
    assert len(runner.ledger.list_invocations(run["id"])) == 1
    fetched = list(ArtifactHandler.fetched)
    runner.ledger.close()
    reopened = Runner(
        tmp_path / "content-remote",
        binding_path=tmp_path / "content-remote.yaml",
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )
    reopened.sweep(worker_id="test")
    assert ArtifactHandler.fetched == fetched
    assert reopened.ledger.get_run(run["id"])["status"] == "blocked"
    assert ArtifactHandler.submit_count == 1
    reopened.ledger.close()


def test_transport_failure_preserves_wait_for_recovery(
    tmp_path: Path, artifact_server: str
) -> None:
    runner, run, attempt = prepare(tmp_path, artifact_server)
    ArtifactHandler.drop_content = True
    with pytest.raises(HttpJobTransportError):
        runner.sweep(worker_id="test")
    assert runner.ledger.get_run(run["id"])["status"] != "blocked"
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "submitted"
    assert runner.ledger.list_artifacts(run["id"]) == []
    ArtifactHandler.drop_content = False
    runner.sweep(worker_id="test")
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "succeeded"
    assert ArtifactHandler.submit_count == 1
    runner.ledger.close()


def test_submit_redirect_stays_unknown_and_is_never_followed(
    artifact_server: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def redirect_submit(handler: ArtifactHandler) -> None:
        ArtifactHandler.submit_count += 1
        handler.send_response(302)
        handler.send_header("Location", "/redirect-target")
        handler.end_headers()

    monkeypatch.setattr(ArtifactHandler, "do_POST", redirect_submit)
    with pytest.raises(HttpJobTransportError, match="submit result is unknown"):
        HttpJobClient(artifact_server).submit({})
    assert ArtifactHandler.submit_count == 1
    assert ArtifactHandler.redirect_hits == 0
