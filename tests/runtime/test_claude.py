from __future__ import annotations

import sys
from pathlib import Path

import pytest

from multiverse_workflow.runtime.claude import (
    ClaudeCli,
    ClaudeOutputLimitError,
    ClaudeProtocolError,
)


def _write_fake(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_claude_cli_parses_structured_json_result(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude.py"
    _write_fake(
        fake,
        "import json,sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'result','subtype':'success',"
        "'result':'{\\\"text\\\":\\\"ok\\\",\\\"artifact_refs\\\":[]}',"
        "'session_id':'session-1'}))\n",
    )

    result = ClaudeCli(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.output == {"text": "ok", "artifact_refs": []}
    assert result.observation["sessionId"] == "session-1"
    assert result.observation["status"] == "completed"


def test_claude_cli_forces_structured_no_tool_mode(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_flags.py"
    _write_fake(
        fake,
        "import json,sys\n"
        "required=['--print','--output-format','json','--no-session-persistence',"
        "'--tools','--permission-mode','dontAsk']\n"
        "assert all(flag in sys.argv for flag in required), sys.argv\n"
        "print(json.dumps({'type':'result','subtype':'success',"
        "'result':'{\\\"text\\\":\\\"ok\\\",\\\"artifact_refs\\\":[]}' }))\n",
    )

    result = ClaudeCli(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.output["text"] == "ok"


def test_claude_cli_replaces_conflicting_mode_flags() -> None:
    args = ClaudeCli._with_options(
        ("claude", "--tools", "Bash", "--output-format", "text", "--print"),
        None,
        "dontAsk",
    )
    assert args.count("--print") == 1
    assert args[args.index("--output-format") + 1] == "json"
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in args


def test_claude_cli_replaces_equals_form_managed_flags() -> None:
    args = ClaudeCli._with_options(
        (
            "claude",
            "--tools=Bash",
            "--output-format=text",
            "--permission-mode=default",
            "--no-session-persistence=false",
            "--print=false",
        ),
        None,
        "dontAsk",
    )
    assert "--tools=Bash" not in args
    assert "--output-format=text" not in args
    assert "--permission-mode=default" not in args
    assert "--no-session-persistence=false" not in args
    assert "--print=false" not in args
    assert args[args.index("--output-format") + 1] == "json"


@pytest.mark.parametrize(
    "flag",
    ["--mcp-config=x.json", "--plugin-dir=plugins", "--add-dir=/tmp/extra"],
)
def test_claude_cli_rejects_security_extension_flags(flag: str) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        ClaudeCli(command=("claude", flag))


def test_claude_cli_rejects_wrapper_when_version_is_required() -> None:
    with pytest.raises(ClaudeProtocolError, match="wrapper"):
        ClaudeCli(
            command=(sys.executable, "-c", "print('unused')"),
            expected_version="2.1.197",
        ).run(
            prompt="return JSON",
            cwd=Path.cwd(),
            home_dir=Path.home(),
            output_schema={"type": "object"},
        )


def test_claude_cli_rejects_nonzero_exit(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_error.py"
    _write_fake(fake, "import sys; sys.stderr.write('denied'); sys.exit(3)\n")

    with pytest.raises(ClaudeProtocolError, match="exit code 3"):
        ClaudeCli(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_claude_cli_enforces_timeout(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_timeout.py"
    _write_fake(fake, "import time; time.sleep(2)\n")

    with pytest.raises(ClaudeProtocolError, match="timed out"):
        ClaudeCli(command=(sys.executable, "-u", str(fake)), timeout_seconds=0.05).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_claude_cli_stops_when_cooperative_stop_is_requested(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_stop.py"
    _write_fake(fake, "import time; time.sleep(5)\n")
    with pytest.raises(Exception, match="stopped"):
        ClaudeCli(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
            should_stop=lambda: True,
        )


def test_claude_cli_rejects_strict_version_mismatch(tmp_path: Path) -> None:
    fake = tmp_path / "claude"
    _write_fake(
        fake,
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if '--version' in sys.argv: print('2.1.197'); raise SystemExit(0)\n"
        "print('{}')\n",
    )
    fake.chmod(0o755)
    with pytest.raises(ClaudeProtocolError, match="version mismatch"):
        ClaudeCli(
            command=(str(fake),),
            expected_version="2.1.198",
            timeout_seconds=2,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_claude_cli_enforces_output_limit(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_output_limit.py"
    _write_fake(
        fake,
        "import sys\n"
        "sys.stdin.read()\n"
        "print('x' * 1000)\n",
    )

    with pytest.raises(ClaudeOutputLimitError, match="maxOutputBytes"):
        ClaudeCli(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
            max_output_bytes=32,
        ).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_claude_cli_rejects_non_json_result(tmp_path: Path) -> None:
    fake = tmp_path / "fake_claude_invalid.py"
    _write_fake(fake, "import sys; sys.stdout.write('not json\\n')\n")

    with pytest.raises(ClaudeProtocolError, match="structured JSON"):
        ClaudeCli(command=(sys.executable, "-u", str(fake)), timeout_seconds=2).run(
            prompt="return JSON",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )


def test_claude_stream_json_reassembles_fragmented_assistant_output(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake_claude_stream.py"
    output = [
        {"type": "system", "subtype": "init", "session_id": "stream-session"},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": '{"text":"streamed",'}]},
        },
        {"type": "content_block_delta", "delta": {"text": '"artifact_refs":[]}' }},
        {"type": "result", "subtype": "success", "result": None, "session_id": "stream-session"},
    ]
    _write_fake(
        fake,
        "import json,sys\n"
        "sys.stdin.read()\n"
        f"events={output!r}\n"
        "for event in events: print(json.dumps(event), flush=True)\n",
    )

    result = ClaudeCli(
        command=(sys.executable, "-u", str(fake)),
        timeout_seconds=2,
        output_format="stream-json",
    ).run(
        prompt="return JSON",
        cwd=tmp_path,
        home_dir=tmp_path,
        output_schema={"type": "object"},
    )

    assert result.output == {"text": "streamed", "artifact_refs": []}
    assert result.observation["sessionId"] == "stream-session"


def test_claude_stream_json_fails_closed_on_native_request(tmp_path: Path) -> None:
    from multiverse_workflow.runtime.claude import ClaudeProcessError

    fake = tmp_path / "fake_claude_request.py"
    _write_fake(
        fake,
        "import json,sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'request','request_id':'r1'}), flush=True)\n",
    )

    with pytest.raises(ClaudeProtocolError, match="unsupported interaction"):
        ClaudeCli(
            command=(sys.executable, "-u", str(fake)),
            timeout_seconds=2,
            output_format="stream-json",
        ).run(
            prompt="request an interaction",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )

    rejected = tmp_path / "fake_claude_rejected.py"
    _write_fake(
        rejected,
        "import json,sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'result','subtype':'error_max_turns',"
        "'is_error':True,'result':'rejected'}), flush=True)\n",
    )
    with pytest.raises(ClaudeProcessError, match="rejected"):
        ClaudeCli(
            command=(sys.executable, "-u", str(rejected)),
            timeout_seconds=2,
            output_format="stream-json",
        ).run(
            prompt="reject",
            cwd=tmp_path,
            home_dir=tmp_path,
            output_schema={"type": "object"},
        )
