"""add meta_json and push tokens

Revision ID: 0008_chat2_meta_push
Revises: 0007_chat2_receipts
Create Date: 2026-01-16 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "0008_chat2_meta_push"
down_revision = "0007_chat2_receipts"
branch_labels = None
depends_on = None

def upgrade():
    # Добавляем колонку meta_json в chat2_messages
    with op.batch_alter_table("chat2_messages") as batch_op:
        batch_op.add_column(
            sa.Column("meta_json", sa.JSON().with_variant(sa.Text(), "sqlite"), nullable=True)
        )
    # Создаём таблицу push-токенов
    op.create_table(
        "chat2_push_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("member_type", sa.String(length=16), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=256), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("member_type", "member_id", "token", name="uq_chat2_push_member_token"),
    )

def downgrade():
    # Удаляем таблицу push-токенов
    op.drop_table("chat2_push_tokens")
    # Удаляем колонку meta_json
    with op.batch_alter_table("chat2_messages") as batch_op:
        batch_op.drop_column("meta_json")