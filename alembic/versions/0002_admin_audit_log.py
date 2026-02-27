"""admin audit log table (explicit DDL, no create_all)

Revision ID: 0002_admin_audit
Revises: 0001_init
Create Date: 2025-12-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0002_admin_audit"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    insp = inspect(conn)
    return table_name in set(insp.get_table_names())


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    insp = inspect(conn)
    try:
        for ix in insp.get_indexes(table_name):
            if ix.get("name") == index_name:
                return True
    except Exception:
        return False
    return False


def upgrade():
    conn = op.get_bind()

    if not _table_exists(conn, "admin_audit_log"):
        op.create_table(
            'admin_audit_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ts', sa.DateTime()),
            sa.Column('actor', sa.String(64), nullable=True),
            sa.Column('role', sa.String(16), nullable=True),
            sa.Column('ip', sa.String(64), nullable=True),
            sa.Column('method', sa.String(8), nullable=True),
            sa.Column('path', sa.String(255), nullable=True),
            sa.Column('action', sa.String(64), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=True)
        )

    if _table_exists(conn, "admin_audit_log") and not _index_exists(conn, "admin_audit_log", "ix_admin_audit_log_ts"):
        op.create_index("ix_admin_audit_log_ts", "admin_audit_log", ["ts"])


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "admin_audit_log") and _index_exists(conn, "admin_audit_log", "ix_admin_audit_log_ts"):
        op.drop_index("ix_admin_audit_log_ts", table_name="admin_audit_log")
    if _table_exists(conn, "admin_audit_log"):
        op.drop_table("admin_audit_log")
