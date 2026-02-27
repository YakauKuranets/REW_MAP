"""add alerting rules and history tables

Revision ID: 0018_alerting_rules_history
Revises: 0017_add_handshake_analyses
Create Date: 2026-02-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_alerting_rules_history"
down_revision = "0017_add_handshake_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("condition", sa.String(length=50), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_condition", "alert_rules", ["condition"], unique=False)
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"], unique=False)

    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_history_created_at", "alert_history", ["created_at"], unique=False)
    op.create_index("ix_alert_history_rule_id", "alert_history", ["rule_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_history_rule_id", table_name="alert_history")
    op.drop_index("ix_alert_history_created_at", table_name="alert_history")
    op.drop_table("alert_history")

    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_condition", table_name="alert_rules")
    op.drop_table("alert_rules")
