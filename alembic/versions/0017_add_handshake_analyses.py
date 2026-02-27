"""add handshake analyses table

Revision ID: 0017_add_handshake_analyses
Revises: 0016_add_auth_tables
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa


revision = '0017_add_handshake_analyses'
down_revision = '0016_add_auth_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'handshake_analyses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.String(length=36), nullable=False, unique=True),
        sa.Column('client_id', sa.String(length=100), nullable=True),
        sa.Column('bssid', sa.String(length=17), nullable=True),
        sa.Column('essid', sa.String(length=100), nullable=True),
        sa.Column('security_type', sa.String(length=10), nullable=True),
        sa.Column('handshake_file', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='pending'),
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('password_found', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('handshake_analyses')
