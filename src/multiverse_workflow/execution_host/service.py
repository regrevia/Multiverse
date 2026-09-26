from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from multiverse_workflow.execution_host.backend import ProcessBackend, ProcessConfig
from multiverse_workflow.execution_host.store import (
    HostConflict,
    HostStore,
    canonical,
    digest,
    strict_json,
)

MAX_REQUEST_BYTES = 262_144


class ExecutionHost:
    def __init__(
        self,
        database: Path,
        root: Path,
        config: ProcessConfig,
        *,
        hook: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.store = HostStore(database)
        try:
            self.backend = ProcessBackend(self.store, root, config, hook)
        except OSError:
            self.store.close()
            raise

    def close(self) -> None:
        self.backend.close()
        self.store.close()

    def descriptor(self) -> dict[str, Any]:
        return {
            "executorRef": self.config.executor_ref,
            "adapter": "http_job",
            "adapterVersion": "1.0.0",
            "executorVersion": "1.0.0",
            "contractVersion": "multiverse/v0.1",
            "capabilities": list(self.config.capabilities),
            "cancelMode": "best_effort",
            "submitDedup": "durable",
            "reconcileByKey": "strong",
            "retryOwner": "runtime",
            "observability": "boundary",
            "enforcement": "trusted_local",
        }

    def submit(self, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        required = {
            "protocolVersion",
            "dispatchKey",
            "effectKey",
            "runId",
            "scopeId",
            "invocationId",
            "attemptId",
            "attemptNo",
            "executorRef",
            "input",
            "inputDigest",
            "inputSchemaDigest",
            "outputSchemaDigest",
            "deadlineAt",
            "authorizationRef",
            "context",
            "traceContext",
        }
        if set(request) != required:
            raise ValueError("request fields do not match ExecutionRequest")
        if request["protocolVersion"] != "multiverse/v0.1":
            raise ValueError("unsupported protocol version")
        if request["executorRef"] != self.config.executor_ref:
            raise ValueError("executor is not installed")
        for name in (
            "dispatchKey",
            "effectKey",
            "runId",
            "scopeId",
            "invocationId",
            "attemptId",
            "deadlineAt",
            "authorizationRef",
        ):
            if not isinstance(request[name], str) or not 1 <= len(request[name]) <= 512:
                raise ValueError("invalid request identity")
        deadline = datetime.fromisoformat(request["deadlineAt"].replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            raise ValueError("deadline must be a timezone-aware timestamp")
        if type(request["attemptNo"]) is not int or request["attemptNo"] < 1:
            raise ValueError("invalid attempt number")
        for name in ("inputDigest", "inputSchemaDigest", "outputSchemaDigest"):
            if not isinstance(request[name], str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", request[name]
            ):
                raise ValueError("invalid request digest")
        if request["inputDigest"] != digest(canonical(request["input"]).encode()):
            raise ValueError("input digest mismatch")
        if not isinstance(request["context"], dict):
            raise ValueError("invalid context")
        row, created = self.store.submit(request)
        if created:
            self.backend.start(row["id"])
        return {"executionRef": row["id"], "status": "accepted"}, created


def create_server(
    host: ExecutionHost, *, address: str = "127.0.0.1", port: int = 0
) -> ThreadingHTTPServer:
    if not ipaddress.ip_address(address).is_loopback or ":" in address:
        raise ValueError("execution host requires an IPv4 loopback address")

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def handle(self) -> None:
            # An absolute read deadline covers slow headers as well as dripped bodies.
            self.read_deadline = time.monotonic() + 5
            timer = threading.Timer(5, self.expire_read)
            timer.start()
            try:
                super().handle()
            finally:
                timer.cancel()

        def expire_read(self) -> None:
            try:
                self.connection.shutdown(socket.SHUT_RD)
            except OSError:
                pass

        def local_request(self) -> bool:
            authority = f"{address}:{cast(ThreadingHTTPServer, self.server).server_port}"
            if self.headers.get_all("Host", []) != [authority] or self.headers.get_all(
                "Origin", []
            ) not in ([], [f"http://{authority}"]):
                self.respond(403, {"error": "loopback host/origin required"})
                return False
            return True

        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self, status: int, document: dict[str, Any] | bytes) -> None:
            is_bytes = isinstance(document, bytes)
            body = document if isinstance(document, bytes) else canonical(document).encode()
            self.send_response(status)
            self.send_header(
                "Content-Type", "application/octet-stream" if is_bytes else "application/json"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:  # noqa: N802
            if not self.local_request():
                return
            try:
                parsed = urlsplit(self.path)
                path = parsed.path
                if path == "/v1/descriptor":
                    self.respond(200, host.descriptor())
                    return
                if path == "/v1/executions/lookup":
                    keys = parse_qs(parsed.query).get("dispatchKey", [])
                    if len(keys) != 1 or not keys[0]:
                        raise ValueError("dispatchKey is required")
                    self.respond(200, host.store.lookup(keys[0]))
                    return
                parts = path.strip("/").split("/")
                if len(parts) >= 3 and parts[:2] == ["v1", "executions"]:
                    ref = parts[2]
                    row = host.store.get(ref)
                    if len(parts) == 3:
                        self.respond(200, json.loads(row["observation_json"]))
                        return
                    if parts[3:] == ["artifacts"]:
                        self.respond(
                            200,
                            {
                                "executionRef": ref,
                                "namespace": host.config.namespace,
                                "artifacts": json.loads(row["artifacts_json"]),
                            },
                        )
                        return
                    if len(parts) == 6 and parts[3] == "artifacts" and parts[5] == "content":
                        self.respond(200, host.backend.artifact_bytes(ref, parts[4]))
                        return
                self.respond(404, {"error": "not found"})
            except KeyError:
                self.respond(404, {"error": "not found"})
            except ValueError:
                self.respond(400, {"error": "invalid request or artifact"})

        def do_POST(self) -> None:  # noqa: N802
            if not self.local_request():
                return
            content_types = self.headers.get_all("Content-Type", [])
            if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != (
                "application/json"
            ):
                self.respond(415, {"error": "application/json required"})
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("transfer encoding is not supported")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1:
                    raise ValueError("one Content-Length is required")
                length = int(lengths[0])
                if not 0 < length <= MAX_REQUEST_BYTES:
                    self.respond(413, {"error": "request exceeds limit"})
                    return
                body = bytearray()
                while len(body) < length:
                    remaining = self.read_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("request read deadline")
                    self.connection.settimeout(remaining)
                    chunk = self.rfile.read1(min(8192, length - len(body)))
                    if not chunk:
                        raise TimeoutError("incomplete request body")
                    body.extend(chunk)
                payload = strict_json(bytes(body))
                if not isinstance(payload, dict):
                    raise ValueError("request must be an object")
                if self.path == "/v1/executions":
                    response, created = host.submit(payload)
                    host.backend.checkpoint("before_submit_response", response["executionRef"])
                    self.respond(201 if created else 200, response)
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["v1", "executions"] and parts[3] == "cancel":
                    if (
                        set(payload) != {"commandId"}
                        or not isinstance(payload["commandId"], str)
                        or not 1 <= len(payload["commandId"]) <= 512
                    ):
                        raise ValueError("invalid cancellation command")
                    host.store.cancel(parts[2], payload["commandId"])
                    host.backend.cancel(parts[2])
                    self.respond(202, {"status": "accepted"})
                    return
                self.respond(404, {"error": "not found"})
            except TimeoutError:
                self.respond(408, {"error": "request read deadline"})
            except HostConflict:
                self.respond(409, {"error": "request conflicts with persisted identity"})
            except KeyError:
                self.respond(404, {"error": "not found"})
            except (ValueError, UnicodeError, RecursionError):
                self.respond(400, {"error": "invalid execution request"})

    return ThreadingHTTPServer((address, port), Handler)
