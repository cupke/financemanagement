"""Конфигурация приложения через Pydantic Settings.

  Все настройки приложения читаются из переменных окружения и/или из файла .env.
  Pydantic валидирует их типы на старте: если переменная отсутствует или неверного
  типа — приложение упадёт с понятной ошибкой ещё до того, как начнёт принимать
  запросы. Это лучше, чем «упасть в 3 часа ночи на проде из-за опечатки в .env».
  """
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
      """Настройки приложения, заполняются из переменных окружения / файла .env."""

      # Строка подключения к БД в формате SQLAlchemy для async-драйвера asyncpg.
      # Пример: postgresql+asyncpg://user:pass@host:port/dbname
      database_url: str = Field(..., description="DSN для PostgreSQL")

      # Текущее окружение: dev / staging / production.
      # Сейчас влияет только на echo SQL-запросов; позже — на CORS, уровень логов и т.п.
      environment: str = Field(default="dev")

      # --- Параметры JWT-токенов ---
      # Секрет, которым подписываются access-токены. Если он утечёт — любой
      # сможет выпустить поддельный токен от имени любого пользователя.
      # В .env храним длинную случайную строку (>=32 байта), сгенерированную
      # командой `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
      jwt_secret_key: str = Field(..., description="Секрет для подписи JWT")

      # Алгоритм подписи. HS256 — симметричный HMAC-SHA256, достаточно для
      # одного backend-сервиса. Для распределённой системы взяли бы RS256.
      jwt_algorithm: str = Field(default="HS256")

      # Время жизни access-токена. 60 минут — баланс между UX (не нужно
      # часто перелогиниваться) и безопасностью (украденный токен живёт
      # ограниченное время).
      jwt_access_token_expires_minutes: int = Field(default=60)

      # --- CORS ---
      # Список origin'ов (схема://хост:порт), которым разрешено стучаться
      # к нашему API из браузера. Без этого же списка браузер блокирует
      # кросс-доменные запросы по Same-Origin Policy — даже если бэкенд
      # вернёт 200 OK, JS на странице ответ не получит.
      #
      # Дефолт — наш dev-frontend (Vite на 60001 в двух вариантах: 127.0.0.1
      # и localhost — это разные origin'ы для браузера). В проде сюда
      # переопределяется публичный домен через env-переменную CORS_ORIGINS
      # в JSON-формате: '["https://fintrack.example"]'.
      cors_origins: list[str] = Field(
          default=[
              "http://127.0.0.1:60001",
              "http://localhost:60001",
          ],
          description="Origin'ы, которым разрешён доступ к API",
      )

      model_config = SettingsConfigDict(
          env_file=".env",
          env_file_encoding="utf-8",
          case_sensitive=False,
      )


  # Один экземпляр на процесс (паттерн Singleton — требование МУ, GoF).
  # Импортируется в любом модуле как `from app.config import settings`.
settings = Settings()