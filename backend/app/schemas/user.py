"""Схемы пользователя для входящих запросов и исходящих ответов API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validate_password_strength(value: str) -> str:
    """Базовая политика пароля: минимум одна буква и одна цифра.

    Длину (>= 8) проверяет Field(min_length=8) у каждого поля-пароля. Здесь —
    минимальная защита от паролей вида "12345678" / "passwordpassword".
    Полную политику (спецсимволы, проверка по словарю утечек) можно добавить
    позже отдельным валидатором — для self-hosted MVP этого достаточно.
    """
    if not any(c.isalpha() for c in value):
        raise ValueError("Пароль должен содержать хотя бы одну букву")
    if not any(c.isdigit() for c in value):
        raise ValueError("Пароль должен содержать хотя бы одну цифру")
    return value


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
        description="Пароль в открытом виде, минимум 8 символов (буква + цифра)",
    )

    _check_password = field_validator("password")(_validate_password_strength)


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
    email_verified: bool
    created_at: datetime

    # from_attributes=True позволяет создать схему прямо из ORM-модели:
    # UserRead.model_validate(user_orm_instance). Без этого пришлось бы вручную
    # переносить поля.
    model_config = ConfigDict(from_attributes=True)


# Минимальная длина нового пароля — та же, что при регистрации (UserCreate, 8).


class ChangePasswordRequest(BaseModel):
    """Тело POST /auth/change-password (для залогиненного пользователя)."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    _check_new_password = field_validator("new_password")(_validate_password_strength)


class ForgotPasswordRequest(BaseModel):
    """Тело POST /auth/forgot-password — запрос ссылки на сброс пароля."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Тело POST /auth/reset-password — установка нового пароля по токену из письма."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    _check_new_password = field_validator("new_password")(_validate_password_strength)


class VerifyEmailRequest(BaseModel):
    """Тело POST /auth/verify-email — подтверждение почты по токену из письма."""

    token: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    """Простой ответ-сообщение для операций без полезной нагрузки."""

    detail: str
