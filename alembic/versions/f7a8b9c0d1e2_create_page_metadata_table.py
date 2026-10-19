"""create_page_metadata_table

Revision ID: f7a8b9c0d1e2
Revises: c9d0e1f2a3b4
Create Date: 2026-10-19 20:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'page_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('meta_title', sa.String(length=500), nullable=False),
        sa.Column('meta_description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_page_metadata_id', 'page_metadata', ['id'])
    op.create_index('ix_page_metadata_path', 'page_metadata', ['path'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_page_metadata_path', table_name='page_metadata')
    op.drop_index('ix_page_metadata_id', table_name='page_metadata')
    op.drop_table('page_metadata')
