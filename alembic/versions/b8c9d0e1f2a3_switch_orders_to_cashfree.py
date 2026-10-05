"""switch_orders_to_cashfree

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_index('ix_orders_razorpay_order_id')
        batch_op.drop_index('ix_orders_razorpay_payment_id')
        batch_op.alter_column('razorpay_order_id', new_column_name='cashfree_order_id',
                              existing_type=sa.String(length=100), existing_nullable=False)
        batch_op.alter_column('razorpay_payment_id', new_column_name='cashfree_payment_id',
                              existing_type=sa.String(length=100), existing_nullable=True)
        batch_op.drop_column('razorpay_signature')
        batch_op.add_column(sa.Column('payment_session_id', sa.String(length=500), nullable=True))

    with op.batch_alter_table('orders') as batch_op:
        batch_op.create_index('ix_orders_cashfree_order_id', ['cashfree_order_id'], unique=True)
        batch_op.create_index('ix_orders_cashfree_payment_id', ['cashfree_payment_id'], unique=True)

    # Stored Razorpay credentials are no longer used
    op.execute("DELETE FROM system_settings WHERE key LIKE 'razorpay_%'")


def downgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_index('ix_orders_cashfree_order_id')
        batch_op.drop_index('ix_orders_cashfree_payment_id')
        batch_op.drop_column('payment_session_id')
        batch_op.add_column(sa.Column('razorpay_signature', sa.String(length=255), nullable=True))
        batch_op.alter_column('cashfree_order_id', new_column_name='razorpay_order_id',
                              existing_type=sa.String(length=100), existing_nullable=False)
        batch_op.alter_column('cashfree_payment_id', new_column_name='razorpay_payment_id',
                              existing_type=sa.String(length=100), existing_nullable=True)

    with op.batch_alter_table('orders') as batch_op:
        batch_op.create_index('ix_orders_razorpay_order_id', ['razorpay_order_id'], unique=True)
        batch_op.create_index('ix_orders_razorpay_payment_id', ['razorpay_payment_id'], unique=True)
