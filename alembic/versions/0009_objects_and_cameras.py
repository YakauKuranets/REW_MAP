"""objects and cameras tables

Revision ID: 0009_objects_and_cameras
Revises: 0008_chat2_meta_push
Create Date: 2026-01-18

Миграционный скрипт для создания таблиц объектов и связанных камер.

Таблица ``objects`` хранит адреса (координаты), описания и произвольные
метки. Таблица ``object_cameras`` хранит ссылки на камеры, связанные
с объектом. При откате миграции таблицы удаляются.
"""

from __future__ import annotations

import os
import sys
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# Добавляем путь к корню проекта, чтобы избежать ошибок импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# revision identifiers, used by Alembic.
revision = '0009_objects_and_cameras'
down_revision = '0008_chat2_meta_push'
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
    # objects table
    if not _table_exists(conn, 'objects'):
        op.create_table(
            'objects',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('tags', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        # index by created_at for sorting
        op.create_index('ix_objects_created_at', 'objects', ['created_at'])

    # object_cameras table
    if not _table_exists(conn, 'object_cameras'):
        op.create_table(
            'object_cameras',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('object_id', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(length=255), nullable=True),
            sa.Column('url', sa.String(length=512), nullable=False),
            sa.Column('type', sa.String(length=32), nullable=True),
        )
        op.create_index('ix_object_cameras_object_id', 'object_cameras', ['object_id'])
        # Foreign key constraint
        op.create_foreign_key(
            'fk_object_cameras_object',
            'object_cameras',
            'objects',
            ['object_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade():
    conn = op.get_bind()
    # Drop cameras first due to FK
    if _table_exists(conn, 'object_cameras'):
        if _index_exists(conn, 'object_cameras', 'ix_object_cameras_object_id'):
            op.drop_index('ix_object_cameras_object_id', table_name='object_cameras')
        op.drop_table('object_cameras')
    if _table_exists(conn, 'objects'):
        if _index_exists(conn, 'objects', 'ix_objects_created_at'):
            op.drop_index('ix_objects_created_at', table_name='objects')
        op.drop_table('objects')