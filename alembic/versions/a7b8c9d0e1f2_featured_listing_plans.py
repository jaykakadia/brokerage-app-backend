"""featured_listing_plans

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-03 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('plans') as batch_op:
        batch_op.add_column(sa.Column('plan_type', sa.String(length=20), nullable=False, server_default='leads'))
        batch_op.create_index('ix_plans_plan_type', ['plan_type'])
    with op.batch_alter_table('listings') as batch_op:
        batch_op.add_column(sa.Column('featured_until', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('listing_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_orders_listing_id', ['listing_id'])
        batch_op.create_foreign_key('fk_orders_listing_id_listings', 'listings', ['listing_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('fk_orders_listing_id_listings', type_='foreignkey')
        batch_op.drop_index('ix_orders_listing_id')
        batch_op.drop_column('listing_id')
    with op.batch_alter_table('listings') as batch_op:
        batch_op.drop_column('featured_until')
    with op.batch_alter_table('plans') as batch_op:
        batch_op.drop_index('ix_plans_plan_type')
        batch_op.drop_column('plan_type')
