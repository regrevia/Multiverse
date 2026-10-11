from __future__ import annotations

import sqlite3

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
            capability_evidence="live_verified",
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
            capability_evidence="live_verified",
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
        assert repeated["capability_evidence"] == "live_verified"
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


def test_superseded_native_binding_can_be_reactivated_without_duplicate_history(
    tmp_path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        session = ledger.create_agent_session(
            namespace="project-a",
            agent_id="reviewer",
            owner_subject="alice",
            scope={"projectId": "multiverse"},
            profile_revision="sha256:profile",
        )
        previous = ledger.bind_native_session(
            session["id"],
            expected_version=1,
            provider_id="claude",
            installation_id="host-a",
            storage_id="project-a-store",
            native_session_id="session-1",
            provider_version="2.1.197",
            capabilities={"resume": True, "fork": True},
            capability_evidence="live_verified",
            source="new",
            workspace_revision="sha256:workspace",
            policy_revision="sha256:policy",
        )
        changed = ledger.bind_native_session(
            session["id"],
            expected_version=2,
            provider_id="claude",
            installation_id="host-a",
            storage_id="project-a-store",
            native_session_id="session-1",
            provider_version="2.1.197",
            capabilities={"resume": True, "fork": True},
            capability_evidence="live_verified",
            source="resume",
            workspace_revision="sha256:workspace",
            policy_revision="sha256:policy",
        )
        bindings = ledger.list_native_session_bindings(session["id"])
        assert changed["id"] != previous["id"]
        assert len(bindings) == 2
        assert bindings[0]["status"] == "superseded"
        assert bindings[1]["status"] == "active"
        assert bindings[1]["source"] == "resume"
    finally:
        ledger.close()


def test_ledger_migrates_legacy_global_native_identity_unique_constraint(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    ledger = Ledger(database)
    try:
        session = ledger.create_agent_session(
            namespace="project-a",
            agent_id="reviewer",
            owner_subject="alice",
            scope={},
            profile_revision="sha256:profile",
        )
        first = ledger.bind_native_session(
            session["id"],
            expected_version=1,
            provider_id="claude",
            installation_id="host-a",
            storage_id="project-a-store",
            native_session_id="session-1",
            provider_version="2.1.197",
            capabilities={"resume": True},
            capability_evidence="live_verified",
            source="new",
            workspace_revision="sha256:workspace",
            policy_revision="sha256:policy",
        )
        ledger.close()
        connection = sqlite3.connect(database)
        connection.execute("DROP INDEX native_session_bindings_active_identity")
        connection.execute(
            """
            CREATE UNIQUE INDEX legacy_native_identity
            ON native_session_bindings(
                provider_id, installation_id, storage_id, native_session_id
            )
            """
        )
        connection.commit()
        connection.close()

        migrated = Ledger(database)
        try:
            changed = migrated.bind_native_session(
                session["id"],
                expected_version=2,
                provider_id="claude",
                installation_id="host-a",
                storage_id="project-a-store",
                native_session_id="session-1",
                provider_version="2.1.197",
                capabilities={"resume": True},
                capability_evidence="live_verified",
                source="resume",
                workspace_revision="sha256:workspace",
                policy_revision="sha256:policy",
            )
            assert changed["id"] != first["id"]
            bindings = migrated.list_native_session_bindings(session["id"])
            assert [item["status"] for item in bindings] == ["superseded", "active"]
            assert bindings[1]["source"] == "resume"
        finally:
            migrated.close()
    finally:
        try:
            ledger.close()
        except sqlite3.Error:
            pass


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
            capability_evidence="protocol_declared_unverified",
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
                capability_evidence="protocol_declared_unverified",
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


def test_native_session_turn_lease_is_single_writer_and_fenced(tmp_path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        first = ledger.acquire_native_session_turn(
            provider_id="codex",
            installation_id="host-a",
            storage_id="codex-home",
            native_session_id="thread-1",
            attempt_id="attempt-a",
            owner_token="execution-a-1",
        )
        assert first["fencing_token"] == 1
        assert ledger.acquire_native_session_turn(
            provider_id="codex",
            installation_id="host-a",
            storage_id="codex-home",
            native_session_id="thread-1",
            attempt_id="attempt-a",
            owner_token="execution-a-1",
        ) == first
        with pytest.raises(LedgerConflict, match="single writer"):
            ledger.acquire_native_session_turn(
                provider_id="codex",
                installation_id="host-a",
                storage_id="codex-home",
                native_session_id="thread-1",
                attempt_id="attempt-a",
                owner_token="execution-a-2",
            )
        with pytest.raises(LedgerConflict, match="single writer"):
            ledger.acquire_native_session_turn(
                provider_id="codex",
                installation_id="host-a",
                storage_id="codex-home",
                native_session_id="thread-1",
                attempt_id="attempt-b",
                owner_token="execution-b-1",
            )
        ledger.release_native_session_turn(
            first["id"],
            attempt_id="attempt-a",
            owner_token="execution-a-1",
            fencing_token=first["fencing_token"],
        )
        second = ledger.acquire_native_session_turn(
            provider_id="codex",
            installation_id="host-a",
            storage_id="codex-home",
            native_session_id="thread-1",
            attempt_id="attempt-b",
            owner_token="execution-b-1",
        )
        assert second["fencing_token"] == 2
        with pytest.raises(LedgerConflict, match="fencing"):
            ledger.release_native_session_turn(
                second["id"],
                attempt_id="attempt-a",
                owner_token="execution-a-1",
                fencing_token=first["fencing_token"],
            )
        released = ledger.release_native_session_turn_for_attempt("attempt-b")
        assert released is not None
        assert released["status"] == "released"
    finally:
        ledger.close()


def test_native_session_lease_recovers_only_after_attempt_is_terminal(tmp_path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        run = ledger.create_run(
            namespace="local",
            deployment_id=None,
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"workflowId": "delivery"},
            input_value={"goal": "test"},
            deadline_at="2099-01-01T00:00:00Z",
        )
        scope = ledger.create_scope(
            run["id"], "delivery", path=["root"], input_value={"goal": "test"}
        )
        invocation = ledger.create_invocation(
            run["id"], scope["id"], "produce", {"goal": "test"}
        )
        attempt = ledger.create_attempt(
            invocation["id"],
            input_value={"goal": "test"},
            dispatch_key=f"{invocation['id']}:1",
            effect_key=invocation["id"],
        )
        first = ledger.acquire_native_session_turn(
            provider_id="codex",
            installation_id="host-a",
            storage_id="codex-home",
            native_session_id="thread-1",
            attempt_id=attempt["id"],
            owner_token="execution-before-crash",
        )
        ledger.finish_attempt(attempt["id"], status="succeeded", output={})

        recovered = ledger.acquire_native_session_turn(
            provider_id="codex",
            installation_id="host-a",
            storage_id="codex-home",
            native_session_id="thread-1",
            attempt_id="next-attempt",
            owner_token="execution-next",
        )
        assert recovered["fencing_token"] == first["fencing_token"] + 1
        assert recovered["owner_attempt_id"] == "next-attempt"
    finally:
        ledger.close()
