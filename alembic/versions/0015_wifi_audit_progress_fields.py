"""add progress fields to wifi_audit_results

Revision ID: 0015_wifi_audit_progress_fields
Revises: 0014_wifi_audit_results
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa

revision = '0015_wifi_audit_progress_fields'
down_revision = '0014_wifi_audit_results'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('wifi_audit_results', sa.Column('estimated_time_seconds', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('wifi_audit_results', sa.Column('progress', sa.Integer(), nullable=True, server_default='0'))

def downgrade() -> None:
    op.drop_column('wifi_audit_results', 'progress')
    op.drop_column('wifi_audit_results', 'estimated_time_seconds')
