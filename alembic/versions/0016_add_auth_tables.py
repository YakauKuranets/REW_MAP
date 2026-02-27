"""add auth tables

Revision ID: 0016_add_auth_tables
Revises: 0015_wifi_audit_progress_fields
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa


revision = '0016_add_auth_tables'
down_revision = '0015_wifi_audit_progress_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(length=80), nullable=False, unique=True),
        sa.Column('email', sa.String(length=120), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=True, server_default='operator'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('permissions', sa.String(length=255), nullable=True, server_default='diagnostics:read'),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    op.create_index('ix_api_keys_key', 'api_keys', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_api_keys_key', table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_table('users')
