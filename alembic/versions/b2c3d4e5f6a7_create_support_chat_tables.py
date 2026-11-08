"""create_support_chat_tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-08 10:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. support_conversations
    op.create_table(
        'support_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('guest_name', sa.String(length=150), nullable=True),
        sa.Column('guest_email', sa.String(length=255), nullable=True),
        sa.Column('guest_phone', sa.String(length=30), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('unread_admin_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unread_user_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_support_conversations_id', 'support_conversations', ['id'])
    op.create_index('ix_support_conversations_session_id', 'support_conversations', ['session_id'], unique=True)
    op.create_index('ix_support_conversations_user_id', 'support_conversations', ['user_id'])
    op.create_index('ix_support_conversations_status', 'support_conversations', ['status'])
    op.create_index('ix_support_conversations_is_deleted', 'support_conversations', ['is_deleted'])

    # 2. support_messages
    op.create_table(
        'support_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_type', sa.String(length=20), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=True),
        sa.Column('sender_name', sa.String(length=150), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['support_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_support_messages_id', 'support_messages', ['id'])
    op.create_index('ix_support_messages_conversation_id', 'support_messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_index('ix_support_messages_conversation_id', table_name='support_messages')
    op.drop_index('ix_support_messages_id', table_name='support_messages')
    op.drop_table('support_messages')

    op.drop_index('ix_support_conversations_is_deleted', table_name='support_conversations')
    op.drop_index('ix_support_conversations_status', table_name='support_conversations')
    op.drop_index('ix_support_conversations_user_id', table_name='support_conversations')
    op.drop_index('ix_support_conversations_session_id', table_name='support_conversations')
    op.drop_index('ix_support_conversations_id', table_name='support_conversations')
    op.drop_table('support_conversations')

