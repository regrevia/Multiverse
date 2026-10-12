from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from multiverse_workflow.runtime.codex import (
    CodexAppServer,
    CodexInterruptedError,
    CodexOutputLimitError,
    CodexProtocolError,
    CodexRunCancelled,
    CodexTurnFailed,
    sanitize_codex_diagnostics,
)


def _runtime_event(method: str, item: dict[str, object]) -> dict[str, object]:
    return {"method": method, "params": {"item": item}}


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
        + "    elif request.get('id') == 3:\n"
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


def test_codex_app_server_forwards_every_runtime_event_in_order(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_many_events.py"
    runtime_events = [
        _runtime_event(
            "item/commandExecution/started",
            {
                "id": f"item-{index}",
                "type": "commandExecution",
                "command": (
                    "--api-key=must-not-persist"
                    if index == 0
                    else f"pytest {index}"
                ),
            },
        )
        for index in range(30)
    ]
    runtime_events[0] = _runtime_event(
        "item/fileChange/started",
        {
            "id": "file-1",
            "type": "fileChange",
            "path": "--api-key=must-not-persist",
        },
    )
    runtime_events[-1] = _runtime_event(
        "item/commandExecution/completed",
        {"id": "item-29", "type": "commandExecution"},
    )
    fake.write_text(
        "import json, sys\n"
        f"runtime_events = {runtime_events!r}\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-events'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-events'}}}), flush=True)\n"
        "        for event in runtime_events:\n"
        "            print(json.dumps(event), flush=True)\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"ok\\\",\\\"artifact_refs\\\":[]}'} }), "
        "flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )
    received: list[dict[str, object]] = []

    CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="emit events",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        on_event=received.append,
    )

    assert [event["method"] for event in received] == [
        *(event["method"] for event in runtime_events),
        "item/agentMessage/delta",
        "turn/completed",
    ]
    assert "must-not-persist" not in json.dumps(received)


def test_codex_app_server_drops_runtime_events_after_configured_observation_budget(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_event_budget.py"
    events = [
        _runtime_event(
            "item/commandExecution/started",
            {"id": f"item-{index}", "type": "commandExecution"},
        )
        for index in range(2050)
    ]
    fake.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-budget'}}}), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-budget'}}}), flush=True)\n"
        f"        for event in {events!r}:\n"
        "            print(json.dumps(event), flush=True)\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"ok\\\",\\\"artifact_refs\\\":[]}'} }), "
        "flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )
    received: list[dict[str, object]] = []
    CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=5,
    ).run(
        prompt="emit events",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        on_event=received.append,
    )

    assert len(received) == 2001
    assert received[-1]["method"] == "runtime/events_truncated"


def test_codex_app_server_truncates_oversized_runtime_event(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_oversized_event.py"
    _write_fake_codex(
        fake,
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread-large"}}},
            {"id": 3, "result": {"turn": {"id": "turn-large"}}},
            {
                "method": "item/fileChange/started",
                "params": {
                    "item": {
                        "id": "file-1",
                        "type": "fileChange",
                        **{f"change-{index}": "x" * 1500 for index in range(20)},
                    }
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {"delta": '{"text":"ok","artifact_refs":[]}'}},
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ],
    )
    received: list[dict[str, object]] = []
    CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=3,
    ).run(
        prompt="emit event",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        on_event=received.append,
    )

    assert received[0] == {
        "method": "item/fileChange/started",
        "params": {"truncated": True, "payloadBytes": received[0]["params"]["payloadBytes"]},
        "receivedAt": received[0]["receivedAt"],
    }
    assert received[0]["params"]["payloadBytes"] > 16384


def test_codex_failed_turn_preserves_error_events_and_stderr(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_failed_turn.py"
    fake.write_text(
        "import json, sys, time\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-failed'}}}), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-failed'}}}), flush=True)\n"
        "        print(json.dumps({'method': 'item/commandExecution/started', "
        "'params': {'item': {'id': 'item-1', 'type': 'commandExecution', "
        "'command': 'pytest -q'}}}), flush=True)\n"
        "        print('provider stderr detail', file=sys.stderr, flush=True)\n"
        "        time.sleep(0.02)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'id': 'turn-failed', 'status': 'failed', "
        "'error': {'codexErrorInfo': 'other', "
        "'message': 'workspace denied token=do-not-store'}}}}), "
        "flush=True)\n"
        ,
        encoding="utf-8",
    )
    events: list[dict[str, object]] = []

    with pytest.raises(CodexTurnFailed, match="workspace denied") as raised:
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="perform a workspace task",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            on_event=events.append,
        )

    assert raised.value.diagnostics["turnError"] == {
        "codexErrorInfo": "other",
        "message": "workspace denied token=[REDACTED]",
    }
    assert "do-not-store" not in str(raised.value)
    assert "do-not-store" not in json.dumps(raised.value.diagnostics)
    assert raised.value.diagnostics["threadId"] == "thread-failed"
    assert raised.value.diagnostics["turnId"] == "turn-failed"
    assert "provider stderr detail" in raised.value.diagnostics["stderr"]
    assert any(event.get("method") == "item/commandExecution/started" for event in events)


def test_codex_diagnostics_redact_secrets_and_bound_payloads() -> None:
    diagnostics = sanitize_codex_diagnostics(
        {
            "apiKey": "top-secret",
            "stderr": (
                "Authorization: Bearer abcdefghijklmnop "
                "request --api-key=another-secret "
                "https://example.test/?access_token=query-secret "
                "token=plain-secret api_key:colon-secret"
            ),
            "events": [{"method": "event"} for _ in range(30)],
            "large": "x" * 2000,
        }
    )

    assert diagnostics["apiKey"] == "[REDACTED]"
    assert "abcdefghijklmnop" not in diagnostics["stderr"]
    assert "another-secret" not in diagnostics["stderr"]
    assert "query-secret" not in diagnostics["stderr"]
    assert "plain-secret" not in diagnostics["stderr"]
    assert "colon-secret" not in diagnostics["stderr"]
    assert len(diagnostics["events"]) == 20
    assert len(diagnostics["large"]) == 1500


def test_codex_stderr_tail_buffer_is_bounded() -> None:
    from multiverse_workflow.runtime.codex import _BoundedTail

    tail = _BoundedTail(max_bytes=8)
    tail.write(b"first-line\n")
    tail.write(b"last-line\n")

    assert tail.getvalue() == b"st-line\n"
    assert tail.truncated


def test_codex_app_server_drains_large_stderr_without_growing_capture(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_stderr_flood.py"
    fake.write_text(
        "import json, sys\n"
        "sys.stderr.write('x' * (2 * 1024 * 1024) + 'final-marker')\n"
        "sys.stderr.flush()\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-stderr'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-stderr'}}}), flush=True)\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"ok\\\",\\\"artifact_refs\\\":[]}'} }), "
        "flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': "
        "{'turn': {'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )

    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=3,
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.output == {"text": "ok", "artifact_refs": []}


@pytest.mark.parametrize(
    ("session_mode", "expected_method", "native_session_id"),
    [
        ("new", "thread/start", None),
        ("resume", "thread/resume", "thread-previous"),
        ("fork", "thread/fork", "thread-previous"),
    ],
)
def test_codex_app_server_uses_explicit_session_mode(
    tmp_path: Path,
    session_mode: str,
    expected_method: str,
    native_session_id: str | None,
) -> None:
    fake = tmp_path / f"fake_codex_{session_mode}.py"
    thread_assertion = (
        "        assert request['params']['threadId'] == 'thread-previous'\n"
        if native_session_id
        else "        assert 'threadId' not in request['params']\n"
    )
    fake.write_text(
        "".join(
            [
                "import json, sys\n",
                "for line in sys.stdin:\n",
                "    request = json.loads(line)\n",
                "    if request.get('id') == 1:\n",
                "        print(json.dumps({'id':1,'result':{}}), flush=True)\n",
                "    elif request.get('id') == 2:\n",
                f"        assert request['method'] == {expected_method!r}, request\n",
                thread_assertion,
                "        print(json.dumps({'id':2,'result':"
                "{'thread':{'id':'thread-next'}}}), flush=True)\n",
                "    elif request.get('id') == 3:\n",
                "        print(json.dumps({'id':3,'result':"
                "{'turn':{'id':'turn-1'}}}), flush=True)\n",
                "        print(json.dumps({'method':'item/agentMessage/delta',"
                "'params':{'delta':'{\"text\":\"ok\",\"artifact_refs\":[]}'}}),"
                " flush=True)\n",
                "        print(json.dumps({'method':'turn/completed',"
                "'params':{'turn':{'status':'completed'}}}), flush=True)\n",
            ]
        ),
        encoding="utf-8",
    )
    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
        session_mode=session_mode,
        native_session_id=native_session_id,
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.observation["sessionMode"] == session_mode


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


def test_codex_app_server_surfaces_handshake_failure(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_handshake_error.py"
    _write_fake_codex(
        fake,
        [
            {"id": 1, "error": {"code": -32000, "message": "handshake denied"}},
        ],
    )

    with pytest.raises(CodexProtocolError, match="request failed"):
        CodexAppServer(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_codex_app_server_treats_response_pipe_loss_as_protocol_unknown(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_response_loss.py"
    fake.write_text(
        "import json, os, sys, time\n"
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
        "        print(json.dumps({'id': 'native-1', 'method': 'item/tool/requestUserInput', "
        "'params': {'threadId': 'thread-1', 'turnId': 'turn-1', 'questions': []}}), flush=True)\n"
        "        os.close(0)\n"
        "        time.sleep(5)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexProtocolError, match="response channel"):
        CodexAppServer(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            on_server_request=lambda request_id, kind, params: {
                "answers": {"question": {"answers": ["yes"]}}
            },
        )


def test_codex_interrupted_terminal_turn_is_not_reported_as_unknown(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_interrupted.py"
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
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexInterruptedError, match="interrupted"):
        CodexAppServer(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_codex_rejected_native_action_is_confirmed_interruption(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_rejected.py"
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
        "        print(json.dumps({'id': 'native-1', "
        "'method': 'item/commandExecution/requestApproval', 'params': "
        "{'threadId': 'thread-1', 'turnId': 'turn-1'}}), flush=True)\n"
        "    elif request_id == 'native-1':\n"
        "        assert json.loads(line)['result']['decision'] == 'cancel'\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexInterruptedError, match="interrupted"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="run a command",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            on_server_request=lambda *_: {"decision": "cancel"},
        )


def test_codex_declined_native_action_can_complete_without_approval(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_declined.py"
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
        "        print(json.dumps({'id': 'native-1', "
        "'method': 'item/commandExecution/requestApproval', 'params': "
        "{'threadId': 'thread-1', 'turnId': 'turn-1'}}), flush=True)\n"
        "    elif request_id == 'native-1':\n"
        "        assert json.loads(line)['result']['decision'] == 'decline'\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"declined safely\\\","
        "\\\"artifact_refs\\\":[]}'}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )

    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="run a command only if approved",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        on_server_request=lambda *_: {"decision": "decline"},
    )

    assert result.output == {"text": "declined safely", "artifact_refs": []}


def test_codex_output_limit_interrupts_the_turn(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_output_limit.py"
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
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': 'output exceeds limit'}}), flush=True)\n"
        "    elif request_id == 4:\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexOutputLimitError, match="maxOutputBytes"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
            max_output_bytes=8,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_codex_deadline_covers_handshake_and_turn_start(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_slow_start.py"
    marker = tmp_path / "turn-started"
    fake.write_text(
        "import json, pathlib, sys, time\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        time.sleep(0.1)\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        time.sleep(0.1)\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        f"        pathlib.Path({str(marker)!r}).touch()\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-1'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexProtocolError, match="timed out"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=0.15,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )

    assert not marker.exists()


def test_codex_final_turn_items_obey_output_byte_limit(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_final_item_limit.py"
    _write_fake_codex(
        fake,
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {
                "method": "turn/completed",
                "params": {
                    "turn": {
                        "status": "completed",
                        "items": [
                            {
                                "type": "agentMessage",
                                "text": '{"text":"too large","artifact_refs":[]}',
                            }
                        ],
                    }
                },
            },
            {"method": "test/unused", "params": {}},
            {"method": "test/unused", "params": {}},
        ],
    )

    with pytest.raises(CodexOutputLimitError, match="maxOutputBytes"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
            max_output_bytes=8,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_expired_native_interaction_is_a_deadline_stop_request(tmp_path: Path) -> None:
    from multiverse_workflow.runtime.codex import CodexInteractionExpired

    fake = tmp_path / "fake_codex_expired_interaction.py"
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
        "        print(json.dumps({'id': 'native-1', 'method': "
        "'item/tool/requestUserInput', 'params': "
        "{'threadId': 'thread-1', 'turnId': 'turn-1'}}), flush=True)\n"
        "    elif request_id == 'native-1':\n"
        "        assert request.get('error', {}).get('code') == -32800\n"
        "    elif request_id == 4:\n"
        "        assert request['method'] == 'turn/interrupt'\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    def expired_request(*_: object) -> dict[str, object]:
        raise CodexInteractionExpired("Codex interaction expired")

    with pytest.raises(CodexInterruptedError) as raised:
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="request input",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            on_server_request=expired_request,
        )

    assert raised.value.deadline


def test_cancel_during_turn_start_interaction_requires_stop_confirmation(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_cancel_during_start.py"
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
        "        print(json.dumps({'id': 'native-1', 'method': "
        "'item/tool/requestUserInput', 'params': "
        "{'threadId': 'thread-1', 'turnId': 'turn-1'}}), flush=True)\n"
        "    elif request_id == 'native-1':\n"
        "        assert request['error']['code'] == -32800\n"
        "    elif request_id == 4:\n"
        "        assert request['method'] == 'turn/interrupt'\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexInterruptedError) as raised:
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="request input",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            on_server_request=lambda *_: (_ for _ in ()).throw(CodexRunCancelled()),
        )

    assert raised.value.cancelled


def test_interrupt_retains_completion_event_received_before_rpc_response(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_codex_early_completion.py"
    turn_started = tmp_path / "turn-started"
    fake.write_text(
        "import json, pathlib, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        f"        pathlib.Path({str(turn_started)!r}).touch()\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "    elif request_id == 4:\n"
        "        assert request['method'] == 'turn/interrupt'\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', "
        "'params': {'delta': '{\\\"text\\\":\\\"completed\\\",'"
        "'\\\"artifact_refs\\\":[]}'}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'completed'}}}), flush=True)\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n",
        encoding="utf-8",
    )

    result = CodexAppServer(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="wait to be cancelled",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
        should_stop=turn_started.exists,
    )

    assert result.output == {"text": "completed", "artifact_refs": []}


def test_interrupt_preserves_known_failed_terminal_turn(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_failed_completion.py"
    turn_started = tmp_path / "turn-started"
    fake.write_text(
        "import json, pathlib, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        f"        pathlib.Path({str(turn_started)!r}).touch()\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "    elif request_id == 4:\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'failed', "
        "'error': {'codexErrorInfo': 'known-failure', "
        "'message': 'provider token=interrupt-secret'}}}}), flush=True)\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexTurnFailed, match="known-failure") as raised:
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="wait to be cancelled",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            should_stop=turn_started.exists,
        )
    assert "interrupt-secret" not in str(raised.value)
    assert "interrupt-secret" not in json.dumps(raised.value.diagnostics)


def test_interrupt_failure_error_code_is_redacted(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_failed_error_code.py"
    turn_started = tmp_path / "turn-started"
    fake.write_text(
        "import json, pathlib, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        f"        pathlib.Path({str(turn_started)!r}).touch()\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "    elif request_id == 4:\n"
        "        print('interrupt stderr marker', file=sys.stderr, flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', "
        "'params': {'turn': {'status': 'failed', "
        "'error': {'codexErrorInfo': 'token=code-secret'}}}}), flush=True)\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexTurnFailed) as raised:
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
        ).run(
            prompt="wait to be cancelled",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            should_stop=turn_started.exists,
        )

    assert "code-secret" not in str(raised.value)
    assert "code-secret" not in json.dumps(raised.value.diagnostics)
    assert set(
        ["model", "cwd", "homeDir", "approvalPolicy", "sandboxMode", "events", "stderr"]
    ).issubset(raised.value.diagnostics)
    assert "interrupt stderr marker" in raised.value.diagnostics["stderr"]


def test_codex_app_server_rejects_an_oversized_protocol_line(tmp_path: Path) -> None:
    fake = tmp_path / "fake_codex_oversized_line.py"
    fake.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('id') == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request.get('id') == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-large'}}}), flush=True)\n"
        "    elif request.get('id') == 3:\n"
        "        print(json.dumps({'id': 3, 'result': "
        "{'turn': {'id': 'turn-large'}}}), flush=True)\n"
        "        sys.stdout.write('x' * (1024 * 1024 + 1) + '\\n')\n"
        "        sys.stdout.flush()\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexProtocolError, match="1 MiB"):
        CodexAppServer(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=3,
        ).run(
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
