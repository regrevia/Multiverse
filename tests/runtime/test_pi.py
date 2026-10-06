from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.pi import (
    PiCancelledError,
    PiProcessError,
    PiProtocolError,
    PiRpc,
)


def _fake(path: Path, records: list[dict[str, object]], version: str = "0.73.1") -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        f"if '--version' in sys.argv: print({version!r}); raise SystemExit(0)\n"
        "sys.stdin.readline()\n"
        f"records={records!r}\n"
        "for record in records: print(json.dumps(record), flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_pi_rpc_reassembles_jsonl_message_update(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(
        fake,
        [
            {"type": "session_start", "sessionId": "pi-session-1"},
            {
                "type": "response",
                "id": "prompt-1",
                "command": "prompt",
                "success": True,
                "data": {"disposition": "started"},
            },
            {"type": "message_start", "message": {"role": "assistant", "content": []}},
            {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3},
            {"type": "auto_retry_end", "success": True, "attempt": 1},
            {"type": "summarization_retry_scheduled", "attempt": 1},
            {"type": "summarization_retry_attempt_start", "source": "compaction"},
            {"type": "summarization_retry_finished"},
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_delta",
                    "delta": '{"text":"pi",',
                },
            },
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_delta",
                    "delta": '"artifact_refs":[]}',
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": '{"text":"authoritative","artifact_refs":[]}',
                        }
                    ],
                },
            },
            {"type": "agent_settled"},
        ],
    )
    result = PiRpc(
        command=(str(fake),),
        timeout_seconds=2,
        expected_version="0.73.1",
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )
    assert result.output == {"text": "authoritative", "artifact_refs": []}
    assert result.observation["sessionId"] == "pi-session-1"


def test_pi_rpc_rejects_unknown_record_type(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(fake, [{"type": "unexpected"}])
    with pytest.raises(PiProtocolError, match="unsupported"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version="0.73.1").run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_requires_response_before_settled(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(fake, [{"type": "agent_settled"}])
    with pytest.raises(PiProtocolError, match="before prompt response"):
        PiRpc(
            command=(str(fake),),
            timeout_seconds=2,
            expected_version="0.73.1",
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_rejects_handled_prompt_without_agent_run(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(
        fake,
        [
            {
                "type": "response",
                "id": "prompt-1",
                "command": "prompt",
                "success": True,
                "data": {"disposition": "handled"},
            }
        ],
    )
    with pytest.raises(PiProcessError, match="handled without an agent run"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version="0.73.1").run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_rejects_incomplete_prompt_response(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(fake, [{"type": "response", "id": "prompt-1", "success": True}])
    with pytest.raises(PiProtocolError, match="prompt response"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version="0.73.1").run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_ignores_tool_only_intermediate_message_end(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(
        fake,
        [
            {
                "type": "response",
                "id": "prompt-1",
                "command": "prompt",
                "success": True,
                "data": {"disposition": "started"},
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "name": "bash"}],
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": '{"text":"done","artifact_refs":[]}'}
                    ],
                },
            },
            {"type": "agent_settled"},
        ],
    )
    result = PiRpc(
        command=(str(fake),), timeout_seconds=2, expected_version="0.73.1"
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )
    assert result.output["text"] == "done"


def test_pi_rpc_rejects_unknown_or_error_message_update(tmp_path: Path) -> None:
    for event, error in (
        ({"type": "mystery"}, "unsupported"),
        ({"type": "error", "error": "provider failed"}, "provider failed"),
    ):
        fake = tmp_path / f"pi-{error.replace(' ', '-')}"
        _fake(
            fake,
            [
                {
                    "type": "response",
                    "id": "prompt-1",
                    "command": "prompt",
                    "success": True,
                    "data": {"disposition": "started"},
                },
                {"type": "message_update", "assistantMessageEvent": event},
            ],
        )
        with pytest.raises(PiProtocolError, match=error):
            PiRpc(
                command=(str(fake),), timeout_seconds=2, expected_version=None
            ).run(
                prompt="return JSON",
                cwd=tmp_path,
                home_dir=tmp_path,
                output_schema={"type": "object"},
            )


def test_pi_rpc_classifies_assistant_stop_reasons(tmp_path: Path) -> None:
    for stop_reason, error_type, message in (
        ("error", PiProcessError, "stopReason=error"),
        ("aborted", PiCancelledError, "stopReason=aborted"),
    ):
        fake = tmp_path / f"pi-{stop_reason}"
        _fake(
            fake,
            [
                {
                    "type": "response",
                    "id": "prompt-1",
                    "command": "prompt",
                    "success": True,
                    "data": {"disposition": "started"},
                },
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "stopReason": stop_reason,
                        "content": [],
                    },
                },
            ],
        )
        with pytest.raises(error_type, match=message):
            PiRpc(
                command=(str(fake),), timeout_seconds=2, expected_version=None
            ).run(
                prompt="return JSON",
                cwd=tmp_path,
                home_dir=tmp_path,
                output_schema={"type": "object"},
            )


def test_pi_rpc_rejects_final_assistant_message_without_text(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(
        fake,
        [
            {
                "type": "response",
                "id": "prompt-1",
                "command": "prompt",
                "success": True,
                "data": {"disposition": "started"},
            },
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_delta",
                    "delta": '{"text":"stale","artifact_refs":[]}',
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "name": "bash"}],
                },
            },
            {"type": "agent_settled"},
        ],
    )
    with pytest.raises(PiProtocolError, match="final assistant message"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version=None).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_does_not_reuse_previous_final_text(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    _fake(
        fake,
        [
            {
                "type": "response",
                "id": "prompt-1",
                "command": "prompt",
                "success": True,
                "data": {"disposition": "started"},
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": '{"text":"old","artifact_refs":[]}'}],
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "toolCall", "name": "bash"}],
                },
            },
            {"type": "agent_settled"},
        ],
    )
    with pytest.raises(PiProtocolError, match="final assistant message"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version=None).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_reports_child_exit_before_settled(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdin.readline()\n"
        "sys.stderr.write('provider unavailable')\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    with pytest.raises(PiProcessError, match="exit code 7.*provider unavailable"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version=None).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_rejects_non_object_jsonl_records(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "sys.stdin.readline()\n"
        "print(json.dumps(['not', 'a', 'record']), flush=True)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    with pytest.raises(PiProtocolError, match="record must be an object"):
        PiRpc(command=(str(fake),), timeout_seconds=2, expected_version=None).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_pi_rpc_deadline_covers_blocked_prompt_write(tmp_path: Path) -> None:
    fake = tmp_path / "pi"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import time\n"
        "time.sleep(2)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    with pytest.raises(PiProtocolError, match="timed out"):
        PiRpc(command=(str(fake),), timeout_seconds=0.05, expected_version=None).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )
