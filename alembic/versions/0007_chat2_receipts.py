"""add delivery/read counts to chat2_messages

Revision ID: 0007_chat2_receipts
Revises: 0006_chat2_media_fields
Create Date: 2026-01-16

Добавляет поля ``delivered_count`` и ``read_count`` в таблицу ``chat2_messages``.
"""

from __future__ import annotations

import os
import sys
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

revision = "0007_chat2_receipts"
down_revision = "0006_chat2_media_fields"
branch_labels = None
depends_on = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    insp = inspect(conn)
    try:
        cols = {c.get('name') for c in insp.get_columns(table_name)}
        return column_name in cols
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    # добавляем delivered_count и read_count, если ещё не созданы
    for col_name in [
        ("delivered_count", sa.Integer(), 0),
        ("read_count", sa.Integer(), 0),
    ]:
        name, ctype, default_val = col_name
        if not _column_exists(conn, "chat2_messages", name):
            op.add_column(
                "chat2_messages",
                sa.Column(name, ctype, nullable=False, server_default=str(default_val)),
            )
    # Убираем server_default сразу после создания, чтобы не оставлять его в схеме
    # (это не критично для SQLite, но желательно для других БД).
    op.alter_column("chat2_messages", "delivered_count", server_default=None)
    op.alter_column("chat2_messages", "read_count", server_default=None)


def downgrade():
    conn = op.get_bind()
    for col in ["read_count", "delivered_count"]:
        if _column_exists(conn, "chat2_messages", col):
            op.drop_column("chat2_messages", col)