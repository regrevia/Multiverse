from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _snapshot_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "kind": "blob",
            "size": len(value),
            "digest": "sha256:" + hashlib.sha256(value).hexdigest(),
        }
    return value


def export_sqlite_snapshot(database_path: Path) -> dict[str, Any]:
    """Return a value-free manifest for a stopped SQLite Ledger.

    The manifest is an integrity summary for a later import/reconciliation
    operation. It deliberately excludes row values, Artifact bytes, and paths.
    """
    path = database_path.expanduser().resolve()
    if not path.is_file():
        raise ValueError("SQLite snapshot database does not exist")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ValueError("SQLite snapshot database is unreadable") from exc
    connection.row_factory = sqlite3.Row
    try:
        try:
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                ).fetchall()
            ]
        except sqlite3.Error as exc:
            raise ValueError("SQLite snapshot database is unreadable") from exc
        table_manifests: dict[str, dict[str, Any]] = {}
        schema_entries: list[dict[str, Any]] = []
        for table in tables:
            try:
                quoted_table = _quote_identifier(table)
                table_sql_row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                columns = [
                    {
                        "name": str(row["name"]),
                        "type": str(row["type"]),
                        "notNull": bool(row["notnull"]),
                        "primaryKey": int(row["pk"]),
                        "default": row["dflt_value"],
                        "hidden": int(row["hidden"]),
                    }
                    for row in connection.execute(
                        f"PRAGMA table_xinfo({quoted_table})"
                    ).fetchall()
                ]
                primary_key: list[str] = [
                    str(column["name"]) for column in columns if column["primaryKey"]
                ]
                order_columns: list[str] = primary_key or [
                    str(column["name"]) for column in columns
                ]
                order_sql = ", ".join(
                    _quote_identifier(column) for column in order_columns
                )
                index_rows = connection.execute(
                    f"PRAGMA index_list({quoted_table})"
                ).fetchall()
                indexes = []
                for index_row in sorted(index_rows, key=lambda row: str(row["name"])):
                    index_name = str(index_row["name"])
                    index_columns = [
                        {
                            "seq": int(column["seqno"]),
                            "cid": int(column["cid"]),
                            "name": column["name"],
                            "desc": int(column["desc"]),
                            "coll": column["coll"],
                            "key": int(column["key"]),
                        }
                        for column in sorted(
                            connection.execute(
                                f"PRAGMA index_xinfo({_quote_identifier(index_name)})"
                            ).fetchall(),
                            key=lambda row: int(row["seqno"]),
                        )
                    ]
                    predicate = connection.execute(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'index' AND name = ?",
                        (index_name,),
                    ).fetchone()
                    indexes.append(
                        {
                            "name": index_name,
                            "unique": bool(index_row["unique"]),
                            "origin": str(index_row["origin"]),
                            "partial": bool(index_row["partial"]),
                            "predicateSql": predicate[0] if predicate else None,
                            "columns": index_columns,
                        }
                    )
                foreign_keys = [
                    dict(row)
                    for row in sorted(
                        connection.execute(
                            f"PRAGMA foreign_key_list({quoted_table})"
                        ).fetchall(),
                        key=lambda row: (
                            int(row["id"]),
                            int(row["seq"]),
                            str(row["table"]),
                            str(row["from"]),
                            str(row["to"]),
                        ),
                    )
                ]
                triggers = [
                    {"name": str(row["name"]), "sql": row["sql"]}
                    for row in connection.execute(
                        "SELECT name, sql FROM sqlite_master "
                        "WHERE type = 'trigger' AND tbl_name = ? ORDER BY name",
                        (table,),
                    ).fetchall()
                ]
            except sqlite3.Error as exc:
                raise ValueError("SQLite snapshot schema is unreadable") from exc
            schema_entries.append(
                {
                    "name": table,
                    "sql": table_sql_row[0] if table_sql_row else None,
                    "columns": columns,
                    "indexes": indexes,
                    "foreignKeys": foreign_keys,
                    "triggers": triggers,
                }
            )
            row_hasher = hashlib.sha256()
            row_count = 0
            try:
                for row in connection.execute(
                    f"SELECT * FROM {quoted_table} ORDER BY {order_sql}"
                ):
                    row_payload = {
                        key: _snapshot_value(row[key]) for key in row.keys()
                    }
                    row_hasher.update(
                        json.dumps(
                            row_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    row_hasher.update(b"\n")
                    row_count += 1
            except sqlite3.Error as exc:
                raise ValueError("SQLite snapshot rows are unreadable") from exc
            table_manifests[table] = {
                "rowCount": row_count,
                "contentDigest": "sha256:" + row_hasher.hexdigest(),
            }
        schema_digest = _digest(schema_entries)
        return {
            "schemaVersion": "multiverse.sqlite-snapshot/v0.2",
            "schemaDigestKind": "sqlite-structure/v0.2",
            "schemaDigest": schema_digest,
            "tables": table_manifests,
            "snapshotDigest": _digest(
                {"schemaDigest": schema_digest, "tables": table_manifests}
            ),
        }
    finally:
        connection.close()
