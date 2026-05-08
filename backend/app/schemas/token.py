"""Схема ответа с JWT access-токеном."""
from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Ответ POST /auth/login.

    Формат `{"access_token": "...", "token_type": "bearer"}` — стандарт
    OAuth2 Bearer Token (RFC 6750). Совместим со встроенным авторизационным
    UI Swagger, который ждёт именно такой формат.
    """

    access_token: str = Field(..., description="JWT access-токен")
    token_type: str = Field(default="bearer", description="Тип токена (всегда bearer)")
