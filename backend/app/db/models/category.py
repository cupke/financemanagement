"""Модель Category — категория транзакций пользователя FinTrack."""
from datetime import datetime
  
from sqlalchemy import (
      DateTime,
      Enum as SAEnum, 
      ForeignKey,
      Index,
      Integer,
      String,
  )
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

  
  # Категория может быть «доходной» или «расходной». Тот же паттерн, что и для
  # Transaction.kind: храним как VARCHAR + CHECK (native_enum=False), а не как
  # PG-ENUM-тип. Это даёт переносимость между БД и более простые миграции при
  # добавлении новых значений в будущем.
CategoryKind = SAEnum(
      "income",
      "expense",
      name="category_kind",
      native_enum=False,
  )
  
  
class Category(Base):
      """Категория транзакций. 

      Иерархия через self-reference parent_id:
      «Расходы» → «Продукты» → «Бакалея». На уровне БД храним плоский список;
      дерево строится клиентом из плоского ответа API. Так избегаем N+1 запросов
      для всех потомков и проблемы «бесконечной глубины».

      Правило целостности: kind дочерней категории всегда совпадает с kind
      родителя — «расходная подкатегория в доходной» бессмысленна. Проверка
      делается на уровне приложения (роутер categories), потому что CHECK
      с JOIN'ом до родителя SQL не поддерживает.
      """
      __tablename__ = "categories"
  
      id: Mapped[int] = mapped_column(Integer, primary_key=True)

      owner_id: Mapped[int] = mapped_column(
          Integer,
          ForeignKey("users.id", ondelete="CASCADE"),
          nullable=False,
          index=True,
      )
  
      name: Mapped[str] = mapped_column(String(100), nullable=False)

      # Тип категории: 'income' — для доходов, 'expense' — для расходов.
      # Задаётся при создании и не меняется после (изменение породило бы
      # несогласованность с уже привязанными транзакциями).
      # server_default='expense' — миграция проставит большинству категорий
      # «расход»; «доходные» пользователь пересоздаст вручную.
      kind: Mapped[str] = mapped_column(
          CategoryKind, nullable=False, server_default="expense", index=True
      )

      # parent_id — self-reference. ON DELETE CASCADE: удаление родителя
      # удаляет всё поддерево (несколько каскадов на одной операции). NULL —
      # корневая категория. index=True ускоряет поиск всех детей родителя.
      parent_id: Mapped[int | None] = mapped_column(
          Integer,
          ForeignKey("categories.id", ondelete="CASCADE"),
          nullable=True,
          index=True,
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

      # Уникальность имени внутри (owner, parent).
      # postgresql_nulls_not_distinct=True (PostgreSQL 15+) делает так, чтобы
      # NULL значения тоже считались одинаковыми. Без этой опции два корневых
      # счёта (parent_id=NULL) с одним именем прошли бы проверку — что неверно
      # с точки зрения UX («Расходы» не должно создаваться дважды).
      __table_args__ = (
          Index(
              "uq_categories_owner_parent_name",
              "owner_id",
              "parent_id",
              "name",
              unique=True,
              postgresql_nulls_not_distinct=True,
          ),
      )
  
      def __repr__(self) -> str:
          return (
              f"<Category id={self.id} owner_id={self.owner_id} "
              f"name={self.name!r} kind={self.kind} parent_id={self.parent_id}>"
          )