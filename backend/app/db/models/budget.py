"""Модель Budget — лимит расходов пользователя по категории на конкретный месяц.

Бизнес-правила:
- Один бюджет = одна expense-категория + один календарный месяц + один пользователь.
  То есть у юзера на «Доставку» может быть бюджет в мае и отдельный — в июне,
  с разными суммами. Если в июне бюджет не создавать — он там просто не отслеживается.
  Это решает задачу сезонного планирования (отпуск в августе, подарки в декабре)
  и снимает класс UX-проблем «лимит появился задним числом и сразу превышен».
- Бюджет только для расходных категорий: для доходов лимит не имеет смысла.
  Проверка kind=='expense' делается на уровне роутера, поскольку в БД
  отдельной CHECK через JOIN не написать.
- Лимит хранится в RUB (см. NFR-04 главы 1 ВКР). Расходы в других
  валютах пересчитываются в рубли по курсу ЦБ РФ на дату операции
  (см. _convert_to_rub в роутере).
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Budget(Base):
    """Лимит расходов по категории на конкретный месяц."""
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Категория, на которую установлен лимит. ON DELETE CASCADE —
    # если юзер удаляет категорию, привязанные к ней бюджеты тоже исчезают
    # (для всех месяцев). Альтернатива SET NULL не подходит:
    # «бюджет без категории» бессмысленен.
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Месячный лимит в RUB. Numeric(15,2) — точное число, как у Account.balance.
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    # Календарный год и месяц периода, на который установлен лимит.
    # Храним как два Integer, а не как Date — так нет соблазна интерпретировать
    # «1 мая 2026» как «лимит с 1 мая», а это всё-таки лимит на ВЕСЬ май.
    # Двойка int + UNIQUE гарантирует одинаковое представление в коде и БД.
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)

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

    __table_args__ = (
        # Один пользователь × одна категория × один месяц = один бюджет.
        # Защищает от ситуации «два конкурирующих лимита на одну категорию
        # в одном месяце», которая в UI отображалась бы непонятно.
        UniqueConstraint(
            "owner_id", "category_id", "period_year", "period_month",
            name="uq_budgets_owner_category_period",
        ),
        # Лимит должен быть положительным.
        CheckConstraint("amount > 0", name="ck_budgets_amount_positive"),
        # Месяц 1-12 — последняя линия обороны на случай кривого INSERT
        # в обход приложения (например, через psql вручную).
        CheckConstraint(
            "period_month BETWEEN 1 AND 12",
            name="ck_budgets_period_month_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Budget id={self.id} owner_id={self.owner_id} "
            f"category_id={self.category_id} amount={self.amount} RUB "
            f"period={self.period_year}-{self.period_month:02d}>"
        )
