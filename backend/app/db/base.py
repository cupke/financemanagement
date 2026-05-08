"""Декларативная база SQLAlchemy для всех ORM-моделей.

Все таблицы FinTrack наследуют этот Base. Через Base.metadata Alembic
узнаёт схему БД и генерирует миграции.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей FinTrack."""
    pass
