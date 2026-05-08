"""Роутер /users: эндпоинты, привязанные к учётной записи."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models.user import User
from app.schemas.user import UserRead


router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Получить данные текущего пользователя",
)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Вернуть профиль того, кому принадлежит JWT в заголовке Authorization.

    Полезно для frontend: после логина клиент сразу зовёт /users/me, чтобы
    показать «Здравствуйте, ...». Также служит хорошим smoke-тестом авторизации.
    """
    return current_user
