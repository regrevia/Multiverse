from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.storage.database import (
    DatabaseTarget,
    DatabaseTargetError,
    parse_database_target,
)


def test_parse_sqlite_path_as_local_target(tmp_path: Path) -> None:
    target = parse_database_target(tmp_path / "runtime.db")

    assert target == DatabaseTarget(
        backend="sqlite",
        location=str((tmp_path / "runtime.db").resolve()),
        service_mode=False,
    )


def test_parse_postgresql_url_as_service_target() -> None:
    target = parse_database_target(
        "postgresql+psycopg://runtime:secret@db.example.test:5432/multiverse"
    )

    assert target.backend == "postgresql"
    assert target.location == "postgresql+psycopg://runtime:secret@db.example.test:5432/multiverse"
    assert target.service_mode is True


def test_safe_location_redacts_userinfo_and_query_secrets() -> None:
    target = parse_database_target(
        "postgresql+psycopg://runtime:secret@db.example.test:5432/multiverse"
        "?password=querysecret&sslmode=require"
    )

    assert "secret" not in target.safe_location
    assert "querysecret" not in target.safe_location
    assert "sslmode=require" in target.safe_location
    api_target = parse_database_target(
        "postgresql://runtime@db.example.test:5432/multiverse"
        "?api_key=querysecret&access_token=accesssecret&application_name=runtime"
    )
    assert "querysecret" not in api_target.safe_location
    assert "accesssecret" not in api_target.safe_location
    assert "application_name=runtime" in api_target.safe_location


def test_safe_location_preserves_ipv6_host_syntax() -> None:
    target = parse_database_target("postgresql://runtime:secret@[::1]:5432/multiverse")

    assert target.safe_location == "postgresql://runtime:***@[::1]:5432/multiverse"


def test_reject_malformed_ipv6_url() -> None:
    with pytest.raises(DatabaseTargetError):
        parse_database_target("postgresql://runtime:secret@[::1/multiverse")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "mysql://db.example.test/multiverse",
        "postgresql://",
        "sqlite://relative/path.db",
        "postgresql://runtime@db.example.test:bad/multiverse",
    ],
)
def test_reject_unsupported_or_ambiguous_database_target(value: str) -> None:
    with pytest.raises(DatabaseTargetError):
        parse_database_target(value)
