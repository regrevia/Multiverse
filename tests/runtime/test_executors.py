from __future__ import annotations

import sys

from multiverse_workflow.runtime.executors import execute_local_process


def test_local_process_round_trips_json() -> None:
    result = execute_local_process(
        {"value": 2},
        {
            "command": [
                sys.executable,
                "-c",
                (
                    "import json, sys; "
                    "value=json.load(sys.stdin)['value']; "
                    "print(json.dumps({'value': value * 2}))"
                ),
            ]
        },
    )

    assert result.output == {"value": 4}
