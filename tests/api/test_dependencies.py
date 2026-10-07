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


def test_service_settings_passes_ledger_factory_to_application_and_worker(
    tmp_path: Path,
) -> None:
    calls: list[Path] = []

    def factory(path: Path):
        from multiverse_workflow.runtime.ledger import Ledger

        calls.append(path)
        return Ledger(path)

    settings = ServiceSettings(
        database_path=tmp_path / "runtime.db",
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
        ledger_factory=factory,
    )
    application = settings.create_application()
    worker = settings.create_worker(worker_id="factory-worker", poll_interval=0)
    try:
        assert len(calls) == 2
    finally:
        application.close()
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


def test_service_settings_readiness_reports_missing_runtime_storage(tmp_path: Path) -> None:
    settings = ServiceSettings(
        database_path=tmp_path / "not-created.db",
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
    )
    readiness = settings.readiness()
    assert readiness["status"] == "not_ready"
    assert readiness["checks"]["database"]["status"] == "not_ready"
    assert readiness["capabilities"]["serviceArtifactBytes"] is False


def test_service_settings_readiness_rejects_incomplete_runtime_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "partial.db"
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    (tmp_path / "artifacts").mkdir()
    settings = ServiceSettings(
        database_path=database,
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
    )
    assert settings.readiness()["checks"]["database"]["status"] == "not_ready"


def test_service_settings_readiness_rejects_placeholder_runtime_tables(
    tmp_path: Path,
) -> None:
    import sqlite3

    database = tmp_path / "placeholder.db"
    table_names = (
        "runs",
        "commands",
        "scopes",
        "invocations",
        "attempts",
        "human_requests",
        "human_decisions",
        "human_progress_intents",
        "waits",
        "outbox",
        "run_events",
        "artifacts",
        "codex_interactions",
        "external_artifact_sources",
    )
    with sqlite3.connect(database) as connection:
        for table in table_names:
            connection.execute(f'CREATE TABLE "{table}" (placeholder TEXT)')
    (tmp_path / "artifacts").mkdir()
    settings = ServiceSettings(
        database_path=database,
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
    )
    assert settings.readiness()["status"] == "not_ready"


def test_service_settings_readiness_probes_artifact_write_read_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "runtime.db"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    settings = ServiceSettings(
        database_path=database,
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
    )
    settings.create_application().close()

    def reject_artifact_probe(*args: object, **kwargs: object):
        raise OSError("simulated read-only artifact storage")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", reject_artifact_probe)
    readiness = settings.readiness()
    assert readiness["checks"]["artifactStorage"]["status"] == "not_ready"
    assert readiness["status"] == "not_ready"
