from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.api.dependencies import ServiceSettings
from multiverse_workflow.runtime.dispatch_lease import NoopDispatchGate
from multiverse_workflow.storage.database import DatabaseTargetError


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


def test_service_settings_reports_sqlite_personal_target(tmp_path: Path) -> None:
    settings = ServiceSettings(
        database_path=tmp_path / "runtime.db",
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
    )
    assert settings.profile == "personal"
    assert settings.database_target.backend == "sqlite"
    assert settings.database_target.service_mode is False


def test_service_settings_preserves_existing_positional_argument_order(
    tmp_path: Path,
) -> None:
    settings = ServiceSettings(
        tmp_path / "runtime.db",
        Path("presets/content-delivery"),
        Path("examples/bindings/content-local.yaml"),
        "deployment-positional",
        "namespace-positional",
        "token-positional",
        "subject-positional",
    )
    assert settings.deployment_id == "deployment-positional"
    assert settings.namespace == "namespace-positional"
    assert settings.bearer_token == "token-positional"
    assert settings.subject == "subject-positional"


def test_service_settings_rejects_team_until_postgres_runtime_is_wired(tmp_path: Path) -> None:
    with pytest.raises(DatabaseTargetError, match="PostgreSQL Runtime backend"):
        ServiceSettings(
            database_path=tmp_path / "runtime.db",
            package_dir=Path("presets/content-delivery"),
            binding_path=Path("examples/bindings/content-local.yaml"),
            profile="team",
        )


@pytest.mark.parametrize("profile", ["enterprise", "tem"])
def test_service_settings_rejects_unknown_profiles(
    tmp_path: Path, profile: str
) -> None:
    with pytest.raises(DatabaseTargetError, match="profile must be"):
        ServiceSettings(
            database_path=tmp_path / "runtime.db",
            package_dir=Path("presets/content-delivery"),
            binding_path=Path("examples/bindings/content-local.yaml"),
            profile=profile,  # type: ignore[arg-type]
        )


def test_service_settings_rejects_offline_until_resource_closure_is_verified(
    tmp_path: Path,
) -> None:
    with pytest.raises(DatabaseTargetError, match="offline resource closure"):
        ServiceSettings(
            database_path=tmp_path / "runtime.db",
            package_dir=Path("presets/content-delivery"),
            binding_path=Path("examples/bindings/content-local.yaml"),
            profile="offline",
        )
