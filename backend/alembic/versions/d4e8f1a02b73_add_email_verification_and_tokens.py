"""add email_verified to users and create email_tokens table

Revision ID: d4e8f1a02b73
Revises: c1f2a3b4d5e6
Create Date: 2026-05-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8f1a02b73'
down_revision: Union[str, Sequence[str], None] = 'c1f2a3b4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Существующие пользователи получают email_verified=false (server_default).
    # Вход им это не блокирует — они увидят баннер-напоминание о подтверждении.
    op.add_column(
        'users',
        sa.Column(
            'email_verified',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )

    op.create_table(
        'email_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'purpose',
            sa.Enum(
                'verify_email', 'reset_password',
                name='email_token_purpose',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_email_tokens_token_hash'),
    )
    op.create_index(
        op.f('ix_email_tokens_owner_id'),
        'email_tokens', ['owner_id'], unique=False,
    )
    op.create_index(
        op.f('ix_email_tokens_token_hash'),
        'email_tokens', ['token_hash'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_tokens_token_hash'), table_name='email_tokens')
    op.drop_index(op.f('ix_email_tokens_owner_id'), table_name='email_tokens')
    op.drop_table('email_tokens')
    op.drop_column('users', 'email_verified')
