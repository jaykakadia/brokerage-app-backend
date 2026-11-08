"""add_attachment_url_to_support_chat

Revision ID: d4e5f6a7b8c0
Revises: b2c3d4e5f6a7
Create Date: 2026-11-08 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c0'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    if dialect_name == 'postgresql':
        op.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS attachment_url VARCHAR(500);")
    else:
        op.add_column('support_messages', sa.Column('attachment_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('support_messages', 'attachment_url')

