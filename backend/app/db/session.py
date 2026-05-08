"""SQLAlchemy: асинхронный engine и фабрика сессий.

Создаём один engine на процесс (Singleton — требование МУ) и фабрику AsyncSession,
которая выдаёт сессии как контекстный менеджер. В эндпоинтах сессия инжектится
через FastAPI Depends(get_session).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


# Один engine на процесс. echo=True в dev печатает каждый SQL-запрос в консоль —
# удобно при отладке. В production выключим через ENVIRONMENT=production.
engine = create_async_engine(
    settings.database_url,
    echo=(settings.environment == "dev"),
    future=True,
)


# Фабрика сессий. expire_on_commit=False — иначе после commit() атрибуты
# ORM-объектов «протухают» и при следующем чтении вызовут ленивый запрос к БД,
# что в async-коде может привести к ошибкам.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: открывает сессию на запрос и закрывает её после.

    Использование в эндпоинте:
        async def endpoint(session: AsyncSession = Depends(get_session)):
            result = await session.execute(...)
    """
    async with AsyncSessionLocal() as session:
        yield session
