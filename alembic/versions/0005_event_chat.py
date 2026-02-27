"""event chat models

Revision ID: 0005_event_chat
Revises: 0004_alert_notify_log
Create Date: 2026-01-16

Этот миграционный скрипт добавляет таблицы для нового событийного чата:
``chat2_channels``, ``chat2_messages`` и ``chat2_members``.
"""

from __future__ import annotations

import os
import sys
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# Добавляем путь к корню проекта, чтобы избежать ошибок импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Revision identifiers, used by Alembic.
revision = "0005_event_chat"
down_revision = "0004_alert_notify_log"
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

    # chat2_channels
    if not _table_exists(conn, "chat2_channels"):
        op.create_table(
            "chat2_channels",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("type", sa.String(length=16), nullable=False),
            sa.Column("shift_id", sa.Integer(), nullable=True),
            sa.Column("marker_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), nullable=True),
        )

    # chat2_messages
    if not _table_exists(conn, "chat2_messages"):
        op.create_table(
            "chat2_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("channel_id", sa.String(length=36), nullable=False),
            sa.Column("sender_type", sa.String(length=16), nullable=False),
            sa.Column("sender_id", sa.String(length=64), nullable=False),
            sa.Column("client_msg_id", sa.String(length=64), nullable=True),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="text"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("edited_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        # Foreign key constraint
        op.create_foreign_key(
            "fk_chat2_messages_channel",
            "chat2_messages",
            "chat2_channels",
            ["channel_id"],
            ["id"],
        )
        # Index for sorting by channel and created_at
        op.create_index(
            "ix_chat2_messages_channel_created",
            "chat2_messages",
            ["channel_id", "created_at"],
        )

    # chat2_members
    if not _table_exists(conn, "chat2_members"):
        op.create_table(
            "chat2_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("channel_id", sa.String(length=36), nullable=False),
            sa.Column("member_type", sa.String(length=16), nullable=False),
            sa.Column("member_id", sa.String(length=64), nullable=False),
            sa.Column("last_read_message_id", sa.String(length=36), nullable=True),
            sa.Column("last_read_at", sa.DateTime(), nullable=True),
        )
        # FK
        op.create_foreign_key(
            "fk_chat2_members_channel",
            "chat2_members",
            "chat2_channels",
            ["channel_id"],
            ["id"],
        )
        # Unique constraint on member
        op.create_unique_constraint(
            "uq_chat2_members_member",
            "chat2_members",
            ["channel_id", "member_type", "member_id"],
        )


def downgrade():
    conn = op.get_bind()
    # Drop chat2_members first (due to FKs)
    if _table_exists(conn, "chat2_members"):
        # Unique constraint will be dropped automatically with table
        op.drop_table("chat2_members")
    if _table_exists(conn, "chat2_messages"):
        # Drop index first
        if _index_exists(conn, "chat2_messages", "ix_chat2_messages_channel_created"):
            op.drop_index("ix_chat2_messages_channel_created", table_name="chat2_messages")
        op.drop_table("chat2_messages")
    if _table_exists(conn, "chat2_channels"):
        op.drop_table("chat2_channels")