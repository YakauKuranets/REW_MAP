"""tracker alert telegram notify log

Revision ID: 0004_alert_notify_log
Revises: 0003_perf_indexes
Create Date: 2026-01-02
"""

from __future__ import annotations

import os
import sys

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

revision = "0004_alert_notify_log"
down_revision = "0003_perf_indexes"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    try:
        return name in inspect(conn).get_table_names()
    except Exception:
        return False


def _index_exists(conn, table: str, index_name: str) -> bool:
    try:
        for ix in inspect(conn).get_indexes(table):
            if ix.get("name") == index_name:
                return True
    except Exception:
        return False
    return False


def upgrade():
    conn = op.get_bind()

    if not _table_exists(conn, "tracker_alert_notify_log"):
        op.create_table(
            "tracker_alert_notify_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.String(length=32), nullable=True, index=True),
            sa.Column("user_id", sa.String(length=32), nullable=True, index=True),
            sa.Column("kind", sa.String(length=32), nullable=False, index=True),
            sa.Column("severity", sa.String(length=16), nullable=True, index=True),
            sa.Column("sent_to", sa.String(length=64), nullable=False, index=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True, index=True),
            sa.Column("digest", sa.String(length=64), nullable=True),
        )

    # дополнительные индексы (для некоторых БД index=True внутри create_table не создаёт)
    if _table_exists(conn, "tracker_alert_notify_log") and not _index_exists(conn, "tracker_alert_notify_log", "ix_tracker_alert_notify_device_kind"):
        op.create_index(
            "ix_tracker_alert_notify_device_kind",
            "tracker_alert_notify_log",
            ["device_id", "kind"],
        )
    if _table_exists(conn, "tracker_alert_notify_log") and not _index_exists(conn, "tracker_alert_notify_log", "ix_tracker_alert_notify_sent_at"):
        op.create_index(
            "ix_tracker_alert_notify_sent_at",
            "tracker_alert_notify_log",
            ["sent_at"],
        )


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "tracker_alert_notify_log"):
        # drop indexes first
        if _index_exists(conn, "tracker_alert_notify_log", "ix_tracker_alert_notify_sent_at"):
            op.drop_index("ix_tracker_alert_notify_sent_at", table_name="tracker_alert_notify_log")
        if _index_exists(conn, "tracker_alert_notify_log", "ix_tracker_alert_notify_device_kind"):
            op.drop_index("ix_tracker_alert_notify_device_kind", table_name="tracker_alert_notify_log")
        op.drop_table("tracker_alert_notify_log")
