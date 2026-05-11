"""Роутер /users: эндпоинты, привязанные к учётной записи."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_session
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


@router.delete(
      "/me",
      status_code=status.HTTP_204_NO_CONTENT,
      summary="Удалить учётную запись текущего пользователя",
  )
async def delete_me(
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Response:
      """Самостоятельное удаление аккаунта (право на забвение).

      Реализует требование ст. 19 п. 2 № 152-ФЗ — пользователь может в любой
      момент уничтожить свои персональные данные. Каскадно через ON DELETE CASCADE
      на FK всех зависимых таблиц удаляются:
      - все счета пользователя (accounts);
      - все категории и их потомки (categories);
      - все транзакции (transactions).

      Курсы валют (exchange_rates) — общие справочные данные, не привязаны к юзеру,
      остаются. После удаления JWT-токен на клиенте становится бесполезен — следующий
      запрос с ним вернёт 401 в `get_current_user` (пользователя с этим id уже нет).

      Возвращает 204 No Content. Клиент должен очистить локальный токен и
      перенаправить пользователя на страницу логина.
      """
      await session.delete(current_user)
      await session.commit()
      return Response(status_code=status.HTTP_204_NO_CONTENT)