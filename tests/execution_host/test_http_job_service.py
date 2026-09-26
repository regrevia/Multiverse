from __future__ import annotations

import concurrent.futures
import json
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from multiverse_workflow.execution_host.service import create_server
from multiverse_workflow.execution_host.store import HostConflict, HostStore

from .conftest import execution_request, wait_final

SUCCESS = 'import json; print(json.dumps({"output":{"text":"done","artifact_refs":[]}}))'


def test_real_process_durable_dedup_conflict_and_observation(host_factory, tmp_path):
    counter = tmp_path / "starts"
    host, client = host_factory(
        f"from pathlib import Path\nPath({str(counter)!r}).open('a').write('1')\n" + SUCCESS
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.submit(execution_request()), range(8)))
    ref = responses[0]["executionRef"]
    assert {response["executionRef"] for response in responses} == {ref}
    final = wait_final(client, ref)
    assert final["status"] == "succeeded"
    assert client.observe(ref) == final
    assert counter.read_text() == "1"
    assert client.lookup("dispatch-1")["executionRef"] == ref
    assert client.lookup("absent")["status"] == "not_created"
    changed = execution_request()
    changed["authorizationRef"] = "different"
    with pytest.raises(HTTPError) as caught:
        urlopen(
            Request(
                client.base_url + "/v1/executions",
                data=json.dumps(changed).encode(),
                headers={"Content-Type": "application/json"},
            )
        )
    assert caught.value.code == 409
    assert counter.read_text() == "1"
    with pytest.raises(HostConflict):
        HostStore(tmp_path / "0" / "host.db")
    with pytest.raises(ValueError, match="loopback"):
        create_server(host, address="0.0.0.0")


def test_dropped_submit_response_recovers_original_real_execution(host_factory, tmp_path):
    reached = threading.Event()
    release = threading.Event()

    def hook(stage, ref):
        if stage == "before_submit_response":
            reached.set()
            assert release.wait(5)

    counter = tmp_path / "starts"
    _, client = host_factory(
        f"from pathlib import Path\nPath({str(counter)!r}).write_text('1')\n" + SUCCESS, hook=hook
    )
    address = client.base_url.removeprefix("http://").split(":")
    connection = socket.create_connection((address[0], int(address[1])))
    body = json.dumps(execution_request()).encode()
    connection.sendall(
        b"POST /v1/executions HTTP/1.0\r\nHost: "
        + client.base_url.removeprefix("http://").encode()
        + b"\r\nContent-Type: application/json\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    assert reached.wait(5)
    connection.shutdown(socket.SHUT_RDWR)
    connection.close()
    release.set()
    ref = client.lookup("dispatch-1")["executionRef"]
    assert wait_final(client, ref)["status"] == "succeeded"
    assert client.submit(execution_request())["executionRef"] == ref
    assert counter.read_text() == "1"


@pytest.mark.parametrize(
    ("script", "options", "code"),
    [
        ("print('x'*100000)", {"max_output_bytes": 1024}, "PROCESS_OUTPUT_LIMIT"),
        ("import sys; sys.stderr.write('x'*100000)", {"max_log_bytes": 1024}, "PROCESS_LOG_LIMIT"),
        ("import time; time.sleep(10)", {"timeout_seconds": 0.1}, "PROCESS_TIMEOUT"),
        ("print('not json')", {}, "PROCESS_OUTPUT_INVALID"),
        ("print('{}{}')", {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{},"output":{}}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{"x":NaN}}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{"x":Infinity}}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{"x":1e999}}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{"x":-1e999}}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ('print(\'{"output":{},"unexpected":1}\')', {}, "PROCESS_OUTPUT_INVALID"),
        ("print('{\"output\":[]}')", {}, "PROCESS_OUTPUT_INVALID"),
    ],
)
def test_real_process_output_boundaries(host_factory, script, options, code):
    host, client = host_factory(script, **options)
    ref = client.submit(execution_request())["executionRef"]
    final = wait_final(client, ref)
    assert final["status"] == "failed"
    assert final["error"]["code"] == code
    assert (host.backend.root / ref / "stderr.log").stat().st_size <= host.config.max_log_bytes


def test_real_cancel_only_owned_process_group_and_persisted_receipt(host_factory, tmp_path):
    marker = tmp_path / "child.pid"
    script = f"""import subprocess,sys,time,json,signal
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
def stop(sig, frame):
    child.wait(timeout=2)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
Path({str(marker)!r}).write_text(str(child.pid))
try:
    time.sleep(60)
finally:
    child.wait()
"""
    host, client = host_factory(script)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        ref = client.submit(execution_request())["executionRef"]
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        assert client.cancel(ref, "cancel-1")["status"] == "accepted"
        assert client.cancel(ref, "cancel-1")["status"] == "accepted"
        final = wait_final(client, ref)
        assert final["status"] == "cancelled"
        assert final["effectState"] == "possible"
        assert bystander.poll() is None
        child_stat = Path(f"/proc/{marker.read_text()}/stat")
        assert not child_stat.exists() or child_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        assert client.describe()["cancelMode"] == "best_effort"
        assert host.store.get(ref)["cancel_requested"] == 1
        assert client.observe(ref) == final
    finally:
        bystander.kill()
        bystander.wait()


def test_environment_does_not_inherit_secrets(host_factory, monkeypatch):
    monkeypatch.setenv("W02_SENTINEL_SECRET", "must-not-be-inherited")
    _, client = host_factory(
        'import os,json; print(json.dumps({"output":{"present":'
        '"W02_SENTINEL_SECRET" in os.environ}}))'
    )
    ref = client.submit(execution_request())["executionRef"]
    assert wait_final(client, ref)["output"] == {"present": False}


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"x":-1e999}']
)
def test_http_rejects_ambiguous_or_nonfinite_json(host_factory, raw):
    _, client = host_factory(SUCCESS)
    with pytest.raises(HTTPError) as caught:
        urlopen(
            Request(
                client.base_url + "/v1/executions",
                data=raw,
                headers={"Content-Type": "application/json"},
            )
        )
    assert caught.value.code == 400
    assert client.lookup("dispatch-1")["status"] == "not_created"


def test_cancel_before_launch_does_not_start_program(host_factory, tmp_path):
    barrier, release = threading.Event(), threading.Event()

    def hook(stage, ref):
        if stage == "after_intent":
            barrier.set()
            assert release.wait(5)

    marker = tmp_path / "must-not-start"
    _, client = host_factory(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n" + SUCCESS, hook=hook
    )
    ref = client.submit(execution_request())["executionRef"]
    assert barrier.wait(5)
    client.cancel(ref, "cancel-before-launch")
    release.set()
    assert wait_final(client, ref)["status"] == "cancelled"
    assert not marker.exists()


def test_closing_output_pipes_is_not_process_exit(host_factory):
    _, client = host_factory(
        "import os,time; os.close(1); os.close(2); time.sleep(20)", timeout_seconds=0.2
    )
    ref = client.submit(execution_request())["executionRef"]
    assert wait_final(client, ref)["error"]["code"] == "PROCESS_TIMEOUT"


def test_expired_deadline_is_rejected_without_intent(host_factory):
    _, client = host_factory(SUCCESS)
    request = execution_request()
    request["deadlineAt"] = "2000-01-01T00:00:00Z"
    with pytest.raises(HTTPError) as caught:
        urlopen(
            Request(
                client.base_url + "/v1/executions",
                data=json.dumps(request).encode(),
                headers={"Content-Type": "application/json"},
            )
        )
    assert caught.value.code == 400
    assert client.lookup(request["dispatchKey"])["status"] == "not_created"


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Content-Type": "text/plain"}, 415),
        ({"Content-Type": "application/x-www-form-urlencoded"}, 415),
        ({"Content-Type": "application/json", "Origin": "https://attacker.example"}, 403),
        ({"Content-Type": "application/json", "Origin": "null"}, 403),
        ({"Content-Type": "application/json", "Host": "attacker.example"}, 403),
    ],
)
def test_browser_cross_site_and_dns_rebinding_cannot_create_intent(host_factory, headers, status):
    _, client = host_factory(SUCCESS)
    with pytest.raises(HTTPError) as caught:
        urlopen(
            Request(
                client.base_url + "/v1/executions",
                data=json.dumps(execution_request()).encode(),
                headers=headers,
            )
        )
    assert caught.value.code == status
    assert client.lookup("dispatch-1")["status"] == "not_created"


def test_slow_request_body_has_absolute_deadline(host_factory):
    _, client = host_factory(SUCCESS)
    address = client.base_url.removeprefix("http://")
    host, port = address.split(":")
    connection = socket.create_connection((host, int(port)), timeout=7)
    started = time.monotonic()
    try:
        connection.sendall(
            (
                f"POST /v1/executions HTTP/1.0\r\nHost: {address}\r\n"
                "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
            ).encode()
        )
        response = connection.recv(4096)
        assert b"408" in response
        assert time.monotonic() - started < 7
    finally:
        connection.close()
    assert client.lookup("dispatch-1")["status"] == "not_created"


def test_expired_duplicate_returns_original_but_new_work_and_conflict_are_rejected(
    host_factory,
    tmp_path,
):
    counter = tmp_path / "starts-after-expiry"
    _, client = host_factory(
        f"from pathlib import Path\nPath({str(counter)!r}).open('a').write('1')\n" + SUCCESS
    )
    request = execution_request()
    deadline = datetime.now(UTC) + timedelta(seconds=1)
    request["deadlineAt"] = deadline.isoformat()

    def post(document):
        return urlopen(
            Request(
                client.base_url + "/v1/executions",
                data=json.dumps(document).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=2,
        )

    with post(request) as response:
        assert response.status == 201
        ref = json.load(response)["executionRef"]
    assert wait_final(client, ref)["status"] == "succeeded"
    time.sleep(max(0, (deadline - datetime.now(UTC)).total_seconds()) + 0.02)
    assert deadline < datetime.now(UTC)
    with post(request) as response:
        assert response.status == 200
        assert json.load(response)["executionRef"] == ref
    assert counter.read_text() == "1"

    changed = {**request, "authorizationRef": "different-request"}
    with pytest.raises(HTTPError) as conflict:
        post(changed)
    assert conflict.value.code == 409
    new = {**request, "dispatchKey": "new-expired-key"}
    with pytest.raises(HTTPError) as expired:
        post(new)
    assert expired.value.code == 400
    assert client.lookup("new-expired-key")["status"] == "not_created"
    assert client.lookup(request["dispatchKey"])["executionRef"] == ref
    assert counter.read_text() == "1"
