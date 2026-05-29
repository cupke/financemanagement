"""Общие FastAPI-зависимости (Depends).

Основная — get_current_user: достаёт пользователя из JWT, переданного в заголовке
Authorization: Bearer <token>. Все защищённые эндпоинты будут просить её через Depends.
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.session import get_session
from app.security import decode_access_token


# OAuth2PasswordBearer — это «спецификация» того, откуда брать токен:
# из заголовка Authorization: Bearer <jwt>. Параметр tokenUrl — путь к /login,
# Swagger UI использует его, чтобы нарисовать кнопку «Authorize».
# auto_error=False означает: если токена нет, не падать сразу 401,
# а вернуть None — мы сами решим, что делать (так точнее контролируем сообщение).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# Единая 401-ошибка для всех случаев «не аутентифицирован».
# WWW-Authenticate=Bearer — стандартный заголовок, по нему клиент понимает,
# каким способом нужно авторизоваться.
_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Не удалось проверить учётные данные",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Извлечь пользователя из JWT.

    Поток:
    1. Если токена нет — 401.
    2. Если токен невалидный/истёк — 401.
    3. Если в `sub` claim нет ID — 401.
    4. Если пользователя с таким ID нет в БД — 401 (мог быть удалён,
       пока токен ещё не истёк).
    """
    if token is None:
        raise _credentials_exception

    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise _credentials_exception from None

    sub = payload.get("sub")
    if sub is None:
        raise _credentials_exception

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise _credentials_exception from None

    user = await session.get(User, user_id)
    if user is None:
        raise _credentials_exception

    return user
