"""add ai_tags and priority for markers and addresses

Revision ID: 0012_ai_tags_priority
Revises: 0011_postgis_geom_columns
Create Date: 2026-02-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0012_ai_tags_priority'
down_revision = '0011_postgis_geom_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == 'postgresql' else sa.JSON()

    op.add_column('addresses', sa.Column('ai_tags', json_type, nullable=True))
    op.add_column('addresses', sa.Column('priority', sa.Integer(), nullable=True))

    op.add_column('pending_markers', sa.Column('ai_tags', json_type, nullable=True))
    op.add_column('pending_markers', sa.Column('priority', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('pending_markers', 'priority')
    op.drop_column('pending_markers', 'ai_tags')
    op.drop_column('addresses', 'priority')
    op.drop_column('addresses', 'ai_tags')
