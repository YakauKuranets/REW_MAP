"""incidents and assignments tables

Revision ID: 0010_incidents
Revises: 0009_objects_and_cameras
Create Date: 2026-01-18

Миграция для создания таблиц ``incidents``, ``incident_events`` и
``incident_assignments``. Эти таблицы реализуют базовую модель
оперативных инцидентов: каждая запись инцидента может быть связана
с объектом, иметь набор событий (таймлайн) и список назначенных
нарядов. При откате миграции создаваемые таблицы удаляются.
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
revision = '0010_incidents'
down_revision = '0009_objects_and_cameras'
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    """Проверить существование таблицы."""
    try:
        return name in inspect(conn).get_table_names()
    except Exception:
        return False


def _index_exists(conn, table: str, index_name: str) -> bool:
    """Проверить существование индекса."""
    try:
        for ix in inspect(conn).get_indexes(table):
            if ix.get("name") == index_name:
                return True
    except Exception:
        return False
    return False


def upgrade():
    conn = op.get_bind()
    # incidents table
    if not _table_exists(conn, 'incidents'):
        op.create_table(
            'incidents',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('object_id', sa.Integer(), nullable=True),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('address', sa.String(length=255), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('priority', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='new'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_incidents_created_at', 'incidents', ['created_at'])
        op.create_index('ix_incidents_status', 'incidents', ['status'])
        op.create_index('ix_incidents_priority', 'incidents', ['priority'])
        # FK to objects (nullable)
        op.create_foreign_key(
            'fk_incidents_object',
            'incidents',
            'objects',
            ['object_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # incident_events table
    if not _table_exists(conn, 'incident_events'):
        op.create_table(
            'incident_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('incident_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=True),
            sa.Column('ts', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_incident_events_incident', 'incident_events', ['incident_id'])
        op.create_index('ix_incident_events_ts', 'incident_events', ['ts'])
        op.create_foreign_key(
            'fk_incident_events_incident',
            'incident_events',
            'incidents',
            ['incident_id'],
            ['id'],
            ondelete='CASCADE',
        )

    # incident_assignments table
    if not _table_exists(conn, 'incident_assignments'):
        op.create_table(
            'incident_assignments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('incident_id', sa.Integer(), nullable=False),
            sa.Column('shift_id', sa.Integer(), nullable=False),
            sa.Column('assigned_at', sa.DateTime(), nullable=True),
            sa.Column('accepted_at', sa.DateTime(), nullable=True),
            sa.Column('enroute_at', sa.DateTime(), nullable=True),
            sa.Column('on_scene_at', sa.DateTime(), nullable=True),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_incident_assignments_incident', 'incident_assignments', ['incident_id'])
        op.create_index('ix_incident_assignments_shift', 'incident_assignments', ['shift_id'])
        # FKs
        op.create_foreign_key(
            'fk_incident_assignments_incident',
            'incident_assignments',
            'incidents',
            ['incident_id'],
            ['id'],
            ondelete='CASCADE',
        )
        op.create_foreign_key(
            'fk_incident_assignments_shift',
            'incident_assignments',
            'duty_shifts',
            ['shift_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade():
    conn = op.get_bind()
    # Drop in reverse order to respect dependencies
    if _table_exists(conn, 'incident_assignments'):
        if _index_exists(conn, 'incident_assignments', 'ix_incident_assignments_incident'):
            op.drop_index('ix_incident_assignments_incident', table_name='incident_assignments')
        if _index_exists(conn, 'incident_assignments', 'ix_incident_assignments_shift'):
            op.drop_index('ix_incident_assignments_shift', table_name='incident_assignments')
        op.drop_table('incident_assignments')
    if _table_exists(conn, 'incident_events'):
        if _index_exists(conn, 'incident_events', 'ix_incident_events_incident'):
            op.drop_index('ix_incident_events_incident', table_name='incident_events')
        if _index_exists(conn, 'incident_events', 'ix_incident_events_ts'):
            op.drop_index('ix_incident_events_ts', table_name='incident_events')
        op.drop_table('incident_events')
    if _table_exists(conn, 'incidents'):
        if _index_exists(conn, 'incidents', 'ix_incidents_created_at'):
            op.drop_index('ix_incidents_created_at', table_name='incidents')
        if _index_exists(conn, 'incidents', 'ix_incidents_status'):
            op.drop_index('ix_incidents_status', table_name='incidents')
        if _index_exists(conn, 'incidents', 'ix_incidents_priority'):
            op.drop_index('ix_incidents_priority', table_name='incidents')
        op.drop_table('incidents')