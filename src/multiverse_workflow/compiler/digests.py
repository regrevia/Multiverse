from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_digest(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def package_digest(package_root: Path) -> str:
    return sha256_digest(canonical_json(package_file_manifest(package_root)))


def package_file_manifest(package_root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or _excluded_package_path(path, package_root):
            continue
        content = path.read_bytes()
        relative = path.relative_to(package_root).as_posix()
        files.append(
            {
                "path": relative,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return files


def binding_digest(binding: Any) -> str:
    return sha256_digest(canonical_json(binding))


def _excluded_package_path(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(
        part in {".git", ".multiverse", "__pycache__"} for part in relative_parts
    ) or path.name in {".DS_Store", "package.lock.json"}
