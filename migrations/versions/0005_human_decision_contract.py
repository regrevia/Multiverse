"""Harden HumanRequest decision ownership and idempotency.

Revision ID: 0005_human_decision_contract
Revises: 0004_ownership_foreign_keys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_human_decision_contract"
down_revision = "0004_ownership_foreign_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("human_decisions", sa.Column("namespace", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE human_decisions AS decisions
            SET namespace = runs.namespace
            FROM human_requests AS requests
            JOIN runs ON runs.id = requests.run_id
            WHERE requests.id = decisions.request_id
            """
        )
    )
    op.alter_column("human_decisions", "namespace", nullable=False)
    op.drop_constraint(
        "human_decisions_idempotency_key_key",
        "human_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_human_decisions_namespace_idempotency",
        "human_decisions",
        ["namespace", "idempotency_key"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM human_decisions
                GROUP BY idempotency_key
                HAVING COUNT(*) > 1
            )
            """
        )
    ).scalar_one()
    if duplicate:
        raise RuntimeError(
            "cannot downgrade human decision idempotency while namespaces duplicate keys"
        )
    op.drop_constraint(
        "uq_human_decisions_namespace_idempotency",
        "human_decisions",
        type_="unique",
    )
    op.create_unique_constraint(
        "human_decisions_idempotency_key_key",
        "human_decisions",
        ["idempotency_key"],
    )
    op.drop_column("human_decisions", "namespace")
