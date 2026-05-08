"""Alembic env.py для async-SQLAlchemy.

Этот файл переопределяет стандартный `alembic init`-шаблон под наш проект:
1. Подключает Settings из .env (DATABASE_URL).
2. Импортирует все наши модели, чтобы autogenerate видел их в Base.metadata.
3. Использует async-engine (asyncpg), а не sync.

Запускается автоматически каждой командой `alembic ...` (revision / upgrade / downgrade).
"""
import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Гарантируем, что папка backend/ есть в sys.path: иначе импорт `from app.config ...`
# не сработает, когда alembic запускается напрямую из папки backend/.
# Path(__file__) → .../backend/alembic/env.py; .parents[1] → .../backend
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: F401, E402  — нужен импорт, чтобы заполнить metadata

# Конфиг Alembic из alembic.ini
config = context.config

# Перезаписываем sqlalchemy.url из alembic.ini нашим DATABASE_URL — единый источник
# истины (.env), не нужно дублировать в двух местах.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Логирование по конфигу из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные, по которым Alembic сравнивает текущую схему БД с моделями
# для autogenerate.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline-режим: генерирует SQL-скрипт, не подключаясь к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync-обёртка для async-коннекта (Alembic API внутри sync)."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Создаёт async-engine и применяет миграции через sync-функцию do_run_migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Online-режим: реально подключается к БД и применяет миграции."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
