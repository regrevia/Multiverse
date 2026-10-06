from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PiProtocolError(RuntimeError):
    """Pi RPC did not produce a usable protocol result."""


class PiProcessError(PiProtocolError):
    """Pi RPC reported a known command or provider failure."""


class PiDeadlineError(PiProtocolError):
    """Pi RPC exceeded its configured deadline."""


class PiCancelledError(PiProtocolError):
    """Pi RPC was cooperatively stopped."""


class PiVersionMismatchError(PiProcessError):
    """The configured Pi executable is not the declared version."""


@dataclass(frozen=True)
class PiResult:
    output: dict[str, Any]
    observation: dict[str, Any]


class PiRpc:
    def __init__(
        self,
        *,
        command: tuple[str, ...] = ("pi", "--mode", "rpc", "--no-session"),
        model: str | None = None,
        timeout_seconds: float = 180.0,
        max_output_bytes: int = 262144,
        expected_version: str | None = None,
    ) -> None:
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ValueError("pi command must be a non-empty argument array")
        if timeout_seconds <= 0:
            raise ValueError("pi timeoutSeconds must be positive")
        if max_output_bytes < 1:
            raise ValueError("pi maxOutputBytes must be positive")
        self.command = self._with_options(command, model)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.expected_version = expected_version
        self._last_session: str | None = None
        self._response_accepted = False
        self._settled = False
        self._final_assistant_text: str | None = None
        self._assistant_message_ended = False

    @staticmethod
    def _with_options(command: tuple[str, ...], model: str | None) -> tuple[str, ...]:
        args = list(command)
        if "--mode" not in args:
            args.extend(["--mode", "rpc"])
        if "--no-session" not in args:
            args.append("--no-session")
        if model and "--model" not in args:
            args.extend(["--model", model])
        return tuple(args)

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        home_dir: Path,
        output_schema: dict[str, Any],
        should_stop: Any = None,
    ) -> PiResult:
        if not prompt.strip():
            raise ValueError("pi prompt must not be empty")
        deadline = time.monotonic() + self.timeout_seconds
        if self.expected_version:
            if Path(self.command[0]).name != "pi":
                raise PiVersionMismatchError(
                    "Pi expectedVersion cannot be verified for a wrapper command"
                )
            try:
                version = subprocess.run(
                    (self.command[0], "--version"),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=max(0.01, deadline - time.monotonic()),
                ).stdout.strip()
            except subprocess.TimeoutExpired as exc:
                raise PiDeadlineError("Pi version check timed out") from exc
            actual = version.split(maxsplit=1)[0]
            if actual != self.expected_version:
                raise PiVersionMismatchError(
                    f"Pi version mismatch: expected {self.expected_version}, got {version}"
                )
        process = subprocess.Popen(
            self.command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "LANG": "C.UTF-8",
                "HOME": str(home_dir),
            },
        )
        try:
            assert process.stdin and process.stdout and process.stderr
            self._last_session = None
            self._response_accepted = False
            self._settled = False
            self._final_assistant_text = None
            self._assistant_message_ended = False
            command = {"id": "prompt-1", "type": "prompt", "message": prompt}
            payload = json.dumps(command).encode("utf-8") + b"\n"
            selector = selectors.DefaultSelector()
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stderr.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            input_offset = 0
            output = bytearray()
            fragments: list[str] = []
            output_bytes = 0
            session_id: str | None = None
            settled = False
            stderr = bytearray()
            try:
                while selector.get_map() or process.poll() is None:
                    now = time.monotonic()
                    if should_stop is not None and should_stop():
                        if not self._stop_process(process):
                            raise PiProtocolError("Pi stop is unconfirmed")
                        raise PiCancelledError("Pi process was cooperatively stopped")
                    if now >= deadline:
                        if not self._stop_process(process):
                            raise PiProtocolError("Pi timeout stop is unconfirmed")
                        raise PiDeadlineError("Pi RPC timed out")
                    events = selector.select(min(0.05, deadline - now))
                    for key, _ in events:
                        if key.fileobj is process.stdin:
                            try:
                                input_offset += os.write(
                                    process.stdin.fileno(), payload[input_offset:]
                                )
                            except BrokenPipeError:
                                input_offset = len(payload)
                            if input_offset == len(payload):
                                selector.unregister(process.stdin)
                                process.stdin.close()
                            continue
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if key.fileobj is process.stdout:
                            output.extend(chunk)
                            output_bytes += len(chunk)
                            if output_bytes > self.max_output_bytes:
                                if not self._stop_process(process):
                                    raise PiProtocolError("Pi output stop is unconfirmed")
                                raise PiProtocolError("Pi output exceeded maxOutputBytes")
                            for line in output.split(b"\n")[:-1]:
                                self._consume_record(
                                    json.loads(line.decode("utf-8").rstrip("\r")),
                                    fragments,
                                )
                            if b"\n" in output:
                                output = bytearray(output.rsplit(b"\n", 1)[1])
                        else:
                            stderr.extend(chunk[:65536 - len(stderr)])
                    if self._last_session is not None:
                        session_id = self._last_session
                    if self._settled:
                        settled = True
                        break
                    if process.poll() is not None:
                        detail = bytes(stderr).decode("utf-8", errors="replace").strip()
                        suffix = f"exit code {process.returncode}"
                        if detail:
                            suffix = f"{suffix}: {detail}"
                        raise PiProcessError(
                            f"Pi process exited before agent_settled: {suffix}"
                        )
                if not settled:
                    raise PiDeadlineError("Pi RPC did not reach agent_settled")
                if process.poll() is not None and self._group_alive(process.pid):
                    self._kill_group(process.pid)
                    raise PiProtocolError(
                        "Pi leader exited while its process group remained active"
                    )
                if output.strip():
                    self._consume_record(
                        json.loads(output.decode("utf-8").rstrip("\r")),
                        fragments,
                    )
            except json.JSONDecodeError as exc:
                raise PiProtocolError("Pi emitted invalid JSONL") from exc
            finally:
                selector.close()
            if self._assistant_message_ended and self._final_assistant_text is None:
                raise PiProtocolError("Pi final assistant message has no text content")
            try:
                payload = json.loads(
                    (
                        self._final_assistant_text
                        if self._assistant_message_ended
                        else "".join(fragments)
                    ).strip()
                )
            except json.JSONDecodeError as exc:
                raise PiProtocolError("Pi final assistant message was not JSON") from exc
            if not isinstance(payload, dict):
                raise PiProtocolError("Pi final assistant message must be an object")
            return PiResult(
                output=payload,
                observation={
                    "provider": "pi",
                    "protocol": "rpc-jsonl",
                    "sessionId": session_id,
                    "status": "completed",
                    "outputSchema": output_schema,
                },
            )
        finally:
            if process.poll() is None or self._group_alive(process.pid):
                if not self._stop_process(process):
                    raise PiProtocolError("Pi cleanup stop is unconfirmed")

    def _consume_record(
        self,
        record: dict[str, Any],
        fragments: list[str],
    ) -> None:
        if not isinstance(record, dict):
            raise PiProtocolError("Pi RPC record must be an object")
        record_type = record.get("type")
        if record_type == "response":
            if record.get("id") != "prompt-1" or record.get("command") != "prompt":
                raise PiProtocolError("Pi prompt response command does not match prompt")
            if record.get("success") is not True:
                raise PiProcessError(str(record.get("error", "Pi prompt failed")))
            data = record.get("data")
            disposition = data.get("disposition") if isinstance(data, dict) else None
            if disposition == "handled":
                raise PiProcessError("Pi prompt was handled without an agent run")
            if disposition not in {"started", "queued"}:
                raise PiProtocolError(f"unsupported Pi prompt disposition: {disposition}")
            self._response_accepted = True
            return
        if record_type == "agent_settled":
            if not self._response_accepted:
                raise PiProtocolError("Pi settled before prompt response was accepted")
            self._settled = True
            return
        if record_type == "message_update":
            event = record.get("assistantMessageEvent")
            if not isinstance(event, dict):
                raise PiProtocolError("Pi message_update event must be an object")
            event_type = event.get("type")
            if event_type == "text_delta":
                delta = event.get("delta")
                if not isinstance(delta, str):
                    raise PiProtocolError("Pi text_delta must contain string delta")
                fragments.append(delta)
            elif event_type == "error":
                raise PiProcessError(str(event.get("error", "Pi provider failed")))
            elif event_type not in {
                "start",
                "text_start",
                "text_end",
                "thinking_start",
                "thinking_delta",
                "thinking_end",
                "toolcall_start",
                "toolcall_delta",
                "toolcall_end",
                "done",
            }:
                raise PiProtocolError(
                    f"unsupported Pi assistant message event type: {event_type}"
                )
            return
        if record_type == "message_end":
            message = record.get("message")
            if not isinstance(message, dict):
                raise PiProtocolError("Pi message_end message must be an object")
            if message.get("role") == "assistant":
                self._assistant_message_ended = True
                stop_reason = message.get("stopReason")
                if stop_reason == "error":
                    raise PiProcessError("Pi assistant message stopReason=error")
                if stop_reason == "aborted":
                    raise PiCancelledError("Pi assistant message stopReason=aborted")
                if stop_reason not in {None, "stop", "toolUse", "length"}:
                    raise PiProtocolError(
                        f"unsupported Pi assistant stopReason: {stop_reason}"
                    )
                content = message.get("content")
                if not isinstance(content, list):
                    raise PiProtocolError("Pi assistant message content must be an array")
                text = "".join(
                    block["text"]
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                )
                self._final_assistant_text = text or None
            return
        if record_type in {"session_start", "session"}:
            value = record.get("sessionId") or record.get("session_id")
            if isinstance(value, str):
                self._last_session = value
            return
        if record_type in {
            "agent_start",
            "agent_end",
            "tool_execution_start",
            "tool_execution_update",
            "tool_execution_end",
            "turn_start",
            "turn_end",
            "message_start",
            "queue_update",
            "entry_appended",
            "session_info_changed",
            "thinking_level_changed",
            "compaction_start",
            "compaction_end",
            "auto_retry_start",
            "auto_retry_end",
            "summarization_retry_scheduled",
            "summarization_retry_attempt_start",
            "summarization_retry_finished",
        }:
            return
        raise PiProtocolError(f"unsupported Pi RPC record type: {record_type}")

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes]) -> bool:
        if process.poll() is not None:
            if not PiRpc._group_alive(process.pid):
                return True
            return PiRpc._kill_group(process.pid)
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=1)
        except (ProcessLookupError, PermissionError):
            return False
        except subprocess.TimeoutExpired:
            return PiRpc._kill_group(process.pid, process)
        if PiRpc._group_alive(process.pid):
            return PiRpc._kill_group(process.pid, process)
        return True

    @staticmethod
    def _kill_group(
        process_group: int,
        process: subprocess.Popen[bytes] | None = None,
    ) -> bool:
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return False
        return not PiRpc._group_alive(process_group)

    @staticmethod
    def _group_alive(process_group: int) -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
