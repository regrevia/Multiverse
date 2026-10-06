"""Complete inbox and host/session persistence edges.

Revision ID: 0003_ledger_completeness
Revises: 0002_ledger_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_ledger_completeness"
down_revision = "0002_ledger_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("executor", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_digest", sa.Text(), nullable=False),
        sa.Column("received_at", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.Text()),
        sa.Column("error_json", sa.Text()),
        sa.UniqueConstraint(
            "namespace",
            "executor",
            "external_id",
            "revision",
            name="uq_inbox_source_revision",
        ),
    )
    op.create_table(
        "execution_host_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("host_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("installation_identity", sa.Text(), nullable=False),
        sa.Column("native_session_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "namespace",
            "provider",
            "installation_identity",
            "native_session_id",
            name="uq_host_session_binding",
        ),
    )
    op.add_column(
        "attempts",
        sa.Column("host_session_id", sa.Text(), sa.ForeignKey("execution_host_sessions.id")),
    )
    op.create_foreign_key(
        "fk_runs_current_scope",
        "runs",
        "scopes",
        ["current_scope_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_runs_current_invocation",
        "runs",
        "invocations",
        ["current_invocation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_scopes_parent_invocation",
        "scopes",
        "invocations",
        ["parent_invocation_id"],
        ["id"],
    )
    op.drop_constraint("outbox_attempt_id_key", "outbox", type_="unique")


def downgrade() -> None:
    connection = op.get_bind()
    has_multiple_actions = connection.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM outbox GROUP BY attempt_id HAVING COUNT(*) > 1"
            ")"
        )
    ).scalar_one()
    if has_multiple_actions:
        raise RuntimeError(
            "cannot downgrade 0003 while an attempt has multiple Outbox actions"
        )
    op.create_unique_constraint("outbox_attempt_id_key", "outbox", ["attempt_id"])
    op.drop_constraint("fk_scopes_parent_invocation", "scopes", type_="foreignkey")
    op.drop_constraint("fk_runs_current_invocation", "runs", type_="foreignkey")
    op.drop_constraint("fk_runs_current_scope", "runs", type_="foreignkey")
    op.drop_column("attempts", "host_session_id")
    op.drop_table("execution_host_sessions")
    op.drop_table("inbox")
