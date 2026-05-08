"""Схемы пользователя для входящих запросов и исходящих ответов API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Тело запроса POST /auth/register.

    Принимаем email и пароль в открытом виде (по HTTPS!) — пароль хэшируется
    на сервере. Минимум 8 символов — простейшая защита от слабых паролей.
    Полную политику (заглавные/цифры/спецсимволы) добавим позже отдельным
    валидатором, если потребуется.
    """

    email: EmailStr = Field(..., description="Email пользователя (он же логин)")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль в открытом виде, минимум 8 символов",
    )


class UserLogin(BaseModel):
    """Тело запроса POST /auth/login."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserRead(BaseModel):
    """Что отдаём в ответе API при успешной регистрации и в /users/me.

    КРИТИЧНО: здесь нет поля password_hash. Никогда не отдавайте хэш наружу —
    отдельная Pydantic-схема для ответа гарантирует это структурно.
    """

    id: int
    email: EmailStr
    created_at: datetime

    # from_attributes=True позволяет создать схему прямо из ORM-модели:
    # UserRead.model_validate(user_orm_instance). Без этого пришлось бы вручную
    # переносить поля.
    model_config = ConfigDict(from_attributes=True)
