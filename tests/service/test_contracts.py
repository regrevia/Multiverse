import pytest
from pydantic import ValidationError

from multiverse_workflow.service.contracts import (
    CommandReceipt,
    RunCreateRequest,
)


def test_run_create_request_requires_deployment_fields() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate({"input": {"goal": "ship"}})


def test_command_receipt_is_accepted_until_runtime_processes_it() -> None:
    receipt = CommandReceipt(
        request_id="request_1",
        status="accepted",
        resource_id="run_1",
        operation="run.create",
    )

    assert receipt.model_dump()["status"] == "accepted"
