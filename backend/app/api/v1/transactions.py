"""Роутер /transactions: CRUD финансовых операций.

  Создание и удаление транзакции атомарно меняют balance связанного счёта
  (или двух счетов для перевода) в одной БД-транзакции. Если любая часть
  упадёт — БД остаётся консистентной (NFR-09 главы 1 ВКР).

  Сознательные упрощения MVP:
  - PATCH не реализован: смена amount/account/kind через DELETE + новый POST.
    Полноценный UPDATE требовал бы пересчёта двух счетов в обратную сторону
    и применения новых значений — хрупко, объёма как у самого CRUD.
  - Перевод только в одной валюте. Кросс-валютные переводы — после интеграции
    курсов ЦБ РФ.
  """
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.category import Category
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.transaction import TransactionCreate, TransactionRead


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post(
      "",
      response_model=TransactionRead,
      status_code=status.HTTP_201_CREATED,
      summary="Создать транзакцию (атомарно меняет балансы)",
  )
async def create_transaction(
      payload: TransactionCreate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Transaction:
      # 1. Источник — обязательно наш (защита от IDOR).
      source = await _get_owned_account_or_404(
          payload.account_id, current_user, session
      )

      # 2. Категория, если задана — обязательно наша. 400 (а не 404), потому
      #    что это валидация входа, а не отсутствующий запрашиваемый ресурс.
      if payload.category_id is not None:
          category = await session.get(Category, payload.category_id)
          if category is None or category.owner_id != current_user.id:
              raise HTTPException(
                  status_code=status.HTTP_400_BAD_REQUEST,
                  detail="Категория не найдена",
              )

      # 3. Для перевода — получатель обязательно наш; одновалютность.
      target: Account | None = None
      if payload.kind == "transfer":
          # transfer_account_id точно не None: проверено model_validator'ом схемы.
          assert payload.transfer_account_id is not None
          target = await _get_owned_account_or_404(
              payload.transfer_account_id, current_user, session
          )
          if target.currency_code != source.currency_code:
              raise HTTPException(
                  status_code=status.HTTP_400_BAD_REQUEST,
                  detail=(
                      "Перевод между счетами разных валют пока не поддерживается. "
                      "Эта функция появится вместе с интеграцией курсов ЦБ РФ."
                  ),
              )

      # 4. Валюта операции — snapshot валюты счёта-источника, если клиент
      #    не передал явно. .upper() для нормализации (RUB / Rub / rub).
      currency = (payload.currency_code or source.currency_code).upper()

      # 5. Создание + пересчёт балансов в одной БД-транзакции. SQLAlchemy
      #    сессия уже в неявной транзакции с момента первого запроса; нам
      #    нужно лишь не вызывать commit между шагами и вызвать его в конце.
      transaction = Transaction(
          owner_id=current_user.id,
          account_id=payload.account_id,
          kind=payload.kind,
          amount=payload.amount,
          currency_code=currency,
          category_id=payload.category_id,
          transfer_account_id=payload.transfer_account_id,
          occurred_at=payload.occurred_at,
          note=payload.note,
      )
      session.add(transaction)

      # delta_source: знаковое изменение баланса счёта-источника при создании.
      delta_source = _signed_delta_for_source(payload.kind, payload.amount)

      # UPDATE ... SET balance = balance + :delta — атомарно на уровне строки
      # в Postgres: даже при двух параллельных POST'ах оба изменения применятся
      # без потерянного обновления (lost update). Это лучше, чем читать balance
      # в Python и записывать новое значение.
      await session.execute(
          update(Account)
          .where(Account.id == source.id)
          .values(balance=Account.balance + delta_source)
      )

      if payload.kind == "transfer":
          assert target is not None  # установлен выше
          await session.execute(
              update(Account)
              .where(Account.id == target.id)
              .values(balance=Account.balance + payload.amount)
          )

      await session.commit()
      await session.refresh(transaction)
      return transaction


@router.get(
      "",
      response_model=list[TransactionRead],
      summary="Список транзакций с фильтрами",
  )
async def list_transactions(
      account_id: int | None = Query(default=None, description="Фильтр по счёту"),
      category_id: int | None = Query(default=None, description="Фильтр по категории"),
      kind: Literal["income", "expense", "transfer"] | None = Query(default=None),
      from_date: datetime | None = Query(default=None, description="С (включительно)"),
      to_date: datetime | None = Query(default=None, description="По (включительно)"),
      limit: int = Query(default=50, ge=1, le=500),
      offset: int = Query(default=0, ge=0),
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> list[Transaction]:
      """Транзакции юзера с фильтрами и пагинацией. Свежие — первыми."""
      stmt = (
          select(Transaction)
          .where(Transaction.owner_id == current_user.id)
          .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
          .limit(limit)
          .offset(offset)
      )
      # Note: фильтр account_id ловит только те операции, где счёт является
      # источником (account_id). Переводы-получатели сюда не попадут.
      # «Все операции, затронувшие счёт» — отдельный отчёт, добавим при
      # необходимости через OR transfer_account_id.
      if account_id is not None:
          stmt = stmt.where(Transaction.account_id == account_id)
      if category_id is not None:
          stmt = stmt.where(Transaction.category_id == category_id)
      if kind is not None:
          stmt = stmt.where(Transaction.kind == kind)
      if from_date is not None:
          stmt = stmt.where(Transaction.occurred_at >= from_date)
      if to_date is not None:
          stmt = stmt.where(Transaction.occurred_at <= to_date)

      result = await session.scalars(stmt)
      return list(result)


@router.get(
      "/{transaction_id}",
      response_model=TransactionRead,
      summary="Получить транзакцию по id",
  )
async def get_transaction(
      transaction_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Transaction:
      return await _get_owned_transaction_or_404(
          transaction_id, current_user, session
      )


@router.delete(
      "/{transaction_id}",
      status_code=status.HTTP_204_NO_CONTENT,
      summary="Удалить транзакцию (с откатом балансов)",
  )
async def delete_transaction(
      transaction_id: int,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Response:
      """Удалить транзакцию и зеркально откатить эффект на балансах счетов.

      DELETE применяет противоположный delta к источнику; для перевода —
      дополнительно вычитает amount из получателя. Всё в одной БД-транзакции.
      """
      transaction = await _get_owned_transaction_or_404(
          transaction_id, current_user, session
      )

      # Зеркальный эффект: применяем противоположный delta.
      delta_source = -_signed_delta_for_source(transaction.kind, transaction.amount)
      await session.execute(
          update(Account)
          .where(Account.id == transaction.account_id)
          .values(balance=Account.balance + delta_source)
      )
      if transaction.kind == "transfer":
          await session.execute(
              update(Account)
              .where(Account.id == transaction.transfer_account_id)
              .values(balance=Account.balance - transaction.amount)
          )

      await session.delete(transaction)
      await session.commit()
      return Response(status_code=status.HTTP_204_NO_CONTENT)


  # ─── Внутренние хелперы ─────────────────────────────────────────────────


def _signed_delta_for_source(kind: str, amount: Decimal) -> Decimal:
      """Знаковое изменение баланса счёта-источника при СОЗДАНИИ транзакции.

      income → +amount (деньги пришли).
      expense → -amount (деньги ушли).
      transfer → -amount (на источнике уменьшается; получатель обновляется
                          отдельным UPDATE'ом в роутере).

      При DELETE применяется противоположный знак (см. delete_transaction).
      """
      if kind == "income":
          return amount
      return -amount


async def _get_owned_account_or_404(
      account_id: int,
      current_user: User,
      session: AsyncSession,
  ) -> Account:
      """То же, что в accounts.py — продублировано здесь, чтобы не создавать
      cross-роутерные импорты ради одной хелпер-функции.
      """
      account = await session.get(Account, account_id)
      if account is None or account.owner_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Счёт не найден",
          )
      return account


async def _get_owned_transaction_or_404(
      transaction_id: int,
      current_user: User,
      session: AsyncSession,
  ) -> Transaction:
      transaction = await session.get(Transaction, transaction_id)
      if transaction is None or transaction.owner_id != current_user.id:
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Транзакция не найдена",
          )
      return transaction