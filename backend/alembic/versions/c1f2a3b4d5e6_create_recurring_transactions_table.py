"""create recurring_transactions table

Revision ID: c1f2a3b4d5e6
Revises: b8d4c2e6f1a9
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f2a3b4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b8d4c2e6f1a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'recurring_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column(
            'kind',
            sa.Enum(
                'income', 'expense', 'transfer',
                name='recurring_transaction_kind',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('transfer_account_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column(
            'frequency',
            sa.Enum(
                'daily', 'weekly', 'monthly', 'yearly',
                name='recurrence_frequency',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('interval', sa.Integer(), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'is_active', sa.Boolean(),
            server_default=sa.text('true'), nullable=False,
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['transfer_account_id'], ['accounts.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('amount > 0', name='ck_recurring_amount_positive'),
        sa.CheckConstraint('interval >= 1', name='ck_recurring_interval_positive'),
        sa.CheckConstraint(
            "(kind <> 'transfer') OR ("
            "transfer_account_id IS NOT NULL AND "
            "category_id IS NULL AND "
            "account_id <> transfer_account_id"
            ")",
            name='ck_recurring_transfer_shape',
        ),
        sa.CheckConstraint(
            "(kind = 'transfer') OR (transfer_account_id IS NULL)",
            name='ck_recurring_non_transfer_shape',
        ),
    )
    op.create_index(
        op.f('ix_recurring_transactions_owner_id'),
        'recurring_transactions', ['owner_id'], unique=False,
    )
    op.create_index(
        op.f('ix_recurring_transactions_account_id'),
        'recurring_transactions', ['account_id'], unique=False,
    )
    op.create_index(
        op.f('ix_recurring_transactions_category_id'),
        'recurring_transactions', ['category_id'], unique=False,
    )
    op.create_index(
        op.f('ix_recurring_transactions_next_run_at'),
        'recurring_transactions', ['next_run_at'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_recurring_transactions_next_run_at'),
        table_name='recurring_transactions',
    )
    op.drop_index(
        op.f('ix_recurring_transactions_category_id'),
        table_name='recurring_transactions',
    )
    op.drop_index(
        op.f('ix_recurring_transactions_account_id'),
        table_name='recurring_transactions',
    )
    op.drop_index(
        op.f('ix_recurring_transactions_owner_id'),
        table_name='recurring_transactions',
    )
    op.drop_table('recurring_transactions')
