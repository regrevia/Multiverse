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


class ClaudeProtocolError(RuntimeError):
    """Claude Code did not produce a usable structured result."""


class ClaudeProcessError(ClaudeProtocolError):
    """Claude Code exited with a known process failure."""


class ClaudeVersionMismatchError(ClaudeProcessError):
    """The configured Claude executable is not the declared version."""


class ClaudeOutputLimitError(ClaudeProtocolError):
    """Claude stdout exceeded the configured bound."""


class ClaudeCancelledError(ClaudeProtocolError):
    """The configured Claude process was cooperatively stopped."""


class ClaudeDeadlineError(ClaudeProtocolError):
    """Claude stopped after the configured deadline."""


@dataclass(frozen=True)
class ClaudeResult:
    output: dict[str, Any]
    observation: dict[str, Any]


class ClaudeCli:
    """One-shot Claude Code adapter using its documented print JSON envelope."""

    def __init__(
        self,
        *,
        command: tuple[str, ...] = (
            "claude",
            "--print",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--tools",
            "",
        ),
        model: str | None = None,
        timeout_seconds: float = 180.0,
        max_output_bytes: int = 262144,
        permission_mode: str = "dontAsk",
        expected_version: str | None = None,
        output_format: str = "json",
    ) -> None:
        if not command or any(not isinstance(item, str) for item in command):
            raise ValueError("claude command must be a non-empty argument array")
        if timeout_seconds <= 0:
            raise ValueError("claude timeoutSeconds must be positive")
        if max_output_bytes < 1:
            raise ValueError("claude maxOutputBytes must be positive")
        if permission_mode not in {"default", "dontAsk", "plan", "acceptEdits"}:
            raise ValueError("unsupported Claude permissionMode")
        forbidden = {
            "--mcp-config",
            "--plugin-dir",
            "--plugin-url",
            "--dangerously-skip-permissions",
            "--allow-dangerously-skip-permissions",
            "--add-dir",
            "--worktree",
            "--settings",
            "--chrome",
            "--ide",
        }
        if any(
            item in forbidden
            or any(item.startswith(f"{flag}=") for flag in forbidden)
            for item in command
        ):
            raise ValueError("Claude command contains a forbidden extension or permission flag")
        if output_format not in {"json", "stream-json"}:
            raise ValueError("unsupported Claude outputFormat")
        self.command = self._with_options(command, model, permission_mode, output_format)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.expected_version = expected_version
        self.output_format = output_format

    @staticmethod
    def _with_options(
        command: tuple[str, ...],
        model: str | None,
        permission_mode: str,
        output_format: str = "json",
    ) -> tuple[str, ...]:
        args: list[str] = []
        managed_with_value = {
            "--output-format",
            "--tools",
            "--permission-mode",
        }
        managed_flags = {"--print", "--no-session-persistence", *managed_with_value}
        index = 0
        while index < len(command):
            item = command[index]
            if item in managed_with_value:
                index += 2
                continue
            if any(item.startswith(f"{flag}=") for flag in managed_with_value):
                index += 1
                continue
            if item in managed_flags or any(
                item.startswith(f"{flag}=") for flag in managed_flags
            ):
                index += 1
                continue
            args.append(item)
            index += 1
        args.extend(
            [
                "--print",
                "--output-format",
                output_format,
                "--no-session-persistence",
                "--tools",
                "",
                "--permission-mode",
                permission_mode,
            ]
        )
        if model and "--model" not in args:
            args.extend(["--model", model])
        if "--permission-mode" not in args:
            args.extend(["--permission-mode", permission_mode])
        return tuple(args)

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        home_dir: Path,
        output_schema: dict[str, Any],
        should_stop: Any = None,
    ) -> ClaudeResult:
        if not prompt.strip():
            raise ValueError("claude prompt must not be empty")
        deadline = time.monotonic() + self.timeout_seconds
        if self.expected_version:
            if Path(self.command[0]).name != "claude":
                raise ClaudeVersionMismatchError(
                    "Claude expectedVersion cannot be verified for a wrapper command"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClaudeDeadlineError("Claude deadline elapsed before version check")
            try:
                version = subprocess.run(
                    (self.command[0], "--version"),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=remaining,
                ).stdout.strip()
            except subprocess.TimeoutExpired as exc:
                raise ClaudeDeadlineError("Claude version check timed out") from exc
            actual_version = version.split(maxsplit=1)[0]
            if actual_version != self.expected_version:
                raise ClaudeVersionMismatchError(
                    f"Claude version mismatch: expected {self.expected_version}, got {version}"
                )
        if time.monotonic() >= deadline:
            raise ClaudeDeadlineError("Claude deadline elapsed before process start")
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
            if time.monotonic() >= deadline:
                if not self._stop_process(process):
                    raise ClaudeProtocolError("Claude startup stop is unconfirmed")
                raise ClaudeDeadlineError("Claude deadline elapsed during process start")
            stdout, stderr = self._communicate(
                process, prompt.encode("utf-8"), deadline, should_stop
            )
            stdout_text = bytes(stdout).decode("utf-8", errors="replace")
            stderr_text = bytes(stderr).decode("utf-8", errors="replace")
            if process.returncode != 0:
                detail = stderr_text.strip()
                try:
                    envelope_error = json.loads(stdout_text)
                except json.JSONDecodeError:
                    envelope_error = None
                if isinstance(envelope_error, dict) and isinstance(
                    envelope_error.get("result"), str
                ):
                    detail = envelope_error["result"]
                suffix = f"exit code {process.returncode}"
                if detail:
                    suffix = f"{suffix}: {detail}"
                raise ClaudeProcessError(f"Claude process failed: {suffix}")
            if self.output_format == "stream-json":
                envelope = self._parse_stream(stdout_text)
            else:
                try:
                    envelope = json.loads(stdout_text)
                except json.JSONDecodeError as exc:
                    raise ClaudeProtocolError("Claude result was not structured JSON") from exc
            if not isinstance(envelope, dict):
                raise ClaudeProtocolError("Claude result envelope must be an object")
            if envelope.get("type") != "result":
                raise ClaudeProtocolError("Claude result envelope has unexpected type")
            if envelope.get("is_error") is True or envelope.get("subtype") not in {
                "success",
                None,
            }:
                raise ClaudeProcessError("Claude result reported a rejected result")
            raw_result = envelope.get("result")
            if isinstance(raw_result, str):
                try:
                    output = json.loads(raw_result)
                except json.JSONDecodeError as exc:
                    raise ClaudeProtocolError("Claude result payload was not JSON") from exc
            else:
                output = raw_result
            if not isinstance(output, dict):
                raise ClaudeProtocolError("Claude result payload must be an object")
            return ClaudeResult(
                output=output,
                observation={
                    "provider": "claude",
                    "protocol": self.output_format,
                    "sessionId": envelope.get("session_id"),
                    "status": "completed",
                    "outputSchema": output_schema,
                },
            )
        finally:
            if process.poll() is None or self._group_alive(process.pid):
                self._stop_process(process)

    @staticmethod
    def _stop_process(process: subprocess.Popen[bytes]) -> bool:
        if process.poll() is not None:
            if not ClaudeCli._group_alive(process.pid):
                return True
            return ClaudeCli._kill_group(process.pid)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        try:
            process.wait(timeout=1)
            return not ClaudeCli._group_alive(process.pid)
        except subprocess.TimeoutExpired:
            pass
        return ClaudeCli._kill_group(process.pid, process=process)

    @staticmethod
    def _kill_group(
        process_group: int,
        *,
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
        return not ClaudeCli._group_alive(process_group)

    @staticmethod
    def _group_alive(process_group: int) -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _communicate(
        self,
        process: subprocess.Popen[bytes],
        payload: bytes,
        deadline: float,
        should_stop: Any,
    ) -> tuple[bytes, bytes]:
        assert process.stdin and process.stdout and process.stderr
        streams = (process.stdin, process.stdout, process.stderr)
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdin, selectors.EVENT_WRITE)
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        offset = 0
        stdout = bytearray()
        stderr = bytearray()
        leader_exit_at: float | None = None
        try:
            while selector.get_map() or process.poll() is None:
                now = time.monotonic()
                if should_stop is not None and should_stop():
                    if not self._stop_process(process):
                        raise ClaudeProtocolError("Claude stop is unconfirmed")
                    raise ClaudeCancelledError("Claude process was cooperatively stopped")
                if now >= deadline:
                    if not self._stop_process(process):
                        raise ClaudeProtocolError("Claude timeout stop is unconfirmed")
                    raise ClaudeDeadlineError("Claude process timed out")
                if process.poll() is not None and leader_exit_at is None:
                    leader_exit_at = now
                drain_deadline = (
                    min(deadline, leader_exit_at + 1.0)
                    if leader_exit_at is not None
                    else deadline
                )
                if leader_exit_at is not None and now >= drain_deadline:
                    if self._group_alive(process.pid):
                        self._kill_group(process.pid)
                    raise ClaudeProtocolError(
                        "Claude leader exited while its process group remained active"
                    )
                for key, _ in selector.select(
                    min(0.05, max(0.0, drain_deadline - now))
                ):
                    if key.fileobj is process.stdin:
                        if offset < len(payload):
                            try:
                                offset += os.write(
                                    process.stdin.fileno(), payload[offset:]
                                )
                            except BrokenPipeError:
                                offset = len(payload)
                        if offset == len(payload):
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if key.fileobj is process.stdout:
                            stdout.extend(chunk)
                            if len(stdout) > self.max_output_bytes:
                                if not self._stop_process(process):
                                    raise ClaudeProtocolError(
                                        "Claude output stop is unconfirmed"
                                    )
                                raise ClaudeOutputLimitError(
                                    "Claude output exceeded maxOutputBytes"
                                )
                        else:
                            stderr.extend(chunk[: max(0, 65536 - len(stderr))])
            if self._group_alive(process.pid):
                self._kill_group(process.pid)
                raise ClaudeProtocolError(
                    "Claude process group remained active after leader exit"
                )
            return bytes(stdout), bytes(stderr)
        finally:
            selector.close()

    @staticmethod
    def _parse_stream(raw: str) -> dict[str, Any]:
        fragments: list[str] = []
        result: dict[str, Any] | None = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ClaudeProtocolError("Claude stream emitted invalid JSON") from exc
            if not isinstance(event, dict):
                raise ClaudeProtocolError("Claude stream event must be an object")
            event_type = event.get("type")
            if event_type in {"request", "permission_request", "tool_use"}:
                raise ClaudeProtocolError("Claude stream request requires unsupported interaction")
            if event_type in {"assistant", "message_delta", "content_block_delta"}:
                text = event.get("text")
                if isinstance(text, str):
                    fragments.append(text)
                delta = event.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                    fragments.append(delta["text"])
                message = event.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and isinstance(block.get("text"), str):
                                fragments.append(block["text"])
                continue
            if event_type == "result":
                if event.get("is_error") is True or event.get("subtype") not in {
                    "success",
                    None,
                }:
                    raise ClaudeProcessError("Claude stream reported a rejected result")
                result = event
                continue
            if event_type in {"system", "user", "tool_result", "rate_limit_event"}:
                continue
            raise ClaudeProtocolError(f"Claude stream emitted unsupported event type: {event_type}")
        if result is None:
            raise ClaudeProtocolError("Claude stream ended without a result event")
        raw_result = result.get("result")
        if isinstance(raw_result, str):
            try:
                output = json.loads(raw_result)
            except json.JSONDecodeError as exc:
                if fragments:
                    try:
                        output = json.loads("".join(fragments))
                    except json.JSONDecodeError:
                        raise ClaudeProtocolError(
                            "Claude stream result payload was not JSON"
                        ) from exc
                else:
                    raise ClaudeProtocolError("Claude stream result payload was not JSON") from exc
        elif raw_result is None and fragments:
            try:
                output = json.loads("".join(fragments))
            except json.JSONDecodeError as exc:
                raise ClaudeProtocolError(
                    "Claude stream result payload was not JSON"
                ) from exc
        else:
            output = raw_result
        if not isinstance(output, dict):
            raise ClaudeProtocolError("Claude stream result payload must be an object")
        return result | {"result": output}
