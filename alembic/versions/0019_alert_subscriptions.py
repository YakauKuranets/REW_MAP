"""add alert subscriptions table

Revision ID: 0019_alert_subscriptions
Revises: 0018_alerting_rules_history
Create Date: 2026-02-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_alert_subscriptions"
down_revision = "0018_alerting_rules_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("min_severity", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_subscriptions_email", "alert_subscriptions", ["email"], unique=False)
    op.create_index("ix_alert_subscriptions_is_active", "alert_subscriptions", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_subscriptions_is_active", table_name="alert_subscriptions")
    op.drop_index("ix_alert_subscriptions_email", table_name="alert_subscriptions")
    op.drop_table("alert_subscriptions")
