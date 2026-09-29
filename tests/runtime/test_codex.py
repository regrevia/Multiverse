from __future__ import annotations

import sys
from pathlib import Path

import pytest

from multiverse_workflow.runtime.codex import (
    CodexAppServer,
    CodexInterruptedError,
    CodexOutputLimitError,
    CodexProtocolError,
    CodexRunCancelled,
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
        "'error': {'codexErrorInfo': 'known-failure'}}}}), flush=True)\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n",
        encoding="utf-8",
    )

    with pytest.raises(CodexProtocolError, match="known-failure"):
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
