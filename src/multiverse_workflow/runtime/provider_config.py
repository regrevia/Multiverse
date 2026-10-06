from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_CLAUDE_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_HOST_AUTH_ENV_VAR",
}


@dataclass(frozen=True)
class ClaudeProviderConfig:
    environment: dict[str, str]
    model: str | None
    metadata: dict[str, str]


def load_cc_switch_claude_config(
    *,
    database_path: Path | None = None,
    profile_id: str | None = None,
    model_alias: str = "claude-sonnet-5",
) -> ClaudeProviderConfig:
    database = database_path or Path.home() / ".cc-switch" / "cc-switch.db"
    try:
        connection = sqlite3.connect(database)
    except sqlite3.Error as exc:
        raise ValueError("cc-switch Claude provider database is unavailable") from exc
    connection.row_factory = sqlite3.Row
    try:
        if profile_id:
            row = connection.execute(
                """
                SELECT id, name, settings_config, meta
                FROM providers
                WHERE app_type = 'claude-desktop' AND id = ?
                """,
                (profile_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT id, name, settings_config, meta
                FROM providers
                WHERE app_type = 'claude-desktop' AND is_current = 1
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("cc-switch Claude provider database is unavailable") from exc
    finally:
        connection.close()
    if row is None:
        raise ValueError("cc-switch has no current Claude provider profile")
    try:
        settings = json.loads(row["settings_config"] or "{}")
        meta = json.loads(row["meta"] or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("cc-switch Claude provider profile is invalid") from exc
    raw_environment = settings.get("env", {})
    if not isinstance(raw_environment, dict):
        raise ValueError("cc-switch Claude provider env is invalid")
    environment = {
        key: value
        for key, value in raw_environment.items()
        if key in _CLAUDE_ENV_KEYS and isinstance(value, str) and value
    }
    routes = meta.get("claudeDesktopModelRoutes", {})
    route = routes.get(model_alias, {}) if isinstance(routes, dict) else {}
    model = route.get("model") if isinstance(route, dict) else None
    return ClaudeProviderConfig(
        environment=environment,
        model=model if isinstance(model, str) and model else None,
        metadata={
            "source": "cc-switch",
            "profileId": str(row["id"]),
            "profileName": str(row["name"]),
            "modelAlias": model_alias,
        },
    )
