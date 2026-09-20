from multiverse_workflow.runtime.registry import local_executor_registry


def test_local_registry_reports_declared_installed_available_and_verified_separately() -> None:
    catalog = {
        item["executorRef"]: item
        for item in local_executor_registry().capability_catalog()
    }

    assert catalog["builtin.human-input.v1"]["available"] is True
    assert catalog["example.remote-content.v1"]["declared"] is True
    assert catalog["example.remote-content.v1"]["installed"] is False
    assert catalog["example.remote-content.v1"]["available"] is False
    assert catalog["example.remote-content.v1"]["verified"] is False
