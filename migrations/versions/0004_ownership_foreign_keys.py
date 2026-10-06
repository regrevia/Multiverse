"""Enforce ownership consistency between Ledger rows.

Revision ID: 0004_ownership_foreign_keys
Revises: 0003_ledger_completeness
"""

from __future__ import annotations

from alembic import op

revision = "0004_ownership_foreign_keys"
down_revision = "0003_ledger_completeness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_scopes_run_id", "scopes", ["id", "run_id"])
    op.create_unique_constraint(
        "uq_scopes_run_id_id",
        "scopes",
        ["run_id", "id"],
    )
    op.create_unique_constraint(
        "uq_invocations_run_scope",
        "invocations",
        ["id", "run_id", "scope_id"],
    )
    op.create_unique_constraint(
        "uq_invocations_run_id",
        "invocations",
        ["run_id", "id"],
    )
    op.create_unique_constraint(
        "uq_attempts_ownership",
        "attempts",
        ["id", "run_id", "scope_id", "invocation_id"],
    )
    op.create_foreign_key(
        "fk_runs_current_scope_ownership",
        "runs",
        "scopes",
        ["current_scope_id", "id"],
        ["id", "run_id"],
    )
    op.create_foreign_key(
        "fk_runs_current_invocation_ownership",
        "runs",
        "invocations",
        ["current_invocation_id", "id"],
        ["id", "run_id"],
    )
    op.create_foreign_key(
        "fk_scopes_parent_invocation_ownership",
        "scopes",
        "invocations",
        ["parent_invocation_id", "run_id"],
        ["id", "run_id"],
    )
    op.create_foreign_key(
        "fk_invocations_scope_ownership",
        "invocations",
        "scopes",
        ["scope_id", "run_id"],
        ["id", "run_id"],
    )
    op.create_foreign_key(
        "fk_attempts_scope_ownership",
        "attempts",
        "scopes",
        ["scope_id", "run_id"],
        ["id", "run_id"],
    )
    op.create_foreign_key(
        "fk_attempts_invocation_ownership",
        "attempts",
        "invocations",
        ["invocation_id", "run_id", "scope_id"],
        ["id", "run_id", "scope_id"],
    )


def downgrade() -> None:
    for name, table, kind in (
        ("fk_attempts_invocation_ownership", "attempts", "foreignkey"),
        ("fk_attempts_scope_ownership", "attempts", "foreignkey"),
        ("fk_invocations_scope_ownership", "invocations", "foreignkey"),
        ("fk_scopes_parent_invocation_ownership", "scopes", "foreignkey"),
        ("fk_runs_current_invocation_ownership", "runs", "foreignkey"),
        ("fk_runs_current_scope_ownership", "runs", "foreignkey"),
    ):
        op.drop_constraint(name, table, type_=kind)
    op.drop_constraint("uq_attempts_ownership", "attempts", type_="unique")
    op.drop_constraint("uq_invocations_run_id", "invocations", type_="unique")
    op.drop_constraint("uq_invocations_run_scope", "invocations", type_="unique")
    op.drop_constraint("uq_scopes_run_id_id", "scopes", type_="unique")
    op.drop_constraint("uq_scopes_run_id", "scopes", type_="unique")
