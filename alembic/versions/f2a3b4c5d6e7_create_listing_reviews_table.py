"""create_listing_reviews_table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-24 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'listing_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('listing_id', sa.Integer(), sa.ForeignKey('listings.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, index=True),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False, index=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'listing_id', name='uq_user_listing_review')
    )


def downgrade() -> None:
    op.drop_table('listing_reviews')
