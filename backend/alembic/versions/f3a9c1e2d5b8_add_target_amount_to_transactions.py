"""add target_amount to transactions (cross-currency transfers)

Revision ID: f3a9c1e2d5b8
Revises: d4e8f1a02b73
Create Date: 2026-05-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1e2d5b8'
down_revision: Union[str, Sequence[str], None] = 'd4e8f1a02b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Сумма зачисления для кросс-валютного перевода (в валюте счёта-получателя).
    # NULL для income/expense и одновалютных переводов — на них поведение
    # не меняется.
    op.add_column(
        'transactions',
        sa.Column('target_amount', sa.Numeric(precision=15, scale=2), nullable=True),
    )
    # target_amount допустим только у перевода.
    op.create_check_constraint(
        'ck_transactions_target_amount_transfer_only',
        'transactions',
        "(target_amount IS NULL) OR (kind = 'transfer')",
    )
    # Если задана — положительная (как и amount).
    op.create_check_constraint(
        'ck_transactions_target_amount_positive',
        'transactions',
        '(target_amount IS NULL) OR (target_amount > 0)',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'ck_transactions_target_amount_positive', 'transactions', type_='check'
    )
    op.drop_constraint(
        'ck_transactions_target_amount_transfer_only', 'transactions', type_='check'
    )
    op.drop_column('transactions', 'target_amount')
