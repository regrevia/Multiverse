from __future__ import annotations

import math
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.constructor import (
    DuplicateKeyError,
)
from ruamel.yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from multiverse_workflow.protocol.diagnostics import Diagnostic, DiagnosticError

_MAX_SAFE_INTEGER = 2**53 - 1
_ROOT_POINTER = ""


def load_document(path: Path) -> LoadedDocument:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiagnosticError(
            Diagnostic(
                code="FILE_READ_FAILED",
                file=str(path),
                pointer=_ROOT_POINTER,
                message=f"无法读取文件：{exc}",
            )
        ) from exc

    yaml = YAML(typ="safe")
    yaml.version = (1, 2)
    yaml.allow_duplicate_keys = False
    _validate_events(path, yaml, text)
    try:
        value = yaml.load(text)
    except DuplicateKeyError as exc:
        key = _extract_duplicate_key(exc)
        raise DiagnosticError(
            Diagnostic(
                code="DUPLICATE_KEY",
                file=str(path),
                pointer=key,
                message=f"对象包含重复键：{key.rsplit('/', 1)[-1]}。",
                suggestion="删除重复键，只保留一个定义。",
            )
        ) from exc
    except Exception as exc:
        raise DiagnosticError(
            Diagnostic(
                code="DOCUMENT_PARSE_FAILED",
                file=str(path),
                pointer=_ROOT_POINTER,
                message=f"文档解析失败：{exc}",
            )
        ) from exc

    _validate_json_value(path, value, _ROOT_POINTER)
    return LoadedDocument(path=path, value=value)


class LoadedDocument:
    def __init__(self, path: Path, value: Any) -> None:
        self.path = path
        self.value = value


def _validate_events(path: Path, yaml: YAML, text: str) -> None:
    try:
        events = list(yaml.parse(text))
        _scan_events(path, events, _ROOT_POINTER)
    except DiagnosticError:
        raise
    except Exception as exc:
        raise DiagnosticError(
            Diagnostic(
                code="DOCUMENT_PARSE_FAILED",
                file=str(path),
                pointer=_ROOT_POINTER,
                message=f"文档语法无效：{exc}",
            )
        ) from exc


def _scan_events(path: Path, events: list[Any], pointer: str) -> int:
    index = 0
    while index < len(events):
        event = events[index]
        _validate_event(path, event, pointer)
        if isinstance(event, MappingStartEvent):
            return _scan_mapping(path, events, index, pointer)
        if isinstance(event, SequenceStartEvent):
            return _scan_sequence(path, events, index, pointer)
        index += 1
    return index


def _scan_mapping(path: Path, events: list[Any], start: int, pointer: str) -> int:
    index = start + 1
    seen: set[str] = set()
    while index < len(events) and not isinstance(events[index], MappingEndEvent):
        key_event = events[index]
        _validate_event(path, key_event, pointer)
        if not isinstance(key_event, ScalarEvent):
            raise DiagnosticError(
                Diagnostic(
                    code="NON_JSON_TYPE",
                    file=str(path),
                    pointer=pointer,
                    message="对象键必须是字符串。",
                )
            )
        key = key_event.value
        key_pointer = f"{pointer}/{_escape_pointer(key)}"
        if key in seen:
            raise DiagnosticError(
                Diagnostic(
                    code="DUPLICATE_KEY",
                    file=str(path),
                    pointer=key_pointer,
                    message=f"对象包含重复键：{key}。",
                    suggestion="删除重复键，只保留一个定义。",
                )
            )
        seen.add(key)
        index = _skip_node(path, events, index, key_pointer)
        index = _scan_value(path, events, index, key_pointer)
    if index >= len(events):
        raise DiagnosticError(
            Diagnostic(
                code="DOCUMENT_PARSE_FAILED",
                file=str(path),
                pointer=pointer,
                message="对象没有正确结束。",
            )
        )
    return index + 1


def _scan_sequence(path: Path, events: list[Any], start: int, pointer: str) -> int:
    index = start + 1
    item_index = 0
    while index < len(events) and not isinstance(events[index], SequenceEndEvent):
        item_pointer = f"{pointer}/{item_index}"
        index = _scan_value(path, events, index, item_pointer)
        item_index += 1
    if index >= len(events):
        raise DiagnosticError(
            Diagnostic(
                code="DOCUMENT_PARSE_FAILED",
                file=str(path),
                pointer=pointer,
                message="数组没有正确结束。",
            )
        )
    return index + 1


def _scan_value(path: Path, events: list[Any], start: int, pointer: str) -> int:
    if start >= len(events):
        raise DiagnosticError(
            Diagnostic(
                code="DOCUMENT_PARSE_FAILED",
                file=str(path),
                pointer=pointer,
                message="对象缺少值。",
            )
        )
    event = events[start]
    _validate_event(path, event, pointer)
    if isinstance(event, MappingStartEvent):
        return _scan_mapping(path, events, start, pointer)
    if isinstance(event, SequenceStartEvent):
        return _scan_sequence(path, events, start, pointer)
    return start + 1


def _skip_node(path: Path, events: list[Any], start: int, pointer: str) -> int:
    return _scan_value(path, events, start, pointer)


def _validate_event(path: Path, event: Any, pointer: str) -> None:
    if isinstance(event, AliasEvent):
        raise DiagnosticError(
            Diagnostic(
                code="YAML_ALIAS_FORBIDDEN",
                file=str(path),
                pointer=pointer,
                message="禁止使用 YAML 别名/锚点。",
            )
        )
    if isinstance(event, MappingStartEvent) and event.anchor is not None:
        raise DiagnosticError(
            Diagnostic(
                code="YAML_ALIAS_FORBIDDEN",
                file=str(path),
                pointer=pointer,
                message="禁止使用 YAML 锚点。",
            )
        )
    if isinstance(event, ScalarEvent):
        if event.tag is not None and not event.implicit[0]:
            raise DiagnosticError(
                Diagnostic(
                    code="YAML_TAG_FORBIDDEN",
                    file=str(path),
                    pointer=pointer,
                    message="禁止使用自定义 YAML 标签。",
                )
            )
        if event.value == "<<":
            raise DiagnosticError(
                Diagnostic(
                    code="YAML_MERGE_FORBIDDEN",
                    file=str(path),
                    pointer=pointer,
                    message="禁止使用 YAML 合并键。",
                )
            )


def _validate_json_value(path: Path, value: Any, pointer: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise DiagnosticError(
                Diagnostic(
                    code="INTEGER_OUT_OF_RANGE",
                    file=str(path),
                    pointer=pointer,
                    message="整数超出 JSON 安全整数范围。",
                    suggestion="将高精度数值编码为带格式说明的字符串。",
                )
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DiagnosticError(
                Diagnostic(
                    code="NON_FINITE_NUMBER",
                    file=str(path),
                    pointer=pointer,
                    message="数字必须是有限 IEEE-754 数字。",
                )
            )
        return
    if isinstance(value, (datetime, date, time)):
        raise DiagnosticError(
            Diagnostic(
                code="NON_JSON_TYPE",
                file=str(path),
                pointer=pointer,
                message="协议文档只能包含 JSON 类型，禁止隐式日期/时间对象。",
            )
        )
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{_escape_pointer(str(key))}"
            _validate_json_value(path, child, child_pointer)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_value(path, child, f"{pointer}/{index}")
        return
    raise DiagnosticError(
        Diagnostic(
            code="NON_JSON_TYPE",
            file=str(path),
            pointer=pointer,
            message=f"协议文档包含不支持的类型：{type(value).__name__}。",
        )
    )


def _extract_duplicate_key(exc: DuplicateKeyError) -> str:
    key = getattr(exc, "key", None)
    if key is not None:
        return f"/{_escape_pointer(str(key))}"
    context = str(exc)
    quoted = context.split('found duplicate key "', 1)
    if len(quoted) == 2:
        name = quoted[1].split('"', 1)[0]
        return f"/{_escape_pointer(name)}"
    return _ROOT_POINTER


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
