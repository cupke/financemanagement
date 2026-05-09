"""Роутер /categories: CRUD категорий пользователя.

  Категории иерархические через parent_id. Все эндпоинты требуют авторизации
  и фильтруют по owner_id (защита от IDOR — OWASP A01). Дополнительно при
  создании/обновлении проверяем, что указанный parent_id принадлежит тому же
  юзеру: иначе можно было бы вложить свою категорию в чужое поддерево.
  """
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.category import Category
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate


router = APIRouter(prefix="/categories", tags=["categories"])


@router.post(
      "",
      response_model=CategoryRead,
      status_code=status.HTTP_201_CREATED,
      summary="Создать категорию",
  )
async def create_category(
      payload: CategoryCreate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Category:
      # Если задан родитель — проверяем, что он наш. Без этой проверки можно
      # было бы создать категорию-потомка в чужом дереве.
      if payload.parent_id is not None:
          await _verify_parent_owned(payload.parent_id, current_user, session)

      category = Category(
          owner_id=current_user.id,
          name=payload.name,
          parent_id=payload.parent_id,
      )
      session.add(category)
      try:
          await session.commit()
      except IntegrityError:
          # Сработал UNIQUE INDEX (owner_id, parent_id, name).
          await session.rollback()
          raise HTTPException(
              status_code=status.HTTP_409_CONFLICT,
              detail="Категория с таким именем уже существует на этом уровне",
          ) from None
      await session.refresh(category)
      return category


@router.get(
      "",
      response_model=list[CategoryRead],
      summary="Список категорий текущего пользователя",
  )
async def list_categories(
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> list[Category]:
      """Все категории юзера, плоский список с parent_id. Дерево строит клиент."""
      result = await session.scalars(
          select(Category)
          .where(Category.owner_id == current_user.id)
          .order_by(Category.id)
      )
      return list(result)


@router.get(
      "/{category_id}",
      response_model=CategoryRead,
      summary="Получить категорию по id",
  )
async def get_category(
      category_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Category:
      return await _get_owned_category_or_404(category_id, current_user, session)


@router.patch(
      "/{category_id}",
      response_model=CategoryRead,
      summary="Обновить категорию",
  )
async def update_category(
      category_id: int,
      payload: CategoryUpdate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Category:
      category = await _get_owned_category_or_404(category_id, current_user, session)
      # exclude_unset=True — оставляет только явно переданные поля. Это
      # позволяет различать «не трогать parent_id» и «сделать корневой» (null).
      update_data = payload.model_dump(exclude_unset=True)

      # Защита от собственного родителя. Глубокие циклы (a→b→a) пока не ловим —
      # потребовался бы рекурсивный CTE-обход. Для MVP не критично.
      if "parent_id" in update_data:
          new_parent = update_data["parent_id"]
          if new_parent is not None:
              if new_parent == category.id:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail="Категория не может быть родителем сама себе",
                  )
              await _verify_parent_owned(new_parent, current_user, session)

      for field, value in update_data.items():
          setattr(category, field, value)

      try:
          await session.commit()
      except IntegrityError:
          await session.rollback()
          raise HTTPException(
              status_code=status.HTTP_409_CONFLICT,
              detail="Категория с таким именем уже существует на этом уровне",
          ) from None
      await session.refresh(category)
      return category


@router.delete(
      "/{category_id}",
      status_code=status.HTTP_204_NO_CONTENT,
      summary="Удалить категорию",
  )
async def delete_category(
      category_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Response:
      """Удалить категорию. Все дети (включая глубоких потомков) удалятся
      каскадно через ON DELETE CASCADE на FK parent_id.

      На фронте перед удалением стоит запрашивать подтверждение, если у
      категории есть потомки — иначе пользователь может случайно стереть
      большую часть классификации.
      """
      category = await _get_owned_category_or_404(category_id, current_user, session)
      await session.delete(category)
      await session.commit()
      return Response(status_code=status.HTTP_204_NO_CONTENT)


  # ─── Внутренние хелперы ─────────────────────────────────────────────────

async def _get_owned_category_or_404(
      category_id: int,
      current_user: User,
      session: AsyncSession,
  ) -> Category:
      """Получить категорию по id и проверить, что она принадлежит юзеру."""
      category = await session.get(Category, category_id)
      if category is None or category.owner_id != current_user.id:
          # Один и тот же 404 для «не существует» и «чужая» — не утекаем
          # информацию о существовании чужих категорий.
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Категория не найдена",
          )
      return category


async def _verify_parent_owned(
      parent_id: int,
      current_user: User,
      session: AsyncSession,
  ) -> None:
      """Убедиться, что родительская категория существует и принадлежит юзеру.

      Используется при создании и обновлении категории. 400, не 404 — потому
      что это ошибка валидации тела запроса, а не запрашиваемого ресурса.
      """
      parent = await session.get(Category, parent_id)
      if parent is None or parent.owner_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Родительская категория не найдена",
          )