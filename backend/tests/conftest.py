import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fintrack:fintrack_dev_password@db:5432/fintrack_test",
)

# Подменяем env ДО первого импорта app — чтобы settings подхватили тестовую БД.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-not-for-prod")

# ВАЖНО: сначала импортируем подмодули, и только потом — FastAPI-инстанс.
# Если сделать наоборот, `import app.db.models` перезапишет имя `app`
# и FastAPI-инстанс станет недоступен под этим именем.
import app.db.models  # noqa: F401, E402  — регистрирует модели в Base.metadata
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_database() -> AsyncGenerator[None, None]:
    """Создать схему в тестовой БД перед всеми тестами и снести после."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Свежая сессия на каждый тест + полная очистка таблиц после."""
    async with TestSessionLocal() as s:
        yield s
        await s.rollback()
    # Чистим таблицы через отдельное соединение, чтобы не было гонок с пулом.
    async with test_engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.commit()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP-клиент, который ходит в FastAPI без поднятия сервера."""

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    fastapi_app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Регистрирует тестового пользователя и возвращает заголовки с JWT."""
    email = "test@example.com"
    password = "TestPassword123!"
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
