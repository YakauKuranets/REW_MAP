"""perf indexes for hot queries

Revision ID: 0003_perf_indexes
Revises: 0002_admin_audit
Create Date: 2025-12-24
"""

from __future__ import annotations

import os
import sys

from alembic import op
from sqlalchemy import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

revision = "0003_perf_indexes"
down_revision = "0002_admin_audit"
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

    # chat_messages: ускорение счётчиков непрочитанного и выборок
    if _table_exists(conn, "chat_messages") and not _index_exists(conn, "chat_messages", "ix_chat_messages_user_sender_isread"):
        op.create_index(
            "ix_chat_messages_user_sender_isread",
            "chat_messages",
            ["user_id", "sender", "is_read", "created_at"],
        )

    # tracking_points: ускорение таймлайна по сессии и по user_id
    if _table_exists(conn, "tracking_points") and not _index_exists(conn, "tracking_points", "ix_tracking_points_session_ts"):
        op.create_index(
            "ix_tracking_points_session_ts",
            "tracking_points",
            ["session_id", "ts"],
        )
    if _table_exists(conn, "tracking_points") and not _index_exists(conn, "tracking_points", "ix_tracking_points_user_ts"):
        op.create_index(
            "ix_tracking_points_user_ts",
            "tracking_points",
            ["user_id", "ts"],
        )

    # duty_events: ускорение выборок по смене
    if _table_exists(conn, "duty_events") and not _index_exists(conn, "duty_events", "ix_duty_events_shift_ts"):
        op.create_index(
            "ix_duty_events_shift_ts",
            "duty_events",
            ["shift_id", "ts"],
        )


def downgrade():
    conn = op.get_bind()
    # drop in reverse order, only if exist
    if _table_exists(conn, "duty_events") and _index_exists(conn, "duty_events", "ix_duty_events_shift_ts"):
        op.drop_index("ix_duty_events_shift_ts", table_name="duty_events")
    if _table_exists(conn, "tracking_points") and _index_exists(conn, "tracking_points", "ix_tracking_points_user_ts"):
        op.drop_index("ix_tracking_points_user_ts", table_name="tracking_points")
    if _table_exists(conn, "tracking_points") and _index_exists(conn, "tracking_points", "ix_tracking_points_session_ts"):
        op.drop_index("ix_tracking_points_session_ts", table_name="tracking_points")
    if _table_exists(conn, "chat_messages") and _index_exists(conn, "chat_messages", "ix_chat_messages_user_sender_isread"):
        op.drop_index("ix_chat_messages_user_sender_isread", table_name="chat_messages")
