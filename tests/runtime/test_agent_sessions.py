from __future__ import annotations

import pytest

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict


def test_agent_session_stores_native_binding_history_by_provider_install_and_store(
    tmp_path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        session = ledger.create_agent_session(
            namespace="project-a",
            agent_id="reviewer",
            owner_subject="alice",
            scope={"projectId": "multiverse", "purpose": "code-review"},
            profile_revision="sha256:profile-v1",
        )
        first = ledger.bind_native_session(
            session["id"],
            expected_version=1,
            provider_id="codex",
            installation_id="mac-mini-codex",
            storage_id="codex-home-a",
            native_session_id="thread-1",
            provider_version="0.156.1",
            capabilities={"resume": True, "fork": True},
            source="new",
            workspace_revision="sha256:workspace-1",
            policy_revision="sha256:policy-1",
        )
        second = ledger.bind_native_session(
            session["id"],
            expected_version=2,
            provider_id="claude",
            installation_id="mac-mini-claude",
            storage_id="claude-project-a",
            native_session_id="session-2",
            provider_version="2.1.197",
            capabilities={"resume": True, "fork": True},
            source="handoff",
            workspace_revision="sha256:workspace-2",
            policy_revision="sha256:policy-1",
        )
        repeated = ledger.bind_native_session(
            session["id"],
            expected_version=3,
            provider_id="claude",
            installation_id="mac-mini-claude",
            storage_id="claude-project-a",
            native_session_id="session-2",
            provider_version="2.1.197",
            capabilities={"resume": True, "fork": True},
            source="handoff",
            workspace_revision="sha256:workspace-2",
            policy_revision="sha256:policy-1",
            idempotency_key="repeat-binding",
        )

        persisted = ledger.get_agent_session(
            "project-a", session["id"], owner_subject="alice"
        )
        assert persisted is not None
        assert persisted["version"] == 3
        assert persisted["active_binding_id"] == second["id"]
        assert [item["id"] for item in persisted["bindings"]] == [first["id"], second["id"]]
        assert persisted["bindings"][0]["status"] == "superseded"
        assert persisted["bindings"][1]["status"] == "active"
        assert repeated["capabilities"] == {"resume": True, "fork": True}
        assert ledger.get_agent_session(
            "project-a", session["id"], owner_subject="bob"
        ) is None
        assert ledger.list_agent_sessions("other-project", owner_subject="alice") == []
    finally:
        ledger.close()


def test_native_session_identity_is_unique_within_provider_installation_and_store(
    tmp_path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        first = ledger.create_agent_session(
            namespace="project-a",
            agent_id="agent-a",
            owner_subject="alice",
            scope={"projectId": "one"},
            profile_revision="sha256:profile-a",
        )
        second = ledger.create_agent_session(
            namespace="project-a",
            agent_id="agent-b",
            owner_subject="alice",
            scope={"projectId": "two"},
            profile_revision="sha256:profile-b",
        )
        identity = {
            "provider_id": "claude",
            "installation_id": "host-a",
            "storage_id": "claude-project",
            "native_session_id": "same-session",
            "provider_version": "2.1.197",
            "capabilities": {"resume": True},
            "source": "new",
            "workspace_revision": None,
            "policy_revision": "sha256:policy",
        }
        ledger.bind_native_session(
            first["id"], expected_version=1, **identity
        )
        with pytest.raises(LedgerConflict, match="already bound"):
            ledger.bind_native_session(
                second["id"], expected_version=1, **identity
            )

        allowed = ledger.bind_native_session(
            second["id"],
            expected_version=1,
            **{
                **identity,
                "installation_id": "host-b",
            },
        )
        assert allowed["native_session_id"] == "same-session"
    finally:
        ledger.close()


def test_native_session_binding_uses_expected_version_and_rejects_unknown_provider(
    tmp_path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        session = ledger.create_agent_session(
            namespace="project-a",
            agent_id="agent-a",
            owner_subject="alice",
            scope={"projectId": "one"},
            profile_revision="sha256:profile-a",
        )
        with pytest.raises(LedgerConflict, match="version"):
            ledger.bind_native_session(
                session["id"],
                expected_version=2,
                provider_id="claude",
                installation_id="host-a",
                storage_id="claude-project",
                native_session_id="session-1",
                provider_version="2.1.197",
                capabilities={"resume": True},
                source="new",
                workspace_revision=None,
                policy_revision="sha256:policy",
            )
        with pytest.raises(LedgerConflict, match="provider"):
            ledger.bind_native_session(
                session["id"],
                expected_version=1,
                provider_id="",
                installation_id="host-a",
                storage_id="claude-project",
                native_session_id="session-1",
                provider_version="2.1.197",
                capabilities={"resume": True},
                source="new",
                workspace_revision=None,
                policy_revision="sha256:policy",
            )
    finally:
        ledger.close()


def test_agent_session_can_be_filtered_to_a_run_scope_and_invocation(
    tmp_path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        run = ledger.create_run(
            namespace="project-a",
            deployment_id=None,
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"workflowId": "delivery"},
            input_value={"goal": "test"},
            deadline_at="2099-01-01T00:00:00Z",
        )
        scope_row = ledger.create_scope(
            run["id"], "delivery", path=["root"], input_value={"goal": "test"}
        )
        invocation = ledger.create_invocation(
            run["id"], scope_row["id"], "review", {"goal": "test"}
        )
        session = ledger.create_agent_session(
            namespace="project-a",
            agent_id="agent-a",
            owner_subject="alice",
            scope={"projectId": "one"},
            profile_revision="sha256:profile-a",
            run_id=run["id"],
            scope_id=scope_row["id"],
            invocation_id=invocation["id"],
        )
        assert ledger.list_agent_sessions(
            "project-a", owner_subject="alice", run_id=run["id"]
        )[0]["id"] == session["id"]
        assert ledger.list_agent_sessions(
            "project-a", owner_subject="alice", run_id="run-other"
        ) == []
        ledger.create_agent_session(
            namespace="project-a",
            agent_id="agent-a",
            owner_subject="alice",
            scope={"projectId": "one"},
            profile_revision="sha256:profile-a",
            run_id=run["id"],
            idempotency_key="same-session-request",
        )

        other_run = ledger.create_run(
            namespace="project-a",
            deployment_id=None,
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"workflowId": "delivery"},
            input_value={"goal": "other"},
            deadline_at="2099-01-01T00:00:00Z",
        )
        with pytest.raises(LedgerConflict, match="idempotency key conflicts"):
            ledger.create_agent_session(
                namespace="project-a",
                agent_id="agent-a",
                owner_subject="alice",
                scope={"projectId": "one"},
                profile_revision="sha256:profile-a",
                run_id=other_run["id"],
                idempotency_key="same-session-request",
            )
    finally:
        ledger.close()


def test_agent_session_rejects_unknown_or_mismatched_runtime_association(tmp_path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        with pytest.raises(LedgerConflict, match="run association"):
            ledger.create_agent_session(
                namespace="project-a",
                agent_id="agent-a",
                owner_subject="alice",
                scope={},
                profile_revision="sha256:profile-a",
                run_id="missing-run",
            )
    finally:
        ledger.close()
