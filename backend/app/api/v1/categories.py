"""Роутер /categories: CRUD категорий пользователя.

  Категории иерархические через parent_id. Все эндпоинты требуют авторизации
  и фильтруют по owner_id (защита от IDOR — OWASP A01). Дополнительно при
  создании/обновлении проверяем, что указанный parent_id принадлежит тому же
  юзеру: иначе можно было бы вложить свою категорию в чужое поддерево.

  Правило kind: дочерняя категория наследует kind родителя. Это обеспечивает
  семантическую целостность (нельзя «расход» вложить в «доход»).
  """
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
      # Если задан родитель — проверяем, что он наш и того же kind.
      # Без проверки kind можно было бы создать дочернюю «доходную» категорию
      # в «расходном» родителе, что семантически неверно.
      if payload.parent_id is not None:
          parent = await _verify_parent_owned(payload.parent_id, current_user, session)
          if parent.kind != payload.kind:
              raise HTTPException(
                  status_code=status.HTTP_400_BAD_REQUEST,
                  detail=(
                      f"Тип подкатегории ({payload.kind}) должен совпадать с "
                      f"типом родителя ({parent.kind})."
                  ),
              )
  
      category = Category(
          owner_id=current_user.id,
          name=payload.name,
          kind=payload.kind,
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
      kind: Literal["income", "expense"] | None = Query(
          default=None,
          description="Фильтр по типу. Без параметра — все категории.",
      ),
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> list[Category]:
      """Категории юзера, плоский список с parent_id. Дерево строит клиент.
  
      Опциональный фильтр по kind — для формы транзакции, где для расхода
      показываем только расходные категории, для дохода — только доходные.
      """
      stmt = (
          select(Category)
          .where(Category.owner_id == current_user.id)
          .order_by(Category.id)
      )
      if kind is not None:
          stmt = stmt.where(Category.kind == kind)

      result = await session.scalars(stmt)
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
          new_parent_id = update_data["parent_id"]
          if new_parent_id is not None:
              if new_parent_id == category.id:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail="Категория не может быть родителем сама себе",
                  )
              new_parent = await _verify_parent_owned(
                  new_parent_id, current_user, session
              )
              if new_parent.kind != category.kind:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail=(
                          f"Тип категории ({category.kind}) должен совпадать "
                          f"с типом нового родителя ({new_parent.kind})."
                      ),
                  )
  
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
  ) -> Category:
      """Убедиться, что родительская категория существует и принадлежит юзеру.

      Возвращает объект родителя (чтобы вызывающий мог проверить parent.kind).
      400 (не 404) — это ошибка валидации тела запроса, а не отсутствующий
      запрашиваемый ресурс.
      """
      parent = await session.get(Category, parent_id)
      if parent is None or parent.owner_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Родительская категория не найдена",
          )
      return parent