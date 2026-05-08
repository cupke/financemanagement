"""FinTrack — точка входа FastAPI.

Здесь регистрируется само приложение и его базовые системные эндпоинты.
Бизнес-логика будет жить в app.api.v1.* и подключаться сюда через include_router.
"""
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth as auth_router
from app.api.v1 import users as users_router
from app.db.session import get_session


app = FastAPI(
    title="FinTrack API",
    description=(
        "Бесплатное self-hosted веб-приложение учёта личных финансов "
        "с открытым REST API и мультивалютностью по курсам ЦБ РФ."
    ),
    version="0.1.0",
)


# Все бизнес-эндпоинты живут под префиксом /api/v1 — единый namespace для версионирования API.
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(users_router.router, prefix="/api/v1")


@app.get(
    "/health",
    tags=["system"],
    summary="Проверка готовности приложения и БД",
)
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Проверяет, что приложение работает и БД отвечает.

    Возвращает 200 OK при успехе. При недоступности БД — HTTP 503,
    чтобы Docker healthcheck / load balancer могли автоматически вывести
    инстанс из ротации.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc.__class__.__name__}",
        ) from exc
    return {"status": "ok", "db": "ok"}
