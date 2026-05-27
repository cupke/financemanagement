"""redesign budgets to per-month

Revision ID: b8d4c2e6f1a9
Revises: a3b1c5d9e7f2
Create Date: 2026-05-27 20:30:00.000000

Перевод бюджетов с модели «один лимит на категорию навсегда + effective_from»
на модель «отдельный бюджет на конкретный календарный месяц».

Зачем: пользователь хочет планировать сезонные расходы — лимит на доставку
в мае не должен автоматически распространяться на июнь, если в июне другие
приоритеты. effective_from эту проблему не решал: лимит всё равно тянулся
вперёд бесконечно.

Изменения в схеме:
- Удаляется effective_from
- Добавляются period_year (Integer) и period_month (Integer)
- Меняется UNIQUE: было (owner, category), стало (owner, category, year, month)
- Добавляется CHECK на month BETWEEN 1 AND 12

Для уже существующих строк period_year/period_month проставляется как
текущий месяц по UTC (момент применения миграции).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4c2e6f1a9'
down_revision: Union[str, Sequence[str], None] = 'a3b1c5d9e7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Добавляем новые колонки nullable, чтобы заполнить значения для
    #    существующих строк перед SET NOT NULL.
    op.add_column(
        'budgets',
        sa.Column('period_year', sa.Integer(), nullable=True),
    )
    op.add_column(
        'budgets',
        sa.Column('period_month', sa.Integer(), nullable=True),
    )

    # 2. Для уже существующих бюджетов выставляем период = текущий месяц.
    #    После миграции пользователь сам решит, переносить ли их на следующие
    #    месяцы или пересоздать.
    op.execute(
        "UPDATE budgets SET "
        "period_year = EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER, "
        "period_month = EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER"
    )

    # 3. Делаем колонки NOT NULL — теперь они всегда обязательны.
    op.alter_column('budgets', 'period_year', nullable=False)
    op.alter_column('budgets', 'period_month', nullable=False)

    # 4. Старый UNIQUE (owner, category) больше не корректен:
    #    в новой модели у юзера на одну категорию может быть N бюджетов
    #    (по одному на каждый месяц).
    op.drop_constraint(
        'uq_budgets_owner_category', 'budgets', type_='unique'
    )

    # 5. Новый UNIQUE: один бюджет на (юзер, категория, год, месяц).
    op.create_unique_constraint(
        'uq_budgets_owner_category_period',
        'budgets',
        ['owner_id', 'category_id', 'period_year', 'period_month'],
    )

    # 6. CHECK на корректность месяца — последняя линия обороны на случай
    #    кривого INSERT в обход приложения.
    op.create_check_constraint(
        'ck_budgets_period_month_range',
        'budgets',
        'period_month BETWEEN 1 AND 12',
    )

    # 7. Старое поле effective_from больше не используется.
    op.drop_column('budgets', 'effective_from')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'budgets',
        sa.Column(
            'effective_from',
            sa.Date(),
            nullable=False,
            server_default=sa.text("DATE_TRUNC('month', CURRENT_DATE)"),
        ),
    )
    op.alter_column('budgets', 'effective_from', server_default=None)

    op.drop_constraint(
        'ck_budgets_period_month_range', 'budgets', type_='check'
    )
    op.drop_constraint(
        'uq_budgets_owner_category_period', 'budgets', type_='unique'
    )
    op.create_unique_constraint(
        'uq_budgets_owner_category', 'budgets', ['owner_id', 'category_id']
    )
    op.drop_column('budgets', 'period_month')
    op.drop_column('budgets', 'period_year')
