"""add_trial_plans_and_claims

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c0
Create Date: 2026-11-21 22:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    if dialect_name == 'postgresql':
        op.execute("ALTER TABLE plans ADD COLUMN IF NOT EXISTS is_trial BOOLEAN DEFAULT FALSE NOT NULL;")
    else:
        op.add_column('plans', sa.Column('is_trial', sa.Boolean(), server_default=sa.text('0'), nullable=False))

    op.create_index(op.f('ix_plans_is_trial'), 'plans', ['is_trial'], unique=False)

    op.create_table(
        'trial_claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trial_claims_id'), 'trial_claims', ['id'], unique=False)
    op.create_index(op.f('ix_trial_claims_email'), 'trial_claims', ['email'], unique=True)
    op.create_index(op.f('ix_trial_claims_phone'), 'trial_claims', ['phone'], unique=False)
    op.create_index(op.f('ix_trial_claims_plan_id'), 'trial_claims', ['plan_id'], unique=False)
    op.create_index(op.f('ix_trial_claims_user_id'), 'trial_claims', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_trial_claims_user_id'), table_name='trial_claims')
    op.drop_index(op.f('ix_trial_claims_plan_id'), table_name='trial_claims')
    op.drop_index(op.f('ix_trial_claims_phone'), table_name='trial_claims')
    op.drop_index(op.f('ix_trial_claims_email'), table_name='trial_claims')
    op.drop_index(op.f('ix_trial_claims_id'), table_name='trial_claims')
    op.drop_table('trial_claims')

    op.drop_index(op.f('ix_plans_is_trial'), table_name='plans')
    op.drop_column('plans', 'is_trial')
