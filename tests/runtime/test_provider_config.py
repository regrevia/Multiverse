from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from multiverse_workflow.runtime.provider_config import load_cc_switch_claude_config


def test_load_cc_switch_claude_config_returns_runtime_env_without_persisting_secrets(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cc-switch.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE providers (id TEXT, app_type TEXT, name TEXT, "
        "settings_config TEXT, meta TEXT, is_current INTEGER)"
    )
    connection.execute(
        "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
        (
            "profile-1",
            "claude-desktop",
            "current",
            json.dumps(
                {
                    "env": {
                        "ANTHROPIC_BASE_URL": "https://example.test",
                        "ANTHROPIC_API_KEY": "secret-value",
                        "UNSAFE": "ignored",
                    }
                }
            ),
            json.dumps(
                {
                    "claudeDesktopModelRoutes": {
                        "claude-sonnet-5": {"model": "mapped-sonnet"}
                    }
                }
            ),
            1,
        ),
    )
    connection.commit()
    connection.close()

    loaded = load_cc_switch_claude_config(
        database_path=database,
        model_alias="claude-sonnet-5",
    )

    assert loaded.environment == {
        "ANTHROPIC_BASE_URL": "https://example.test",
        "ANTHROPIC_API_KEY": "secret-value",
    }
    assert loaded.model == "mapped-sonnet"
    assert "secret-value" not in repr(loaded.metadata)
    assert loaded.metadata == {
        "source": "cc-switch",
        "profileId": "profile-1",
        "profileName": "current",
        "modelAlias": "claude-sonnet-5",
    }


def test_load_cc_switch_claude_config_classifies_connection_failure(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="database is unavailable"):
        load_cc_switch_claude_config(database_path=tmp_path / "missing" / "cc-switch.db")
