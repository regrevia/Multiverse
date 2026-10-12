from __future__ import annotations

import json
import os
import re
import selectors
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class CodexProtocolError(RuntimeError):
    """Codex App Server returned an unusable response or lost its process."""


class CodexInterruptedError(CodexProtocolError):
    """Codex acknowledged a cooperative turn interruption."""

    def __init__(
        self,
        message: str,
        *,
        deadline: bool = False,
        cancelled: bool = False,
    ) -> None:
        super().__init__(message)
        self.deadline = deadline
        self.cancelled = cancelled


class CodexStopRequested(CodexProtocolError):
    """A persisted control condition requires the active Codex turn to stop."""

    def __init__(
        self, message: str, *, deadline: bool = False, cancelled: bool = False
    ) -> None:
        super().__init__(message)
        self.deadline = deadline
        self.cancelled = cancelled


class CodexInteractionExpired(CodexStopRequested):
    """A persisted native interaction expired before it received a reply."""

    def __init__(self, message: str) -> None:
        super().__init__(message, deadline=True)


class CodexRunCancelled(CodexStopRequested):
    """The owning Run received a cancellation request."""

    def __init__(self, message: str = "Run cancellation requested") -> None:
        super().__init__(message, cancelled=True)


class CodexOutputLimitError(CodexProtocolError):
    """Codex output exceeded the configured cap and the turn was stopped."""


class CodexTurnFailed(CodexProtocolError):
    """Codex reported a known failed terminal turn."""

    def __init__(
        self, message: str, *, diagnostics: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


_SENSITIVE_DIAGNOSTIC_KEY = re.compile(
    r"(authorization|token|secret|password|api[_-]?key|credential|cookie)",
    re.IGNORECASE,
)
_SENSITIVE_DIAGNOSTIC_VALUE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*"
    r"|\b(?:sk-ant-|sk-|ghp_|gho_|github_pat_)[A-Za-z0-9_-]{12,}\b"
    r"|((?:--?|[?&])(?:access[_-]?token|api[_-]?key|token|secret|password)="
    r")[^&\s]+"
    r"|((?:access[_-]?token|api[_-]?key|token|secret|password)\s*[:=]\s*)"
    r"['\"]?[^'\"\s,;]+"
)
_CODEX_RUNTIME_EVENT_METHODS = frozenset(
    {
        "item/agentMessage/delta",
        "item/agentMessage/completed",
        "item/commandExecution/started",
        "item/commandExecution/completed",
        "item/fileChange/started",
        "item/fileChange/completed",
        "item/started",
        "item/completed",
        "turn/started",
        "turn/completed",
        "thread/started",
        "thread/tokenUsage/updated",
    }
)
_MAX_PROTOCOL_LINE_BYTES = 1024 * 1024
_MAX_EVENT_BYTES = 16 * 1024
_MAX_EVENT_COUNT = 2000
_MAX_EVENT_TOTAL_BYTES = 512 * 1024


def sanitize_codex_diagnostics(value: Any) -> Any:
    """Bound and redact provider diagnostics before they enter the Ledger."""
    if isinstance(value, dict):
        return {
            str(key)[:128]: (
                "[REDACTED]"
                if _SENSITIVE_DIAGNOSTIC_KEY.search(str(key))
                else sanitize_codex_diagnostics(item)
            )
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, list):
        return [sanitize_codex_diagnostics(item) for item in value[:20]]
    if isinstance(value, str):
        redacted = _SENSITIVE_DIAGNOSTIC_VALUE.sub(
            lambda match: (
                f"{match.group(1) or match.group(2) or match.group(3)}[REDACTED]"
                if match.group(1) or match.group(2) or match.group(3)
                else (
                    "[REDACTED]"
                )
            ),
            value,
        )
        return redacted[:1500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return f"<{type(value).__name__}>"


class _BoundedTail:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self.truncated = False

    def write(self, value: bytes) -> None:
        with self._lock:
            self._buffer.extend(value)
            if len(self._buffer) > self.max_bytes:
                del self._buffer[: len(self._buffer) - self.max_bytes]
                self.truncated = True

    def getvalue(self) -> bytes:
        with self._lock:
            return bytes(self._buffer)


@dataclass(frozen=True)
class CodexResult:
    output: dict[str, Any]
    observation: dict[str, Any]


class CodexAppServer:
    def __init__(
        self,
        *,
        command: tuple[str, ...] = ("codex", "app-server", "--stdio"),
        model: str | None = None,
        timeout_seconds: float = 180.0,
        approval_policy: str = "never",
        sandbox_mode: str = "workspace-write",
        max_output_bytes: int = 262144,
        session_mode: str = "new",
        native_session_id: str | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("codex command must be a non-empty argument array")
        if timeout_seconds <= 0:
            raise ValueError("codex timeoutSeconds must be positive")
        if approval_policy not in {"never", "on-request", "untrusted"}:
            raise ValueError("unsupported Codex approvalPolicy")
        if sandbox_mode not in {
            "read-only",
            "workspace-write",
            "danger-full-access",
        }:
            raise ValueError("unsupported Codex sandboxMode")
        if max_output_bytes < 1:
            raise ValueError("codex maxOutputBytes must be positive")
        if session_mode not in {"new", "resume", "fork"}:
            raise ValueError("unsupported Codex sessionMode")
        if session_mode in {"resume", "fork"} and not native_session_id:
            raise ValueError("Codex resume/fork requires nativeSessionId")
        if session_mode == "new" and native_session_id:
            raise ValueError("Codex new session cannot include nativeSessionId")
        self.command, self.model, self.timeout_seconds = command, model, timeout_seconds
        self.approval_policy = approval_policy
        self.sandbox_mode = sandbox_mode
        self.max_output_bytes = max_output_bytes
        self.session_mode = session_mode
        self.native_session_id = native_session_id
        self._read_buffer = bytearray()
        self._pending_messages: deque[dict[str, Any]] = deque()
        self._last_terminal_error: str | None = None
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=20)
        self._stderr_buffer: _BoundedTail | None = None
        self._stderr_reader: threading.Thread | None = None
        self._diagnostic_context: dict[str, Any] = {}

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        home_dir: Path,
        output_schema: dict[str, Any],
        on_server_request: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
        on_server_response: Callable[[str, dict[str, Any]], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> CodexResult:
        deadline = time.monotonic() + self.timeout_seconds
        self._read_buffer.clear()
        self._pending_messages.clear()
        self._last_terminal_error = None
        self._last_terminal_error_payload: dict[str, Any] | None = None
        self._recent_events.clear()
        self._diagnostic_context = {
            "provider": "codex",
            "protocol": "app-server",
            "model": self.model,
            "cwd": str(cwd),
            "homeDir": str(home_dir),
            "approvalPolicy": self.approval_policy,
            "sandboxMode": self.sandbox_mode,
        }
        stderr_buffer = _BoundedTail(32768)
        self._stderr_buffer = stderr_buffer
        process = subprocess.Popen(
            self.command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "LANG": "C.UTF-8",
                "HOME": str(home_dir),
            },
        )
        assert process.stderr
        stderr_reader = threading.Thread(
            target=self._drain_stderr,
            args=(process.stderr, stderr_buffer),
            name="multiverse-codex-stderr",
            daemon=True,
        )
        stderr_reader.start()
        self._stderr_reader = stderr_reader
        emitted_event_count = 0
        emitted_event_bytes = 0
        event_budget_exhausted = False

        def emit_event(event: dict[str, Any]) -> None:
            nonlocal emitted_event_count, emitted_event_bytes, event_budget_exhausted
            if on_event is None or event_budget_exhausted:
                return
            safe_event = sanitize_codex_diagnostics(event)
            serialized = json.dumps(
                safe_event, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(serialized) > _MAX_EVENT_BYTES:
                safe_event = {
                    "method": event["method"],
                    "params": {
                        "truncated": True,
                        "payloadBytes": len(serialized),
                    },
                    "receivedAt": event["receivedAt"],
                }
                serialized = json.dumps(
                    safe_event, separators=(",", ":")
                ).encode("utf-8")
            if (
                emitted_event_count >= _MAX_EVENT_COUNT
                or emitted_event_bytes + len(serialized) > _MAX_EVENT_TOTAL_BYTES
            ):
                event_budget_exhausted = True
                marker = {
                    "method": "runtime/events_truncated",
                    "params": {
                        "maxEvents": _MAX_EVENT_COUNT,
                        "maxBytes": _MAX_EVENT_TOTAL_BYTES,
                    },
                    "receivedAt": time.time(),
                }
                on_event(marker)
                return
            emitted_event_count += 1
            emitted_event_bytes += len(serialized)
            on_event(safe_event)

        def stop_process_and_drain_stderr() -> None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            stderr_reader.join(timeout=2)

        try:
            request_id = 1
            self._send(
                process,
                request_id,
                "initialize",
                {
                    "clientInfo": {"name": "multiverse-runtime", "version": "0.1.0"},
                    "capabilities": {},
                },
            )
            self._read_response(
                process,
                request_id,
                on_server_request,
                deadline=deadline,
                should_stop=should_stop,
            )
            self._send_notification(process, "initialized", {})
            request_id = 2
            thread_method = {
                "new": "thread/start",
                "resume": "thread/resume",
                "fork": "thread/fork",
            }[self.session_mode]
            thread_params: dict[str, Any] = {
                "cwd": str(cwd),
                "approvalPolicy": self.approval_policy,
                "sandbox": self.sandbox_mode,
                **({"model": self.model} if self.model else {}),
            }
            if self.session_mode != "new":
                thread_params["threadId"] = self.native_session_id
            self._send(process, request_id, thread_method, thread_params)
            thread_id = self._read_response(
                process,
                request_id,
                on_server_request,
                deadline=deadline,
                should_stop=should_stop,
            ).get("thread", {}).get("id")
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexProtocolError("thread/start did not return a thread id")
            if should_stop is not None and should_stop():
                raise CodexRunCancelled()
            request_id = 3
            self._send(
                process,
                request_id,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "approvalPolicy": self.approval_policy,
                    "outputSchema": output_schema,
                },
            )
            turn_id = self._read_response(
                process,
                request_id,
                on_server_request,
                deadline=deadline,
                should_stop=should_stop,
            ).get("turn", {}).get("id")
            if not isinstance(turn_id, str) or not turn_id:
                raise CodexProtocolError("turn/start did not return a turn id")
            parts: list[str] = []
            output_bytes = 0
            stop_requested = False
            try:
                while time.monotonic() < deadline:
                    if not stop_requested and should_stop is not None and should_stop():
                        self._interrupt_or_raise(
                            process,
                            thread_id,
                            turn_id,
                            request_id + 1,
                            "Codex turn interrupted after Run cancellation",
                            cancelled=True,
                        )
                        stop_requested = True
                    try:
                        message = self._read_message(
                            process,
                            min(0.1, deadline - time.monotonic()),
                        )
                    except CodexProtocolError as exc:
                        if (
                            "timed out" in str(exc)
                            and time.monotonic() < deadline
                        ):
                            continue
                        raise
                    method = message.get("method")
                    if method in _CODEX_RUNTIME_EVENT_METHODS:
                        event = {
                            "method": method,
                            "params": message.get("params", {}),
                            "receivedAt": time.time(),
                        }
                        safe_event = sanitize_codex_diagnostics(event)
                        if len(
                            json.dumps(
                                safe_event, ensure_ascii=False, separators=(",", ":")
                            ).encode("utf-8")
                        ) > _MAX_EVENT_BYTES:
                            safe_event = {
                                "method": method,
                                "params": {"truncated": True},
                                "receivedAt": event["receivedAt"],
                            }
                        self._recent_events.append(safe_event)
                        emit_event(event)
                    if "method" in message and "id" in message:
                        if on_server_request is None:
                            raise CodexProtocolError(
                                f"unhandled Codex server request: {message['method']}"
                            )
                        params = message.get("params")
                        if not isinstance(params, dict):
                            raise CodexProtocolError(
                                "Codex server request params must be an object"
                            )
                        try:
                            response = on_server_request(
                                str(message["id"]),
                                str(message["method"]),
                                params,
                            )
                            if should_stop is not None and should_stop():
                                raise CodexRunCancelled()
                        except CodexStopRequested as exc:
                            self._send_server_error(process, message["id"], str(exc))
                            self._interrupt_or_raise(
                                process,
                                thread_id,
                                turn_id,
                                request_id + 1,
                                str(exc),
                                deadline=exc.deadline,
                                cancelled=exc.cancelled,
                            )
                        self._send_server_response(process, message["id"], response)
                        if on_server_response is not None:
                            on_server_response(str(message["id"]), response)
                        continue
                    if message.get("method") == "item/agentMessage/delta":
                        delta = message.get("params", {}).get("delta")
                        if isinstance(delta, str):
                            output_bytes += len(delta.encode("utf-8"))
                            if output_bytes > self.max_output_bytes:
                                if (
                                    self._interrupt_active_turn(
                                        process, thread_id, turn_id, request_id + 1
                                    )
                                    == "interrupted"
                                ):
                                    raise CodexOutputLimitError(
                                        "Codex output exceeded maxOutputBytes"
                                    )
                                raise CodexProtocolError(
                                    "Codex output limit exceeded and stop is unconfirmed"
                                )
                            parts.append(delta)
                    if message.get("method") == "turn/completed":
                        turn = message.get("params", {}).get("turn", {})
                        turn_status = turn.get("status")
                        if turn_status == "interrupted":
                            raise CodexInterruptedError(
                                "Codex turn completed with interrupted status"
                            )
                        if turn_status != "completed":
                            error = turn.get("error")
                            self._last_terminal_error_payload = (
                                error if isinstance(error, dict) else None
                            )
                            error_code = (
                                error.get("codexErrorInfo")
                                if isinstance(error, dict)
                                else None
                            )
                            message_text = (
                                error.get("message", "")
                                if isinstance(error, dict)
                                else ""
                            )
                            stop_process_and_drain_stderr()
                            stderr_text = sanitize_codex_diagnostics(
                                stderr_buffer.getvalue().decode(
                                    "utf-8", errors="replace"
                                )
                            )
                            safe_error_code = (
                                sanitize_codex_diagnostics(error_code)
                                if isinstance(error_code, str)
                                else None
                            )
                            raise CodexTurnFailed(
                                "Codex turn ended with "
                                f"status={turn_status or 'unknown'}"
                                + (
                                    f", errorCode={safe_error_code}"
                                    if isinstance(safe_error_code, str)
                                    else ""
                                )
                                + (
                                    f": {sanitize_codex_diagnostics(message_text)}"
                                    if isinstance(message_text, str) and message_text
                                    else ""
                                ),
                                diagnostics=sanitize_codex_diagnostics({
                                    "provider": "codex",
                                    "protocol": "app-server",
                                    "model": self.model,
                                    "cwd": str(cwd),
                                    "homeDir": str(home_dir),
                                    "approvalPolicy": self.approval_policy,
                                    "sandboxMode": self.sandbox_mode,
                                    "threadId": thread_id,
                                    "turnId": turn_id,
                                    "turnStatus": turn_status,
                                    "turnError": error,
                                    "events": list(self._recent_events),
                                "stderr": stderr_text,
                                "stderrTruncated": stderr_buffer.truncated,
                                }),
                            )
                        if not parts:
                            for item in turn.get("items", []):
                                if item.get("type") == "agentMessage" and isinstance(
                                    item.get("text"), str
                                ):
                                    text = item["text"]
                                    output_bytes += len(text.encode("utf-8"))
                                    if output_bytes > self.max_output_bytes:
                                        raise CodexOutputLimitError(
                                            "Codex output exceeded maxOutputBytes"
                                        )
                                    parts.append(text)
                        break
                else:
                    raise CodexProtocolError("Codex App Server timed out")
            except CodexProtocolError as exc:
                if "timed out" not in str(exc):
                    raise
                if (
                    self._interrupt_active_turn(process, thread_id, turn_id, request_id + 1)
                    == "interrupted"
                ):
                    raise CodexInterruptedError(
                        "Codex turn interrupted after timeout", deadline=True
                    ) from exc
                raise
            try:
                output = json.loads("".join(parts).strip())
            except json.JSONDecodeError as exc:
                raise CodexProtocolError("Codex final message was not JSON") from exc
            if not isinstance(output, dict):
                raise CodexProtocolError("Codex output must be an object")
            return CodexResult(
                output,
                {
                    "provider": "codex",
                    "protocol": "app-server",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "sessionMode": self.session_mode,
                    "model": self.model,
                    "status": "completed",
                },
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if process.stderr:
                process.stderr.close()
            stderr_reader.join(timeout=2)

    @staticmethod
    def _drain_stderr(stream: Any, tail: _BoundedTail) -> None:
        try:
            while chunk := os.read(stream.fileno(), 4096):
                tail.write(chunk)
        except OSError:
            return

    @staticmethod
    def interrupt(
        *,
        command: tuple[str, ...],
        home_dir: Path,
        thread_id: str,
        turn_id: str,
        timeout_seconds: float = 10.0,
    ) -> str | None:
        """Request cooperative stop through a fresh App Server connection."""
        process = subprocess.Popen(
            command,
            cwd=home_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "LANG": "C.UTF-8",
                "HOME": str(home_dir),
            },
        )
        bridge = CodexAppServer(command=command, timeout_seconds=timeout_seconds)
        try:
            bridge._send(process, 1, "initialize", {
                "clientInfo": {"name": "multiverse-runtime", "version": "0.1.0"},
                "capabilities": {},
            })
            bridge._read_response(process, 1)
            bridge._send_notification(process, "initialized", {})
            bridge._send(process, 2, "turn/interrupt", {
                "threadId": thread_id,
                "turnId": turn_id,
            })
            bridge._read_response(process, 2)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                message = bridge._read_message(process, deadline - time.monotonic())
                if message.get("method") != "turn/completed":
                    continue
                turn = message.get("params", {}).get("turn", {})
                status = turn.get("status")
                return status if isinstance(status, str) else None
            return None
        except CodexProtocolError:
            return None
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

    def _interrupt_active_turn(
        self,
        process: subprocess.Popen[bytes],
        thread_id: str,
        turn_id: str,
        request_id: int,
    ) -> str | None:
        self._send(
            process,
            request_id,
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
        )
        self._read_response(process, request_id)
        confirmation_deadline = time.monotonic() + 5.0
        while time.monotonic() < confirmation_deadline:
            try:
                message = self._read_message(
                    process, confirmation_deadline - time.monotonic()
                )
            except CodexProtocolError:
                return None
            if message.get("method") != "turn/completed":
                self._pending_messages.append(message)
                continue
            turn = message.get("params", {}).get("turn", {})
            status = turn.get("status")
            if not isinstance(status, str):
                return None
            self._pending_messages.append(message)
            if status == "failed":
                error = turn.get("error")
                code = error.get("codexErrorInfo") if isinstance(error, dict) else None
                self._last_terminal_error = code if isinstance(code, str) else None
                self._last_terminal_error_payload = (
                    sanitize_codex_diagnostics(error)
                    if isinstance(error, dict)
                    else None
                )
            return status
        return None

    def _interrupt_or_raise(
        self,
        process: subprocess.Popen[bytes],
        thread_id: str,
        turn_id: str,
        request_id: int,
        message: str,
        *,
        deadline: bool = False,
        cancelled: bool = False,
    ) -> str:
        status = self._interrupt_active_turn(process, thread_id, turn_id, request_id)
        if status == "interrupted":
            raise CodexInterruptedError(
                message, deadline=deadline, cancelled=cancelled
            )
        if status in {"completed", "failed"}:
            if status == "failed":
                self._stop_process_and_drain(process)
                safe_terminal_error = (
                    sanitize_codex_diagnostics(self._last_terminal_error)
                    if self._last_terminal_error
                    else None
                )
                failed_detail = (
                    f": {safe_terminal_error}"
                    if isinstance(safe_terminal_error, str)
                    else ""
                )
                raise CodexTurnFailed(
                    f"{message}; Codex reported failed{failed_detail}",
                    diagnostics=self._diagnostics_snapshot(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        turn_status=status,
                    ),
                )
            return status
        raise CodexProtocolError(f"{message}; Codex stop is unconfirmed")

    def _diagnostics_snapshot(
        self,
        *,
        thread_id: str | None = None,
        turn_id: str | None = None,
        turn_status: str | None = None,
    ) -> dict[str, Any]:
        stderr = self._stderr_buffer
        return cast(
            dict[str, Any],
            sanitize_codex_diagnostics(
            {
                **self._diagnostic_context,
                "threadId": thread_id,
                "turnId": turn_id,
                "turnStatus": turn_status,
                "turnError": self._last_terminal_error_payload,
                "events": list(self._recent_events),
                "stderr": (
                    stderr.getvalue().decode("utf-8", errors="replace")
                    if stderr is not None
                    else ""
                ),
                "stderrTruncated": stderr.truncated if stderr is not None else False,
            }
            ),
        )

    def _stop_process_and_drain(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self._stderr_reader is not None:
            self._stderr_reader.join(timeout=2)

    @staticmethod
    def _send(
        process: subprocess.Popen[bytes],
        request_id: int,
        method: str,
        params: dict[str, Any],
    ) -> None:
        assert process.stdin
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    @staticmethod
    def _send_notification(
        process: subprocess.Popen[bytes], method: str, params: dict[str, Any]
    ) -> None:
        assert process.stdin
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    @staticmethod
    def _send_server_response(
        process: subprocess.Popen[bytes], request_id: Any, result: dict[str, Any]
    ) -> None:
        assert process.stdin
        message = {"jsonrpc": "2.0", "id": request_id, "result": result}
        try:
            process.stdin.write((json.dumps(message) + "\n").encode())
            process.stdin.flush()
        except OSError as exc:
            raise CodexProtocolError(
                "Codex response channel closed before write completed"
            ) from exc

    def _read_response(
        self,
        process: subprocess.Popen[bytes],
        request_id: int,
        on_server_request: Callable[[str, str, dict[str, Any]], dict[str, Any]]
        | None = None,
        on_server_response: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        deadline: float | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        response_deadline = (
            deadline
            if deadline is not None
            else time.monotonic() + self.timeout_seconds
        )
        while True:
            if (
                should_stop is not None
                and should_stop()
                and request_id != 3
            ):
                raise CodexRunCancelled()
            remaining = response_deadline - time.monotonic()
            if remaining <= 0:
                raise CodexProtocolError("Codex App Server timed out")
            try:
                message = self._read_message(
                    process,
                    min(0.1, remaining),
                    include_pending=False,
                )
            except CodexProtocolError as exc:
                if "timed out" in str(exc) and time.monotonic() < response_deadline:
                    continue
                raise
            if "method" in message and "id" in message:
                if on_server_request is None:
                    raise CodexProtocolError(
                        f"unhandled Codex server request: {message['method']}"
                    )
                params = message.get("params")
                if not isinstance(params, dict):
                    raise CodexProtocolError(
                        "Codex server request params must be an object"
                    )
                try:
                    response = on_server_request(
                        str(message["id"]), str(message["method"]), params
                    )
                    if should_stop is not None and should_stop():
                        raise CodexRunCancelled()
                except CodexStopRequested as exc:
                    self._send_server_error(process, message["id"], str(exc))
                    if request_id != 3:
                        raise CodexInterruptedError(
                            str(exc),
                            deadline=exc.deadline,
                            cancelled=exc.cancelled,
                        ) from exc
                    thread_id = params.get("threadId")
                    turn_id = params.get("turnId")
                    if not isinstance(thread_id, str) or not isinstance(turn_id, str):
                        raise CodexProtocolError(
                            "Codex turn/start stop request has no native turn identity"
                        ) from exc
                    stop_status = self._interrupt_or_raise(
                        process,
                        thread_id,
                        turn_id,
                        request_id + 1,
                        str(exc),
                        deadline=exc.deadline,
                        cancelled=exc.cancelled,
                    )
                    if request_id == 3 and stop_status != "interrupted":
                        raise CodexProtocolError(
                            f"Codex turn/start ended with status={stop_status}"
                        ) from exc
                self._send_server_response(process, message["id"], response)
                if on_server_response is not None:
                    on_server_response(str(message["id"]), response)
                continue
            if message.get("id") != request_id:
                self._pending_messages.append(message)
                continue
            if "error" in message:
                raise CodexProtocolError("Codex request failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexProtocolError("Codex response result must be an object")
            return result

    @staticmethod
    def _send_server_error(
        process: subprocess.Popen[bytes], request_id: Any, message: str
    ) -> None:
        assert process.stdin
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32800, "message": message},
        }
        try:
            process.stdin.write((json.dumps(response) + "\n").encode())
            process.stdin.flush()
        except OSError as exc:
            raise CodexProtocolError(
                "Codex response channel closed before error delivery"
            ) from exc

    def _read_message(
        self,
        process: subprocess.Popen[bytes],
        timeout: float,
        *,
        include_pending: bool = True,
    ) -> dict[str, Any]:
        if include_pending and self._pending_messages:
            return self._pending_messages.popleft()
        assert process.stdout
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            deadline = time.monotonic() + max(0.01, timeout)
            while b"\n" not in self._read_buffer:
                if len(self._read_buffer) > _MAX_PROTOCOL_LINE_BYTES:
                    raise CodexProtocolError(
                        "Codex App Server protocol line exceeded 1 MiB"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise CodexProtocolError("Codex App Server timed out")
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    raise CodexProtocolError("Codex App Server closed the connection")
                self._read_buffer.extend(chunk)
                newline_at = self._read_buffer.find(b"\n")
                if newline_at > _MAX_PROTOCOL_LINE_BYTES:
                    raise CodexProtocolError(
                        "Codex App Server protocol line exceeded 1 MiB"
                    )
        finally:
            selector.close()
        line, _, rest = self._read_buffer.partition(b"\n")
        self._read_buffer = bytearray(rest)
        try:
            message = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CodexProtocolError("Codex emitted invalid JSON") from exc
        if not isinstance(message, dict):
            raise CodexProtocolError("Codex message must be an object")
        return message
