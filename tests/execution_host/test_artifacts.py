from __future__ import annotations

import json
from pathlib import Path

import pytest

from multiverse_workflow.compiler.preflight import preflight_package
from multiverse_workflow.runtime.registry import (
    ExecutorDescriptor,
    ExecutorRegistry,
    local_executor_registry,
)
from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.errors import ServiceError

from .conftest import execution_request, wait_final

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "setup,declarations",
    [
        ("", [{"path": "../outside", "name": "bad", "mediaType": "text/plain"}]),
        (
            "Path('bad').symlink_to('/etc/hosts')",
            [{"path": "bad", "name": "bad", "mediaType": "text/plain"}],
        ),
        ("Path('bad').mkdir()", [{"path": "bad", "name": "bad", "mediaType": "text/plain"}]),
        (
            "Path('bad').write_bytes(b'x'*1048577)",
            [{"path": "bad", "name": "bad", "mediaType": "text/plain"}],
        ),
        (
            "Path('bad').write_bytes(b'x')",
            [{"path": "bad", "name": "bad", "mediaType": "text/plain"}] * 9,
        ),
        (
            "Path('bad').write_bytes(b'x'*1048576)",
            [{"path": "bad", "name": "bad", "mediaType": "text/plain"}] * 5,
        ),
    ],
)
def test_host_rejects_unsafe_or_excessive_artifacts(host_factory, setup, declarations):
    script = (
        "import json\nfrom pathlib import Path\n"
        + setup
        + "\nprint(json.dumps({'output':{},'artifacts':"
        + repr(declarations)
        + "}))"
    )
    _, client = host_factory(script)
    ref = client.submit(execution_request())["executionRef"]
    final = wait_final(client, ref)
    assert final["status"] == "failed"
    assert client.fetch_artifacts(ref)["artifacts"] == []


def test_real_program_file_imported_by_runtime_and_read_through_artifact_acl(
    host_factory,
    tmp_path,
):
    script = """import json
from pathlib import Path
Path('deliverable.txt').write_text('real subprocess artifact')
print(json.dumps({'output':{'text':'Real deliverable','artifact_refs':[]},'artifacts':[
{'path':'deliverable.txt','name':'deliverable.txt','mediaType':'text/plain'}]}))
"""
    host, client = host_factory(script, executor_ref="example.remote-content.v1")
    delivered_binding = ROOT / "examples/bindings/content-execution-host.yaml"
    text = delivered_binding.read_text().replace("http://127.0.0.1:8790", client.base_url)
    binding = tmp_path / "binding.yaml"
    binding.write_text(text)
    registry = ExecutorRegistry(
        [
            *[
                item
                for item in local_executor_registry().descriptors()
                if item.executor_ref != "example.remote-content.v1"
            ],
            ExecutorDescriptor(
                executor_ref="example.remote-content.v1",
                adapter="http_job",
                capabilities=frozenset({"content.produce@1", "content.review@1"}),
                contract_version="multiverse/v0.1",
                executor_version="1.0.0",
                supports_cancel=True,
                supports_idempotency=True,
                supports_recovery_query=True,
                observability_level="boundary",
                permission_level="trusted_local",
                installed=True,
                available=True,
                verified=True,
            ),
        ]
    )
    report = preflight_package(
        ROOT / "presets/content-delivery",
        binding_path=delivered_binding,
        executor_registry=registry,
    )
    assert report.ok, report.as_dict()
    application = RuntimeApplication(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )
    runner = application.runner
    try:
        started = runner.start({"goal": "produce a real file"})
        attempt = runner.ledger.list_attempts(started["id"])[0]
        runner.sweep(worker_id="host-integration")
        external = runner.ledger.get_attempt(attempt["id"])["external_ref"]
        assert json.loads(host.store.get(external)["request_json"])["authorizationRef"] == (
            "local-grant"
        )
        observation = wait_final(client, external)
        assert observation["status"] == "succeeded"
        runner.sweep(worker_id="host-integration")
        completed = runner.ledger.get_attempt(attempt["id"])
        assert completed["status"] == "succeeded"
        output = json.loads(completed["output_json"])
        assert len(output["artifact_refs"]) == 1
        artifact_id = output["artifact_refs"][0]
        assert application.get_artifact_content("local", artifact_id) == b"real subprocess artifact"
        with pytest.raises(ServiceError):
            application.get_artifact_content("other-namespace", artifact_id)
        saved = runner.ledger.get_artifact(artifact_id)
        assert saved["invocation_id"] == attempt["invocation_id"]
        assert not Path(saved["storage_ref"]).is_relative_to(host.backend.root)
        # Replaying the exact same source import reuses its registered Runtime reference.
        imported = client.download_artifacts(external, "local", observation["artifacts"])
        assert runner.ledger.register_external_artifacts(
            attempt_id=attempt["id"], execution_ref=external, artifacts=imported
        ) == [artifact_id]
        assert len(runner.ledger.list_artifacts(started["id"])) == 1
        assert json.loads(completed["observation_json"])["output"]["artifact_refs"] == []
        # Host observations/events remain immutable despite Runtime ref substitution.
        assert client.observe(external) == observation
        assert host.backend.events(external)[-1] == observation
    finally:
        runner.ledger.close()
