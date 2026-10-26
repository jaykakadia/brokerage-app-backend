"""add_is_featured_column

Revision ID: 0d2652f96b5f
Revises: f7a8b9c0d1e2
Create Date: 2026-10-26 22:58:41.166092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d2652f96b5f'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add is_featured column to listings table."""
    with op.batch_alter_table('listings') as batch_op:
        batch_op.add_column(sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Downgrade schema - remove is_featured column."""
    with op.batch_alter_table('listings') as batch_op:
        batch_op.drop_column('is_featured')
