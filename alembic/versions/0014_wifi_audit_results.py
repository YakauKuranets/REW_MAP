"""create wifi_audit_results table

Revision ID: 0014_wifi_audit_results
Revises: 0013_payload_json_to_jsonb_safe
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa


revision = '0014_wifi_audit_results'
down_revision = '0013_payload_json_to_jsonb_safe'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'wifi_audit_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.String(length=36), nullable=False, unique=True),
        sa.Column('client_id', sa.String(length=100), nullable=True),
        sa.Column('bssid', sa.String(length=17), nullable=True),
        sa.Column('essid', sa.String(length=100), nullable=True),
        sa.Column('security_type', sa.String(length=10), nullable=True),
        sa.Column('is_vulnerable', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('vulnerability_type', sa.String(length=50), nullable=True),
        sa.Column('found_password', sa.String(length=100), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('wifi_audit_results')
