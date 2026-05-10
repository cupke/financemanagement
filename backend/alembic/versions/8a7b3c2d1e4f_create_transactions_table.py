"""create transactions table

  Revision ID: 8a7b3c2d1e4f
  Revises: 64b509ccd311
  Create Date: 2026-05-10 12:00:00.000000

  """
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


  # revision identifiers, used by Alembic.
revision: str = '8a7b3c2d1e4f'
down_revision: Union[str, Sequence[str], None] = '64b509ccd311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
      """Upgrade schema."""
      op.create_table(
          'transactions',
          sa.Column('id', sa.Integer(), nullable=False),
          sa.Column('owner_id', sa.Integer(), nullable=False),
          sa.Column('account_id', sa.Integer(), nullable=False),
          sa.Column(
              'kind',
              sa.Enum(
                  'income', 'expense', 'transfer',
                  name='transaction_kind',
                  native_enum=False,
              ),
              nullable=False,
          ),
          sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
          sa.Column('currency_code', sa.String(length=3), nullable=False),
          sa.Column('category_id', sa.Integer(), nullable=True),
          sa.Column('transfer_account_id', sa.Integer(), nullable=True),
          sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
          sa.Column('note', sa.String(length=500), nullable=True),
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
          sa.CheckConstraint('amount > 0', name='ck_transactions_amount_positive'),
          sa.CheckConstraint(
              "(kind <> 'transfer') OR ("
              "transfer_account_id IS NOT NULL AND "
              "category_id IS NULL AND "
              "account_id <> transfer_account_id"
              ")",
              name='ck_transactions_transfer_shape',
          ),
          sa.CheckConstraint(
              "(kind = 'transfer') OR (transfer_account_id IS NULL)",
              name='ck_transactions_non_transfer_shape',
          ),
      )
      op.create_index(
          op.f('ix_transactions_owner_id'),
          'transactions', ['owner_id'], unique=False,
      )
      op.create_index(
          op.f('ix_transactions_account_id'),
          'transactions', ['account_id'], unique=False,
      )
      op.create_index(
          op.f('ix_transactions_category_id'),
          'transactions', ['category_id'], unique=False,
      )
      op.create_index(
          op.f('ix_transactions_occurred_at'),
          'transactions', ['occurred_at'], unique=False,
      )


def downgrade() -> None:
      """Downgrade schema."""
      op.drop_index(op.f('ix_transactions_occurred_at'), table_name='transactions')
      op.drop_index(op.f('ix_transactions_category_id'), table_name='transactions')
      op.drop_index(op.f('ix_transactions_account_id'), table_name='transactions')
      op.drop_index(op.f('ix_transactions_owner_id'), table_name='transactions')
      op.drop_table('transactions')