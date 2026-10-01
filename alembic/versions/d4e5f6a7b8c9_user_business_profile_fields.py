"""user_business_profile_fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-01 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('business_name', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('whatsapp', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('facebook_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('website_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('x_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('x_url')
        batch_op.drop_column('website_url')
        batch_op.drop_column('facebook_url')
        batch_op.drop_column('whatsapp')
        batch_op.drop_column('business_name')
