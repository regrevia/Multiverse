from __future__ import annotations

from pathlib import Path

from multiverse_workflow.api.dependencies import ServiceSettings
from multiverse_workflow.runtime.dispatch_lease import NoopDispatchGate


def test_service_settings_passes_dispatch_gate_to_worker_factory(tmp_path: Path) -> None:
    settings = ServiceSettings(
        database_path=tmp_path / "runtime.db",
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
        dispatch_gate=NoopDispatchGate(),
    )
    worker = settings.create_worker(worker_id="settings-worker", poll_interval=0)
    try:
        assert worker.dispatch_gate is settings.dispatch_gate
    finally:
        worker.close()
