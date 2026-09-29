from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodexProtocolError(RuntimeError):
    """Codex App Server returned an unusable response or lost its process."""


class CodexInterruptedError(CodexProtocolError):
    """Codex acknowledged a cooperative turn interruption."""


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
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("codex command must be a non-empty argument array")
        if timeout_seconds <= 0:
            raise ValueError("codex timeoutSeconds must be positive")
        self.command, self.model, self.timeout_seconds = command, model, timeout_seconds
        self._read_buffer = bytearray()

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        home_dir: Path,
        output_schema: dict[str, Any],
        on_server_request: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None,
        on_server_response: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> CodexResult:
        process = subprocess.Popen(
            self.command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            env={
                "PATH": os.environ.get("PATH", os.defpath),
                "LANG": "C.UTF-8",
                "HOME": str(home_dir),
            },
        )
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
            self._read_response(process, request_id, on_server_request)
            self._send_notification(process, "initialized", {})
            request_id = 2
            self._send(
                process,
                request_id,
                "thread/start",
                {
                    "cwd": str(cwd),
                    "approvalPolicy": "never",
                    "sandbox": "workspace-write",
                    **({"model": self.model} if self.model else {}),
                },
            )
            thread_id = self._read_response(
                process, request_id, on_server_request
            ).get("thread", {}).get("id")
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexProtocolError("thread/start did not return a thread id")
            request_id = 3
            self._send(
                process,
                request_id,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "approvalPolicy": "never",
                    "outputSchema": output_schema,
                },
            )
            turn_id = self._read_response(
                process, request_id, on_server_request
            ).get("turn", {}).get("id")
            if not isinstance(turn_id, str) or not turn_id:
                raise CodexProtocolError("turn/start did not return a turn id")
            parts: list[str] = []
            deadline = time.monotonic() + self.timeout_seconds
            try:
                while time.monotonic() < deadline:
                    message = self._read_message(process, deadline - time.monotonic())
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
                        response = on_server_request(
                            str(message["id"]),
                            str(message["method"]),
                            params,
                        )
                        self._send_server_response(process, message["id"], response)
                        if on_server_response is not None:
                            on_server_response(str(message["id"]), response)
                        continue
                    if message.get("method") == "item/agentMessage/delta":
                        delta = message.get("params", {}).get("delta")
                        if isinstance(delta, str):
                            parts.append(delta)
                    if message.get("method") == "turn/completed":
                        turn = message.get("params", {}).get("turn", {})
                        if turn.get("status") != "completed":
                            raise CodexProtocolError("Codex turn did not complete")
                        if not parts:
                            for item in turn.get("items", []):
                                if item.get("type") == "agentMessage" and isinstance(
                                    item.get("text"), str
                                ):
                                    parts.append(item["text"])
                        break
                else:
                    raise CodexProtocolError("Codex App Server timed out")
            except CodexProtocolError as exc:
                if "timed out" not in str(exc):
                    raise
                if self._interrupt_active_turn(process, thread_id, turn_id, request_id + 1):
                    raise CodexInterruptedError("Codex turn interrupted after timeout") from exc
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

    @staticmethod
    def interrupt(
        *,
        command: tuple[str, ...],
        home_dir: Path,
        thread_id: str,
        turn_id: str,
        timeout_seconds: float = 10.0,
    ) -> bool:
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
                return turn.get("status") == "interrupted"
            return False
        except CodexProtocolError:
            return False
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
    ) -> bool:
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
                return False
            if message.get("method") != "turn/completed":
                continue
            turn = message.get("params", {}).get("turn", {})
            return turn.get("status") == "interrupted"
        return False

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
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

    def _read_response(
        self,
        process: subprocess.Popen[bytes],
        request_id: int,
        on_server_request: Callable[[str, str, dict[str, Any]], dict[str, Any]]
        | None = None,
        on_server_response: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        while True:
            message = self._read_message(process, self.timeout_seconds)
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
                response = on_server_request(
                    str(message["id"]), str(message["method"]), params
                )
                self._send_server_response(process, message["id"], response)
                if on_server_response is not None:
                    on_server_response(str(message["id"]), response)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexProtocolError("Codex request failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise CodexProtocolError("Codex response result must be an object")
            return result

    def _read_message(self, process: subprocess.Popen[bytes], timeout: float) -> dict[str, Any]:
        assert process.stdout
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            deadline = time.monotonic() + max(0.01, timeout)
            while b"\n" not in self._read_buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise CodexProtocolError("Codex App Server timed out")
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    raise CodexProtocolError("Codex App Server closed the connection")
                self._read_buffer.extend(chunk)
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
