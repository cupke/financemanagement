"""Модель RecurringTransaction — правило автоповтора финансовой операции.

Зачем фича: регулярные доходы и расходы (зарплата, аренда, подписки,
платёж по кредиту) пользователь не хочет вбивать вручную каждый месяц.
Правило описывает «что» и «как часто», а приложение само создаёт по нему
обычные операции (Transaction).

КАК генерируются операции (важное проектное решение):
В приложении нет фонового планировщика (Celery/cron). Вместо него —
«ленивая до-генерация» (catch-up): правило хранит next_run_at — момент
следующей назревшей операции. При заходе пользователя в приложение
роутер /recurring-transactions/run проходит по всем активным правилам и
материализует ВСЕ операции, чьё время уже наступило (next_run_at <= сейчас),
сдвигая next_run_at вперёд на (interval × frequency). Так не нужен отдельный
демон, а пропуски (пользователь не заходил месяц) автоматически
доганяются при следующем заходе.

Сгенерированная операция — обычный Transaction, неотличимый от введённого
руками: связи «операция ← правило» в MVP нет (см. перспективы развития ВКР).

Поля kind/account/amount/category/transfer повторяют форму Transaction —
правило это, по сути, «шаблон» будущих операций. CHECK-констрейнты тоже
зеркалят transaction'ы, чтобы движок не создал невалидную операцию.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


# native_enum=False — храним как VARCHAR + CHECK, не как PG ENUM-тип
# (тот же подход, что у Transaction.kind): проще миграции и переносимость на
# любую SQL-БД.
RecurrenceFrequency = SAEnum(
    "daily",
    "weekly",
    "monthly",
    "yearly",
    name="recurrence_frequency",
    native_enum=False,
)

# Тип операции — те же три значения, что у Transaction.
RecurringKind = SAEnum(
    "income",
    "expense",
    "transfer",
    name="recurring_transaction_kind",
    native_enum=False,
)


class RecurringTransaction(Base):
    """Правило автоповтора операции."""
    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Человекочитаемое имя правила («Зарплата», «Аренда квартиры»). Помогает
    # отличать правила в списке, когда у них одинаковые сумма/счёт.
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    kind: Mapped[str] = mapped_column(RecurringKind, nullable=False)

    # Счёт-источник (как у Transaction.account_id). ON DELETE CASCADE —
    # удалили счёт → правила по нему теряют смысл, удаляются вместе с ним.
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    # Снимок валюты на момент создания правила (для отображения в списке без
    # JOIN на счёт). При материализации операции валюта берётся из счёта
    # актуально — на случай, если пользователь сменил валюту счёта.
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)

    # Категория (для income/expense). Для перевода — всегда NULL (CHECK).
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

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Частота: daily/weekly/monthly/yearly.
    frequency: Mapped[str] = mapped_column(RecurrenceFrequency, nullable=False)

    # «Каждые N периодов»: interval=2 + frequency=weekly → раз в две недели.
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Дата/время первой операции по правилу. Может быть в прошлом — тогда при
    # первом /run доганяются все пропущенные с этой даты до сейчас.
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Необязательная дата окончания. После неё правило больше не генерит
    # операции и автоматически деактивируется. NULL = бессрочно.
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Момент следующей назревшей операции — «курсор» движка. При создании
    # равен start_at; после каждой материализации сдвигается вперёд.
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Когда последний раз сгенерировали операцию (для UI «последний запуск»).
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Пауза без удаления: is_active=False → правило игнорируется движком.
    # Также сюда движок сам ставит False, когда next_run_at перешагнул end_at.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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

    # CHECK-констрейнты зеркалят инварианты Transaction — последняя линия
    # обороны, чтобы движок физически не смог создать кривую операцию.
    __table_args__ = (
        CheckConstraint(
            "amount > 0", name="ck_recurring_amount_positive"
        ),
        CheckConstraint(
            "interval >= 1", name="ck_recurring_interval_positive"
        ),
        # Перевод: получатель обязателен, категории нет, источник != получатель.
        CheckConstraint(
            "(kind <> 'transfer') OR ("
            "transfer_account_id IS NOT NULL AND "
            "category_id IS NULL AND "
            "account_id <> transfer_account_id"
            ")",
            name="ck_recurring_transfer_shape",
        ),
        # income/expense: получателя быть не должно.
        CheckConstraint(
            "(kind = 'transfer') OR (transfer_account_id IS NULL)",
            name="ck_recurring_non_transfer_shape",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RecurringTransaction id={self.id} owner_id={self.owner_id} "
            f"name={self.name!r} kind={self.kind} amount={self.amount} "
            f"{self.frequency} x{self.interval} active={self.is_active}>"
        )
