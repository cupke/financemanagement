"""Реестр всех ORM-моделей.

  Alembic при autogenerate смотрит Base.metadata. Чтобы метаданные
  содержали все наши таблицы, каждая модель должна быть импортирована
  хотя бы один раз. Делаем это здесь — и подключаем `from app.db import models`
  в alembic/env.py.
  """
from app.db.models.account import Account
from app.db.models.user import User

__all__ = ["Account", "User"]