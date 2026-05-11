"""Модель Account — счёт пользователя FinTrack."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
      DateTime,
      Enum as SAEnum,
      ForeignKey,
      Integer,
      Numeric,
      String,
      UniqueConstraint,
  )
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


  # Тип счёта. native_enum=False — VARCHAR + CHECK, не PG-ENUM-тип:
  # проще миграции при добавлении значений, переносится на любую SQL-БД.
  # Тот же паттерн, что для Transaction.kind и Category.kind.
AccountKind = SAEnum(
      "card",       # банковская дебетовая карта
      "cash",       # наличные
      "savings",    # накопительный / депозитный счёт
      "credit",     # кредитная карта
      "e_wallet",   # электронный кошелёк (ЮMoney, Qiwi, PayPal и т.п.)
      "other",      # прочее — на случай нестандартных активов
      name="account_kind",
      native_enum=False,
  )


class Account(Base):
      """Счёт пользователя — банковская карта, наличные, электронный кошелёк
      или накопительный счёт. У одного пользователя может быть несколько счетов
      в разных валютах. Сумма всех счетов — общий капитал пользователя в системе.
      """
      __tablename__ = "accounts"

      id: Mapped[int] = mapped_column(Integer, primary_key=True)

      # Владелец счёта. CASCADE — удаление юзера удаляет его счета вместе
      # с привязанными транзакциями. index=True — частые выборки «все счета
      # этого юзера».
      owner_id: Mapped[int] = mapped_column(
          Integer,
          ForeignKey("users.id", ondelete="CASCADE"),
          nullable=False,
          index=True,
      )

      # Название счёта.
      name: Mapped[str] = mapped_column(String(100), nullable=False)

      # Тип счёта — для категоризации в UI (отдельная иконка/цвет, фильтрация
      # в отчётах). server_default='other' — миграция проставит большинству
      # существующих счетов «прочее», пользователь переклассифицирует вручную.
      kind: Mapped[str] = mapped_column(
          AccountKind, nullable=False, server_default="other"
      )

      # Произвольная заметка пользователя — «зарплатная», «копилка на отпуск»,
      # «дом», и т.п. Опциональна; 500 символов — достаточно для бытовых описаний.
      note: Mapped[str | None] = mapped_column(String(500), nullable=True)

      # Текущий баланс. Numeric(15, 2) = до 13 цифр перед запятой и 2 после.
      balance: Mapped[Decimal] = mapped_column(
          Numeric(15, 2), nullable=False, server_default="0"
      )

      # Код валюты ISO 4217 ("RUB", "USD", "EUR").
      currency_code: Mapped[str] = mapped_column(
          String(3), nullable=False, server_default="RUB"
      )

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

      # У одного юзера не может быть двух счетов с одинаковым названием.
      # У разных юзеров — может (Иван и Пётр оба могут иметь "Наличные").
      __table_args__ = (
          UniqueConstraint("owner_id", "name", name="uq_accounts_owner_name"),
      )

      def __repr__(self) -> str:
          return (
              f"<Account id={self.id} owner_id={self.owner_id} "
              f"name={self.name!r} kind={self.kind} balance={self.balance} {self.currency_code}>"
          )