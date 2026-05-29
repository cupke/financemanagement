"""Роутер /accounts: CRUD счетов пользователя.

  Все эндпоинты требуют авторизации через Depends(get_current_user) и
  фильтруют данные по owner_id текущего пользователя — защита от IDOR
  (Insecure Direct Object Reference, OWASP A01).

  Ошибка 404 при попытке доступа к чужому счёту намеренная: сообщать
  «счёт принадлежит другому пользователю» (403) — значит подтверждать,
  что счёт с таким id существует. 404 не утекает эту информацию.
  """
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.transaction import Transaction
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
      # Если клиент не передал opening_date — берём «сейчас». Делаем это
      # в роутере (а не в Pydantic-default), чтобы получить актуальный
      # NOW() на момент запроса, а не на момент импорта модуля.
      opening_date = payload.opening_date or datetime.now(timezone.utc)
      account = Account(
            owner_id=current_user.id,
            name=payload.name,
            kind=payload.kind,
            note=payload.note,
            opening_balance=payload.opening_balance,
            opening_date=opening_date,
            # У нового счёта транзакций ещё нет → balance = opening_balance.
            # При первом POST транзакции balance будет пересчитан или
            # инкрементально обновлён в transactions.py.
            balance=payload.opening_balance,
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
      # Не даём занулить opening_balance/opening_date — оба NOT NULL.
      if "opening_balance" in update_data and update_data["opening_balance"] is None:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="opening_balance не может быть null",
          )
      if "opening_date" in update_data and update_data["opening_date"] is None:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="opening_date не может быть null",
          )

      # Сохраним, нужно ли пересчитывать balance: только если меняется
      # opening_balance или opening_date (от них зависит формула).
      # Изменение currency_code на пересчёт не влияет — currency_code
      # транзакций фиксируется на момент создания (snapshot).
      needs_recompute = (
          "opening_balance" in update_data or "opening_date" in update_data
      )

      for field, value in update_data.items():
          setattr(account, field, value)

      if needs_recompute:
          await recompute_account_balance(account, session)

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
      """Удалить счёт. Связанные транзакции каскадно удалятся через
      ON DELETE CASCADE.

      ВАЖНО: если у счёта были переводы, balance ДРУГИХ счетов (источников
      входящих переводов и получателей исходящих) был ранее изменён на
      сумму этих переводов. После каскадного удаления транзакций их balance
      «зависнет» с эффектом несуществующих операций — рассинхрон кеша
      с источником правды (та же категория ошибки, что была с opening_balance).

      Поэтому: собираем id затронутых счетов ДО удаления, делаем delete +
      flush (триггерим CASCADE), потом пересчитываем balance каждого
      из связанных через recompute_account_balance.
      """
      account = await _get_owned_account_or_404(account_id, current_user, session)

      # 1. Найти счета-получатели наших исходящих переводов.
      outgoing_targets_stmt = (
          select(Transaction.transfer_account_id)
          .where(
              Transaction.account_id == account.id,
              Transaction.kind == "transfer",
              Transaction.transfer_account_id.is_not(None),
          )
          .distinct()
      )
      outgoing_targets = (await session.scalars(outgoing_targets_stmt)).all()

      # 2. Найти счета-источники входящих к нам переводов.
      incoming_sources_stmt = (
          select(Transaction.account_id)
          .where(
              Transaction.transfer_account_id == account.id,
              Transaction.kind == "transfer",
          )
          .distinct()
      )
      incoming_sources = (await session.scalars(incoming_sources_stmt)).all()

      related_ids = set(outgoing_targets) | set(incoming_sources)
      related_ids.discard(account.id)  # себя пересчитывать не нужно — нас не будет

      # 3. Удалить + сразу flush, чтобы CASCADE сработал ДО пересчёта.
      #    Иначе SUM в recompute захватит ещё не удалённые транзакции
      #    и balance связанных счетов не изменится.
      await session.delete(account)
      await session.flush()

      # 4. Пересчитать balance каждого связанного счёта.
      for related_id in related_ids:
          related = await session.get(Account, related_id)
          if related is not None:  # был наш и не удалился — проверка-страховка
              await recompute_account_balance(related, session)

      await session.commit()
      # 204 No Content — стандартный ответ на успешный DELETE без тела.
      return Response(status_code=status.HTTP_204_NO_CONTENT)


  # ─── Хелпер пересчёта баланса ──────────────────────────────────────────────


async def recompute_account_balance(
      account: Account, session: AsyncSession
  ) -> None:
      """Полный пересчёт account.balance по формуле:

          balance = opening_balance
                  + Σ signed_amount транзакций где account_id = account.id
                                                  AND occurred_at >= opening_date
                  + Σ amount транзакций-переводов где transfer_account_id = account.id
                                                  AND occurred_at >= opening_date

      Используется в:
      - PATCH /accounts/{id} при изменении opening_balance или opening_date,
      - PATCH /transactions/{id} при пересечении occurred_at границы opening_date
        (см. transactions.py).

      Для обычных POST/DELETE транзакций мы НЕ делаем полный пересчёт —
      там работает инкрементальный +delta / -delta (быстрее на большом объёме).
      Полный пересчёт — для редких операций, где состояние сложное.

      Не вызывает commit. Caller отвечает за транзакционность.
      """
      # 1. Эффект транзакций, где счёт — источник.
      #    income → +amount; expense, transfer → -amount.
      #    Σ берётся через SQL CASE, чтобы не тащить все строки в Python.
      source_sum_stmt = select(
          func.coalesce(
              func.sum(
                  case(
                      (Transaction.kind == "income", Transaction.amount),
                      else_=-Transaction.amount,
                  )
              ),
              Decimal("0"),
          )
      ).where(
          Transaction.account_id == account.id,
          Transaction.occurred_at >= account.opening_date,
      )
      source_sum = await session.scalar(source_sum_stmt) or Decimal("0")

      # 2. Эффект переводов, где счёт — получатель. Зачисляется target_amount
      #    (сумма в валюте получателя для кросс-валютного перевода); для
      #    одновалютного перевода target_amount = NULL → берём amount.
      #    Без coalesce кросс-валютный перевод зачислил бы сумму в валюте
      #    источника — рассинхрон баланса (инкрементальный путь в transactions.py
      #    уже использует credited = target_amount|amount, см. delete/PATCH).
      target_sum_stmt = select(
          func.coalesce(
              func.sum(
                  func.coalesce(Transaction.target_amount, Transaction.amount)
              ),
              Decimal("0"),
          )
      ).where(
          Transaction.transfer_account_id == account.id,
          Transaction.kind == "transfer",
          Transaction.occurred_at >= account.opening_date,
      )
      target_sum = await session.scalar(target_sum_stmt) or Decimal("0")

      account.balance = account.opening_balance + source_sum + target_sum


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