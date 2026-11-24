"""add_images_to_listing_reviews

Revision ID: a7b8c9d0e1f3
Revises: f2a3b4c5d6e7
Create Date: 2026-11-25 00:42:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f3'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('listing_reviews', sa.Column('images', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('listing_reviews', 'images')
