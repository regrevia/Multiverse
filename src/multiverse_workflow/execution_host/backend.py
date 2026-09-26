from __future__ import annotations

import json
import os
import selectors
import signal
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from multiverse_workflow.execution_host.store import HostStore, canonical, digest, strict_json

MAX_ARTIFACT_BYTES = 1_048_576
MAX_TOTAL_ARTIFACT_BYTES = 4_194_304
MAX_ARTIFACTS = 8


@dataclass(frozen=True)
class ProcessConfig:
    command: tuple[str, ...]
    executor_ref: str = "example.execution-host.v1"
    namespace: str = "local"
    max_output_bytes: int = 262_144
    max_log_bytes: int = 65_536
    timeout_seconds: float = 30.0
    capabilities: tuple[str, ...] = ("content.produce@1",)

    def __post_init__(self) -> None:
        if not self.command or any(not isinstance(s, str) or not s for s in self.command):
            raise ValueError("operator command must be a non-empty argument array")
        if not Path(self.command[0]).is_absolute():
            raise ValueError("operator executable must be absolute")
        if not 1 <= self.max_output_bytes <= 1_048_576:
            raise ValueError("output limit must be between 1 and 1048576")
        if not 1 <= self.max_log_bytes <= 1_048_576:
            raise ValueError("log limit must be between 1 and 1048576")
        if not 0 < self.timeout_seconds <= 3600:
            raise ValueError("timeout must be between 0 and 3600 seconds")


class ProcessBackend:
    """Owned POSIX process groups, bounded pipes, no restart/retry authority."""

    def __init__(
        self,
        store: HostStore,
        root: Path,
        config: ProcessConfig,
        hook: Callable[[str, str], None] | None = None,
    ) -> None:
        self.store, self.config = store, config
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.hook = hook
        self._mutex = threading.RLock()
        self._closing = threading.Event()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._threads: list[threading.Thread] = []

    def checkpoint(self, stage: str, ref: str) -> None:
        if self.hook:
            self.hook(stage, ref)

    def start(self, ref: str) -> None:
        thread = threading.Thread(target=self._run, args=(ref,), daemon=True)
        with self._mutex:
            self._threads.append(thread)
        thread.start()

    def query(self, ref: str) -> dict[str, Any]:
        return json.loads(self.store.get(ref)["observation_json"])  # type: ignore[no-any-return]

    def events(self, ref: str, after: int = 0) -> list[dict[str, Any]]:
        return self.store.events(ref, after)

    def artifacts(self, ref: str) -> list[dict[str, Any]]:
        return json.loads(self.store.get(ref)["artifacts_json"])  # type: ignore[no-any-return]

    def cancel(self, ref: str) -> None:
        # Only unreaped Popen objects created by this live host carry authority.
        with self._mutex:
            process = self._processes.get(ref)
            if process is not None:
                self._signal(process, signal.SIGTERM)

    @staticmethod
    def _signal(process: subprocess.Popen[bytes], sig: int) -> None:
        # poll()/wait() must not reap the leader before group signalling is finished.
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        self._closing.set()
        with self._mutex:
            for process in self._processes.values():
                self._signal(process, signal.SIGKILL)
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=5)

    def _run(self, ref: str) -> None:
        process: subprocess.Popen[bytes] | None = None
        final_status = "failed"
        error: dict[str, Any] | None = None
        output: Any = None
        artifacts: list[dict[str, Any]] = []
        work = self.root / ref / "work"
        work.mkdir(parents=True)
        try:
            self.checkpoint("after_intent", ref)
            self.store.launch_intent(ref)
            self.checkpoint("before_launch", ref)
            request = json.loads(self.store.get(ref)["request_json"])
            with self._mutex:
                if self._closing.is_set():
                    raise OutputLimit("PROCESS_HOST_STOPPED")
                if self.store.get(ref)["cancel_requested"]:
                    final_status = "cancelled"
                    error = {"code": "PROCESS_CANCELLED", "message": "Cancelled before launch"}
                    return
                requested_deadline = datetime.fromisoformat(
                    request["deadlineAt"].replace("Z", "+00:00")
                )
                if requested_deadline <= datetime.now(UTC):
                    raise OutputLimit("PROCESS_DEADLINE_EXCEEDED")
                process = subprocess.Popen(
                    self.config.command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=work,
                    start_new_session=True,
                    close_fds=True,
                    env={"PATH": os.defpath, "LANG": "C.UTF-8", "HOME": str(work)},
                )
                self._processes[ref] = process
            self.checkpoint("after_launch", ref)
            self.store.associate(
                ref,
                {
                    "pid": process.pid,
                    "processGroup": process.pid,
                    "bootIdentity": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                    "startTime": Path(f"/proc/{process.pid}/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()[19],
                    "workspaceRef": ref,
                    "logRef": ref + "/stderr.log",
                },
            )
            encoded = (canonical(request) + "\n").encode()
            deadline = datetime.fromisoformat(request["deadlineAt"].replace("Z", "+00:00"))
            remaining = max(0.0, (deadline - datetime.now(UTC)).total_seconds())
            result = self._communicate(ref, process, encoded, remaining)
            self.checkpoint("before_result", ref)
            if self.store.get(ref)["cancel_requested"]:
                final_status = "cancelled"
                error = {"code": "PROCESS_CANCELLED", "message": "Owned process group signalled"}
            elif process.returncode != 0:
                error = {
                    "code": "PROCESS_EXIT",
                    "message": "Process returned nonzero exit status",
                    "exitCode": process.returncode,
                }
            else:
                document = strict_json(result)
                if not isinstance(document, dict) or set(document) - {"output", "artifacts"}:
                    raise ValueError("result must contain output and optional artifacts")
                output = document["output"]
                if not isinstance(output, dict) or output.get("artifact_refs", []) != []:
                    raise ValueError("result output must be an object without artifact references")
                artifacts = self._artifacts(ref, document.get("artifacts", []), work)
                final_status = "succeeded"
        except (ValueError, KeyError, UnicodeError, OSError, RecursionError) as exc:
            error = {"code": "PROCESS_OUTPUT_INVALID", "message": type(exc).__name__}
        except OutputLimit as exc:
            error = {"code": exc.code, "message": "Execution exceeded its configured boundary"}
        finally:
            if process is not None:
                with self._mutex:
                    # Kill remaining owned group before reaping/releasing its leader identity.
                    if process.returncode is None:
                        self._signal(process, signal.SIGKILL)
                        process.wait(timeout=5)
                    self._processes.pop(ref, None)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
            self.store.update(
                ref, final_status, final=True, output=output, error=error, artifacts=artifacts
            )
            with self._mutex:
                self._threads.remove(threading.current_thread())

    def _communicate(
        self, ref: str, process: subprocess.Popen[bytes], payload: bytes, remaining: float
    ) -> bytes:
        assert process.stdin and process.stdout and process.stderr
        selector = selectors.DefaultSelector()
        output = bytearray()
        log_bytes = 0
        deadline = time.monotonic() + min(self.config.timeout_seconds, remaining)
        cancel_deadline: float | None = None
        written = 0
        for stream, event in (
            (process.stdin, selectors.EVENT_WRITE),
            (process.stdout, selectors.EVENT_READ),
            (process.stderr, selectors.EVENT_READ),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, event)
        try:
            with (self.root / ref / "stderr.log").open("wb") as log:
                while selector.get_map():
                    if self._closing.is_set():
                        raise OutputLimit("PROCESS_HOST_STOPPED")
                    now = time.monotonic()
                    if self.store.get(ref)["cancel_requested"]:
                        if cancel_deadline is None:
                            self._signal(process, signal.SIGTERM)
                            cancel_deadline = now + 0.25
                        if now >= cancel_deadline:
                            self._signal(process, signal.SIGKILL)
                    if now > deadline:
                        raise OutputLimit("PROCESS_TIMEOUT")
                    for key, _ in selector.select(0.05):
                        selected_stream = key.fileobj
                        if selected_stream is process.stdin:
                            try:
                                written += os.write(process.stdin.fileno(), payload[written:])
                            except BrokenPipeError:
                                written = len(payload)
                            if written == len(payload):
                                selector.unregister(process.stdin)
                                process.stdin.close()
                            continue
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(selected_stream)
                            continue
                        if selected_stream is process.stdout:
                            if len(output) + len(chunk) > self.config.max_output_bytes:
                                raise OutputLimit("PROCESS_OUTPUT_LIMIT")
                            output.extend(chunk)
                        else:
                            permitted = self.config.max_log_bytes - log_bytes
                            log.write(chunk[:permitted])
                            log_bytes += len(chunk)
                            if log_bytes > self.config.max_log_bytes:
                                raise OutputLimit("PROCESS_LOG_LIMIT")
            # EOF is not proof of exit: programs can close pipes and continue running.
            # WNOWAIT retains the leader identity until group signalling is complete.
            while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
                if self.store.get(ref)["cancel_requested"]:
                    self._signal(process, signal.SIGKILL)
                if time.monotonic() > deadline:
                    raise OutputLimit("PROCESS_TIMEOUT")
                time.sleep(0.01)
            with self._mutex:
                self._signal(process, signal.SIGKILL)
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
                self._processes.pop(ref, None)
            return bytes(output)
        finally:
            selector.close()

    def _artifacts(self, ref: str, declarations: Any, work: Path) -> list[dict[str, Any]]:
        if not isinstance(declarations, list) or len(declarations) > MAX_ARTIFACTS:
            raise ValueError("invalid artifact declarations")
        metadata = []
        total = 0
        blobs = self.root / ref / "blobs"
        blobs.mkdir()
        for item in declarations:
            if not isinstance(item, dict) or set(item) != {"path", "name", "mediaType"}:
                raise ValueError("invalid artifact declaration")
            name = item["path"]
            if (
                not isinstance(name, str)
                or not name
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
            ):
                raise ValueError("artifact path must be a filename in the task workspace")
            if any(
                not isinstance(item[key], str) or not 1 <= len(item[key]) <= 200
                for key in ("name", "mediaType")
            ):
                raise ValueError("invalid artifact metadata")
            fd = os.open(work / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("artifact must be a regular file")
                content = source.read(MAX_ARTIFACT_BYTES + 1)
                after = os.fstat(source.fileno())
            if len(content) > MAX_ARTIFACT_BYTES or (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError("artifact exceeds limit or changed while reading")
            total += len(content)
            if total > MAX_TOTAL_ARTIFACT_BYTES:
                raise ValueError("artifact total exceeds limit")
            artifact_id = "blob-" + uuid.uuid4().hex
            with (blobs / artifact_id).open("xb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            metadata.append(
                {
                    "artifactId": artifact_id,
                    "version": 1,
                    "executionRef": ref,
                    "namespace": self.config.namespace,
                    "name": item["name"],
                    "mediaType": item["mediaType"],
                    "sizeBytes": len(content),
                    "digest": digest(content),
                }
            )
        return metadata

    def artifact_bytes(self, ref: str, artifact_id: str) -> bytes:
        metadata = json.loads(self.store.get(ref)["artifacts_json"])
        item = next((item for item in metadata if item["artifactId"] == artifact_id), None)
        if item is None:
            raise KeyError(artifact_id)
        fd = os.open(self.root / ref / "blobs" / artifact_id, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            content = source.read(MAX_ARTIFACT_BYTES + 1)
        if len(content) != item["sizeBytes"] or digest(content) != item["digest"]:
            raise ValueError("stored artifact integrity failure")
        return content


class OutputLimit(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
