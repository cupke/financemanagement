"""Модель Transaction — финансовая операция пользователя FinTrack.

  Три типа операций (kind):
  - income — доход (зачисление): balance счёта += amount.
  - expense — расход (списание): balance счёта -= amount.
  - transfer — перевод между двумя своими счетами: balance источника -= amount,
    balance получателя += amount, всё в одной БД-транзакции (атомарно).

  amount всегда положительное; знак вычисляется по kind. Так SUM по периодам
  становится тривиальным (без CASE), а пересчёт баланса при удалении —
  зеркальное применение того же знака.
  """
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
      CheckConstraint,
      DateTime,
      Enum as SAEnum,
      ForeignKey,
      Integer,
      Numeric,
      String,
  )
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


  # native_enum=False — храним kind как VARCHAR + CHECK, не как PG ENUM-тип.
  # Так миграции проще (не нужно ALTER TYPE для добавления значений), и
  # решение переносится на любую SQL-БД без изменений.
TransactionKind = SAEnum(
      "income",
      "expense",
      "transfer",
      name="transaction_kind",
      native_enum=False,
  )


class Transaction(Base):
      """Финансовая операция."""
      __tablename__ = "transactions"

      id: Mapped[int] = mapped_column(Integer, primary_key=True)

      # Прямой owner_id (а не через JOIN на account) — упрощает фильтрацию
      # «все транзакции юзера» одним WHERE без JOIN'а. Это хорошо для отчётов.
      owner_id: Mapped[int] = mapped_column(
          Integer,
          ForeignKey("users.id", ondelete="CASCADE"),
          nullable=False,
          index=True,
      )

      # Основной счёт операции:
      # - income: счёт-получатель (куда пришли деньги).
      # - expense: счёт-источник (откуда списали).
      # - transfer: счёт-источник (откуда уходят деньги).
      account_id: Mapped[int] = mapped_column(
          Integer,
          ForeignKey("accounts.id", ondelete="CASCADE"),
          nullable=False,
          index=True,
      )

      kind: Mapped[str] = mapped_column(TransactionKind, nullable=False)

      # Всегда > 0. Знак определяется kind (см. _signed_delta_for_source в роутере).
      amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

      # Snapshot валюты на момент операции. Если потом юзер сменит currency_code
      # счёта, исторические транзакции останутся с исходной валютой — это нужно
      # для корректных отчётов «сколько потратили в долларах за прошлый год».
      currency_code: Mapped[str] = mapped_column(String(3), nullable=False)

      # Категория опциональна (uncategorized — валидное состояние). SET NULL —
      # удаление категории не стирает транзакцию, просто обнуляет ссылку.
      # Для перевода — всегда NULL (CHECK).
      category_id: Mapped[int | None] = mapped_column(
          Integer,
          ForeignKey("categories.id", ondelete="SET NULL"),
          nullable=True,
          index=True,
      )

      # Счёт-получатель для перевода. NULL для income/expense (CHECK).
      transfer_account_id: Mapped[int | None] = mapped_column(
          Integer,
          ForeignKey("accounts.id", ondelete="CASCADE"),
          nullable=True,
      )

      # Когда операция фактически произошла (по словам юзера). Может быть в
      # прошлом — тогда юзер вводит ретро-чек, не «сейчас». Индекс — потому что
      # история всегда сортируется по этому полю и фильтруется по диапазону.
      occurred_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          nullable=False,
          index=True,
      )

      note: Mapped[str | None] = mapped_column(String(500), nullable=True)

      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          nullable=False,
      )
      updated_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          onupdate=func.now(),
          nullable=False,
      )

      # CHECK-констрейнты — последняя линия обороны. Даже если код будет
      # заполнять поля неправильно (баг), БД отвергнет невалидное состояние.
      __table_args__ = (
          CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
          # Перевод: получатель обязателен, категории нет, источник != получатель.
          CheckConstraint(
              "(kind <> 'transfer') OR ("
              "transfer_account_id IS NOT NULL AND "
              "category_id IS NULL AND "
              "account_id <> transfer_account_id"
              ")",
              name="ck_transactions_transfer_shape",
          ),
          # income/expense: получателя быть не должно.
          CheckConstraint(
              "(kind = 'transfer') OR (transfer_account_id IS NULL)",
              name="ck_transactions_non_transfer_shape",
          ),
      )

      def __repr__(self) -> str:
          return (
              f"<Transaction id={self.id} owner_id={self.owner_id} "
              f"kind={self.kind} amount={self.amount} {self.currency_code} "
              f"account_id={self.account_id}>"
          )