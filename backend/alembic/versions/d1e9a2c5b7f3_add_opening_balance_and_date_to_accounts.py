"""add opening_balance and opening_date to accounts

  Revision ID: d1e9a2c5b7f3
  Revises: b2b7542ac735
  Create Date: 2026-05-16 18:00:00.000000

  Цель: устранить «двойной учёт» ретро-транзакций.

  До этой миграции Account.balance был единственным источником правды о
  текущем балансе, и каждый POST транзакции его слепо менял — независимо
  от occurred_at. Это давало артефакт: пользователь вводил «сейчас на карте
  100k», добавлял ретро-операцию «20.04 трата 100» — и balance становился
  99 900, хотя банк по-прежнему показывал 100 000.

  После миграции:
  - opening_balance — снимок состояния счёта НА ДАТУ opening_date.
  - balance — кеш текущего значения, считается как
      opening_balance + Σ(signed_amount транзакций c occurred_at >= opening_date).
  - Транзакции с occurred_at < opening_date видны в истории, но в balance
    не входят (их эффект уже сидит в opening_balance).

  Data migration: opening_balance = balance, opening_date = NOW().
  Старые транзакции удаляются (пользователь выбрал «обнулить и пересоздать»
  для чистого тестирования новой логики).

  Подробно — в vkr/02_design.md, заметка 2026-05-16.
  """
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


  # revision identifiers, used by Alembic.
revision: str = 'd1e9a2c5b7f3'
down_revision: Union[str, Sequence[str], None] = 'b2b7542ac735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
      """Upgrade schema."""
      op.add_column(
          'accounts',
          sa.Column(
              'opening_balance',
              sa.Numeric(15, 2),
              server_default='0',
              nullable=False,
          ),
      )
      op.add_column(
          'accounts',
          sa.Column(
              'opening_date',
              sa.DateTime(timezone=True),
              server_default=sa.text('NOW()'),
              nullable=False,
          ),
      )
      op.execute("UPDATE accounts SET opening_balance = balance")
      op.execute("DELETE FROM transactions")


def downgrade() -> None:
      """Downgrade schema."""
      op.drop_column('accounts', 'opening_date')
      op.drop_column('accounts', 'opening_balance')