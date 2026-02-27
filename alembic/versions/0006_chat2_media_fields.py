"""add media fields to chat2_messages

Revision ID: 0006_chat2_media_fields
Revises: 0005_event_chat
Create Date: 2026-01-16

Добавляет поля для хранения медиа в таблицу ``chat2_messages``:
``media_key``, ``mime``, ``size`` и ``thumb_key``.
"""

from __future__ import annotations

import os
import sys
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

revision = "0006_chat2_media_fields"
down_revision = "0005_event_chat"
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
    # Добавляем новые столбцы, если их нет
    for col_name, col_type in [
        ("media_key", sa.String(length=256)),
        ("mime", sa.String(length=64)),
        ("size", sa.Integer()),
        ("thumb_key", sa.String(length=256)),
    ]:
        if not _column_exists(conn, "chat2_messages", col_name):
            op.add_column("chat2_messages", sa.Column(col_name, col_type, nullable=True))


def downgrade():
    conn = op.get_bind()
    for col_name in ["thumb_key", "size", "mime", "media_key"]:
        if _column_exists(conn, "chat2_messages", col_name):
            op.drop_column("chat2_messages", col_name)