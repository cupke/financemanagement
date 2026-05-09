"""FinTrack — точка входа FastAPI.

  Здесь регистрируется само приложение и его базовые системные эндпоинты.
  Бизнес-логика будет жить в app.api.v1.* и подключаться сюда через include_router.
  """
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from swagger_ui_bundle import swagger_ui_path

from app.api.v1 import accounts as accounts_router
from app.api.v1 import auth as auth_router
from app.api.v1 import categories as categories_router
from app.api.v1 import users as users_router
from app.config import settings
from app.db.session import get_session


  # docs_url=None — отключаем дефолтный /docs, который тащит ассеты с
  # cdn.jsdelivr.net (на машине пользователя CDN блокируется расширением/
  # антивирусом). Дальше регистрируем свой /docs с локальными ассетами.
app = FastAPI(
      title="FinTrack API",
      description=(
          "Бесплатное self-hosted веб-приложение учёта личных финансов "
          "с открытым REST API и мультивалютностью по курсам ЦБ РФ."
      ),
      version="0.1.0",
      docs_url=None,
  )
# Swagger UI 4.x (тот, что в pip-пакете swagger-ui-bundle 1.x) понимает
  # только OpenAPI 3.0. FastAPI по умолчанию пишет 3.1 — переключаем на 3.0.2,
  # чтобы наши схемы рендерились в Swagger. Свои фичи 3.1 мы не используем.
app.openapi_version = "3.0.2"


  # CORS-middleware — разрешает frontend (другой origin) делать запросы к API.
app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.cors_origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )


  # Локальные ассеты Swagger UI (JS и CSS), упакованные в pip-пакет
  # swagger-ui-bundle. Раздаём их через StaticFiles на /static-docs/*.
  # Так Swagger перестаёт зависеть от внешнего CDN.
app.mount(
      "/static-docs",
      StaticFiles(directory=swagger_ui_path),
      name="static-docs",
  )


  # Свой /docs, использующий локальные ассеты вместо CDN.
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> object:
      return get_swagger_ui_html(
          openapi_url=app.openapi_url,
          title=f"{app.title} — Swagger UI",
          swagger_js_url="/static-docs/swagger-ui-bundle.js",
          swagger_css_url="/static-docs/swagger-ui.css",
      )


  # Все бизнес-эндпоинты живут под префиксом /api/v1 — единый namespace для версионирования API.
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(users_router.router, prefix="/api/v1")
app.include_router(accounts_router.router, prefix="/api/v1")
app.include_router(categories_router.router, prefix="/api/v1")


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