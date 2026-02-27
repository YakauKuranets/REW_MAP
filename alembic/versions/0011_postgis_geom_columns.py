"""add postgis geometry columns for addresses and pending markers

Revision ID: 0011_postgis_geom_columns
Revises: 0010_incidents
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
try:
    from geoalchemy2 import Geometry
except Exception:  # pragma: no cover
    class Geometry:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            pass



revision = '0011_postgis_geom_columns'
down_revision = '0010_incidents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS postgis'))

    op.add_column('addresses', sa.Column('geom', Geometry(geometry_type='POINT', srid=4326), nullable=True))
    op.add_column('pending_markers', sa.Column('geom', Geometry(geometry_type='POINT', srid=4326), nullable=True))

    op.execute(sa.text("""
        UPDATE addresses
        SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        WHERE lon IS NOT NULL AND lat IS NOT NULL
    """))
    op.execute(sa.text("""
        UPDATE pending_markers
        SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        WHERE lon IS NOT NULL AND lat IS NOT NULL
    """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.drop_column('pending_markers', 'geom')
    op.drop_column('addresses', 'geom')
