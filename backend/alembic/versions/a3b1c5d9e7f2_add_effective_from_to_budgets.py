"""add effective_from to budgets

Revision ID: a3b1c5d9e7f2
Revises: e7c8f4a92d50
Create Date: 2026-05-27 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b1c5d9e7f2'
down_revision: Union[str, Sequence[str], None] = 'e7c8f4a92d50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Добавляем effective_from — дату, с которой бюджет действует. Для уже
    существующих строк по умолчанию ставим первый день текущего месяца
    (DATE_TRUNC по CURRENT_DATE). Дальше серверный default снимаем, чтобы
    приложение всегда явно подставляло значение само.
    """
    op.add_column(
        'budgets',
        sa.Column(
            'effective_from',
            sa.Date(),
            nullable=False,
            server_default=sa.text("DATE_TRUNC('month', CURRENT_DATE)"),
        ),
    )
    # Снимаем server_default — теперь приложение само пишет значение.
    # Существующие строки уже получили дефолт; на новые INSERT'ы он влиять не будет.
    op.alter_column('budgets', 'effective_from', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('budgets', 'effective_from')
