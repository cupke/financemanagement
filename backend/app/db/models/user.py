"""Модель User — учётная запись пользователя FinTrack."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    """Учётная запись пользователя.

    На этом этапе храним только то, что нужно для регистрации/входа:
    идентификатор, email (уникальный), хэш пароля, время создания записи.
    Дополнительные поля (имя, аватар, настройки) будем добавлять позже
    отдельными миграциями — это нормальный сценарий Alembic.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Email — основной идентификатор пользователя.
    # unique=True гарантирует, что не будет двух учётных записей с одним email;
    # index=True ускоряет поиск при логине (он будет очень частым запросом).
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )

    # Хэш пароля Argon2id (NFR-04 в требованиях ВКР).
    # Длина 200 символов — с запасом под формат Argon2 (обычно ~120-150).
    # Сам пароль никогда не хранится — только хэш.
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)

    # Подтверждён ли email. Регистрация создаёт пользователя с False; письмо со
    # ссылкой пользователь запрашивает сам кнопкой на странице профиля
    # (/resend-verification), переход по ссылке ставит True. Вход НЕ блокируется —
    # неподтверждённый пользователь видит напоминание на профиле (мягкий сценарий).
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Время создания записи. server_default=func.now() — БД сама проставляет
    # значение через NOW() при INSERT, не зависит от часов клиента.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
