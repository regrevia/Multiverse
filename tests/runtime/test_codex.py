from __future__ import annotations

import sys
from pathlib import Path

import pytest

from multiverse_workflow.runtime.codex import (
    CodexAppServer,
    CodexInterruptedError,
    CodexProtocolError,
)


def _write_fake_codex(path: Path, messages: list[dict[str, object]]) -> None:
    path.write_text(
        "import json, sys\n"
        f"messages = {messages!r}\n"
        "while True:\n"
        "    line = sys.stdin.readline()\n"
        "    if not line:\n"
        "        break\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps(messages[0]), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps(messages[1]), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        "        print(json.dumps(messages[2]), flush=True)\n"
        "        print(json.dumps(messages[3]), flush=True)\n"
        "        print(json.dumps(messages[4]), flush=True)\n"
        "        print(json.dumps(messages[5]), flush=True)\n",
        encoding="utf-8",
    )


def test_codex_app_server_round_trips_structured_output(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex.py"
    _write_fake_codex(
        fake,
        [
            {"id": 1, "result": {"userAgent": "fake"}},
            {"id": 2, "result": {"thread": {"id": "thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {"method": "item/agentMessage/delta", "params": {"delta": '{"text":"ok",'}},
            {"method": "item/agentMessage/delta", "params": {"delta": '"artifact_refs":[]}' }},
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn-1", "status": "completed"}},
            },
        ],
    )

    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.output == {"text": "ok", "artifact_refs": []}
    assert result.observation["threadId"] == "thread-1"
    assert result.observation["turnId"] == "turn-1"


def test_codex_app_server_rejects_non_json_final_message(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex.py"
    _write_fake_codex(
        fake,
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {"method": "item/agentMessage/delta", "params": {"delta": "not json"}},
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
            {"method": "noop", "params": {}},
        ],
    )

    with pytest.raises(CodexProtocolError, match="not JSON"):
        CodexAppServer(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_codex_app_server_can_interrupt_a_turn(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex.py"
    fake.write_text(
        "import json, sys\n"
        "while True:\n"
        "    line = sys.stdin.readline()\n"
        "    if not line: break\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps({'id': 2, 'result': {}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    assert CodexAppServer.interrupt(
        command=(sys.executable, "-u", str(fake)),
        home_dir=tmp_path,
        thread_id="thread-1",
        turn_id="turn-1",
        timeout_seconds=2,
    )


def test_codex_timeout_requests_and_confirms_turn_interrupt(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_interrupt.py"
    fake.write_text(
        "import json, sys, time\n"
        "import threading\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps({'id': 2, 'result': {'thread': {'id': "
        "'thread-1'}}}), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        "        print(json.dumps({'id': 3, 'result': {'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "        threading.Thread(target=lambda: time.sleep(10), daemon=True).start()\n"
        "    elif request.get('id') == 4:\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexInterruptedError, match="interrupted"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=0.05,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_codex_server_request_is_returned_over_the_same_rpc_connection(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_request.py"
    fake.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        "        print(json.dumps({'id': 3, 'result': {'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "        print(json.dumps({'id': 'native-7', 'method': 'item/tool/requestUserInput', "
        "'params': {'threadId': 'thread-1', 'turnId': 'turn-1', 'questions': []}}), flush=True)\n"
        "    elif request_id == 'native-7':\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"continued\\\","
        "\\\"artifact_refs\\\":[]}'}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )
    seen: list[tuple[str, dict[str, object]]] = []
    sent: list[str] = []

    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="continue",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        on_server_request=lambda request_id, method, params: (
            seen.append((method, params)) or {"answers": {"choice": {"answers": ["yes"]}}}
        ),
        on_server_response=lambda request_id, response: sent.append(request_id),
    )

    assert seen == [
        (
            "item/tool/requestUserInput",
            {"threadId": "thread-1", "turnId": "turn-1", "questions": []},
        )
    ]
    assert result.output == {"text": "continued", "artifact_refs": []}
    assert sent == ["native-7"]
