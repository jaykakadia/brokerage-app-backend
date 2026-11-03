"""soft_delete_and_audit_logs

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-11-03 15:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOFT_DELETE_TABLES = [
    'listings',
    'users',
    'categories',
    'locations',
    'plans',
    'employees',
    'blogs',
    'enquiries',
    'page_metadata',
    'wishlists',
]


def upgrade() -> None:
    # 1. Add is_deleted and deleted_at to domain tables
    for table in SOFT_DELETE_TABLES:
        op.add_column(
            table,
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false'))
        )
        op.add_column(
            table,
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index(f'ix_{table}_is_deleted', table, ['is_deleted'])

    # Sync any pre-existing rows marked status='deleted'
    op.execute("UPDATE listings SET is_deleted = true, deleted_at = NOW() WHERE status = 'deleted'")
    op.execute("UPDATE users SET is_deleted = true, deleted_at = NOW() WHERE status = 'deleted'")

    # 2. Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('table_name', sa.String(length=50), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('record_name', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_email', sa.String(length=255), nullable=True),
        sa.Column('actor_role', sa.String(length=50), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'])
    op.create_index('ix_audit_logs_table_name', 'audit_logs', ['table_name'])
    op.create_index('ix_audit_logs_record_id', 'audit_logs', ['record_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    for table in SOFT_DELETE_TABLES:
        op.drop_index(f'ix_{table}_is_deleted', table_name=table)
        op.drop_column(table, 'deleted_at')
        op.drop_column(table, 'is_deleted')

