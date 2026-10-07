"""Record SQLite to PostgreSQL control-plane import proofs.

Revision ID: 0006_sqlite_import_receipts
Revises: 0005_human_decision_contract
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_sqlite_import_receipts"
down_revision = "0005_human_decision_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sqlite_import_receipts",
        sa.Column("namespace", sa.Text(), primary_key=True),
        sa.Column("snapshot_digest", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sqlite_import_receipts")
