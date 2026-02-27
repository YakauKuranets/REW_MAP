"""safely migrate payload text columns to JSON/JSONB

Revision ID: 0013_payload_json_to_jsonb_safe
Revises: 0012_ai_tags_priority
Create Date: 2026-02-23
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0013_payload_json_to_jsonb_safe'
down_revision = '0012_ai_tags_priority'
branch_labels = None
depends_on = None


_TABLES = (
    'incident_events',
    'duty_events',
    'duty_notifications',
    'tracker_alerts',
    'tracker_admin_audit',
    'admin_audit_log',
)


def _migrate_postgres() -> None:
    # Безопасный парсер: возвращает NULL для невалидного JSON вместо ошибки.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION _safe_text_to_jsonb(src text)
        RETURNS jsonb
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF src IS NULL OR btrim(src) = '' THEN
                RETURN NULL;
            END IF;
            RETURN src::jsonb;
        EXCEPTION WHEN others THEN
            RETURN NULL;
        END;
        $$;
        """
    )

    for table in _TABLES:
        op.add_column(table, sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        op.execute(
            f"""
            UPDATE {table}
            SET payload = CASE
                WHEN payload_json IS NULL OR btrim(payload_json) = '' THEN NULL
                ELSE COALESCE(_safe_text_to_jsonb(payload_json), '{{}}'::jsonb)
            END
            """
        )
        op.drop_column(table, 'payload_json')

    op.execute("DROP FUNCTION IF EXISTS _safe_text_to_jsonb(text);")


def _migrate_generic() -> None:
    # Fallback для SQLite/других БД в dev/test: преобразуем Python-ом.
    bind = op.get_bind()

    for table in _TABLES:
        op.add_column(table, sa.Column('payload', sa.JSON(), nullable=True))

        rows = list(bind.execute(sa.text(f"SELECT id, payload_json FROM {table}")))
        for row in rows:
            raw = row[1]
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                parsed = None
            else:
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    parsed = {}
            bind.execute(
                sa.text(f"UPDATE {table} SET payload = :payload WHERE id = :id"),
                {'payload': parsed, 'id': row[0]},
            )

        op.drop_column(table, 'payload_json')


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        _migrate_postgres()
    else:
        _migrate_generic()


def downgrade() -> None:
    bind = op.get_bind()

    for table in _TABLES:
        op.add_column(table, sa.Column('payload_json', sa.Text(), nullable=True))
        if bind.dialect.name == 'postgresql':
            op.execute(
                f"""
                UPDATE {table}
                SET payload_json = CASE
                    WHEN payload IS NULL THEN NULL
                    ELSE payload::text
                END
                """
            )
        else:
            rows = list(bind.execute(sa.text(f"SELECT id, payload FROM {table}")))
            for row in rows:
                raw = row[1]
                if raw is None:
                    payload_json = None
                elif isinstance(raw, str):
                    payload_json = raw
                else:
                    payload_json = json.dumps(raw, ensure_ascii=False)
                bind.execute(
                    sa.text(f"UPDATE {table} SET payload_json = :payload_json WHERE id = :id"),
                    {'payload_json': payload_json, 'id': row[0]},
                )

        op.drop_column(table, 'payload')
