"""Роутер /accounts: CRUD счетов пользователя.

  Все эндпоинты требуют авторизации через Depends(get_current_user) и
  фильтруют данные по owner_id текущего пользователя — защита от IDOR
  (Insecure Direct Object Reference, OWASP A01).

  Ошибка 404 при попытке доступа к чужому счёту намеренная: сообщать
  «счёт принадлежит другому пользователю» (403) — значит подтверждать,
  что счёт с таким id существует. 404 не утекает эту информацию.
  """
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
      "",
      response_model=AccountRead,
      status_code=status.HTTP_201_CREATED,
      summary="Создать счёт",
  )
async def create_account(
      payload: AccountCreate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Account:
      """Создать новый счёт для текущего пользователя.

      owner_id берётся из JWT, не из тела запроса — клиент не может
      создать счёт другому юзеру.
      """
      account = Account(
          owner_id=current_user.id,
          name=payload.name,
          balance=payload.balance,
          currency_code=payload.currency_code.upper(),
      )
      session.add(account)
      try:
          await session.commit()
      except IntegrityError:
          # Сработал UniqueConstraint(owner_id, name) — у юзера уже есть
          # счёт с таким именем. rollback обязателен, иначе сессия в
          # broken-состоянии и следующий запрос упадёт.
          await session.rollback()
          raise HTTPException(
              status_code=status.HTTP_409_CONFLICT,
              detail="Счёт с таким названием уже существует",
          ) from None
      await session.refresh(account)
      return account


@router.get(
      "",
      response_model=list[AccountRead],
      summary="Список счетов текущего пользователя",
  )
async def list_accounts(
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> list[Account]:
      """Все счета юзера, отсортированы по id (стабильный порядок)."""
      result = await session.scalars(
          select(Account)
          .where(Account.owner_id == current_user.id)
          .order_by(Account.id)
      )
      return list(result)


@router.get(
      "/{account_id}",
      response_model=AccountRead,
      summary="Получить счёт по id",
  )
async def get_account(
      account_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Account:
      account = await _get_owned_account_or_404(account_id, current_user, session)
      return account


@router.patch(
      "/{account_id}",
      response_model=AccountRead,
      summary="Обновить счёт (частично)",
  )
async def update_account(
      account_id: int,
      payload: AccountUpdate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Account:
      """Обновить только переданные поля.

      `model_dump(exclude_unset=True)` оставляет только те ключи, которые
      клиент явно прислал — не задетые поля сохраняют старое значение.
      """
      account = await _get_owned_account_or_404(account_id, current_user, session)
      update_data = payload.model_dump(exclude_unset=True)
      if "currency_code" in update_data and update_data["currency_code"] is not None:
          update_data["currency_code"] = update_data["currency_code"].upper()
      for field, value in update_data.items():
          setattr(account, field, value)
      try:
          await session.commit()
      except IntegrityError:
          await session.rollback()
          raise HTTPException(
              status_code=status.HTTP_409_CONFLICT,
              detail="Счёт с таким названием уже существует",
          ) from None
      await session.refresh(account)
      return account


@router.delete(
      "/{account_id}",
      status_code=status.HTTP_204_NO_CONTENT,
      summary="Удалить счёт",
  )
async def delete_account(
      account_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Response:
      """Удалить счёт. Связанные транзакции (когда они появятся) удалятся
      каскадно через ON DELETE CASCADE.
      """
      account = await _get_owned_account_or_404(account_id, current_user, session)
      await session.delete(account)
      await session.commit()
      # 204 No Content — стандартный ответ на успешный DELETE без тела.
      return Response(status_code=status.HTTP_204_NO_CONTENT)


  # ─── Внутренний хелпер ─────────────────────────────────────────────────────

async def _get_owned_account_or_404(
      account_id: int,
      current_user: User,
      session: AsyncSession,
  ) -> Account:
      """Получить счёт по id и проверить принадлежность текущему юзеру.

      Используется во всех эндпоинтах кроме create/list. Выносим в одну
      функцию, чтобы не дублировать проверку IDOR пять раз.
      """
      account = await session.get(Account, account_id)
      if account is None or account.owner_id != current_user.id:
          # Одинаковая ошибка для «не существует» и «чужой» — не утекаем
          # информацию о существовании чужих счетов.
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Счёт не найден",
          )
      return account