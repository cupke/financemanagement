"""Роутер /transactions: CRUD финансовых операций.

  Создание и удаление транзакции атомарно меняют balance связанного счёта
  (или двух счетов для перевода) в одной БД-транзакции. Если любая часть
  упадёт — БД остаётся консистентной (NFR-09 главы 1 ВКР).

  Сознательные упрощения MVP:
  - PATCH реализован ЧАСТИЧНО: правятся только «безопасные» поля, не
    влияющие на балансы — category_id, occurred_at, note. Изменение
    суммы / счёта / типа / счёта-получателя делается через DELETE
    старой операции + POST новой. Так мы по построению исключаем класс
    багов «рассинхрон баланса и истории», который возникал бы при
    полноценном UPDATE с пересчётом балансов «откатить старое →
    применить новое» (особенно для переводов и при смене kind).
  - Кросс-валютный перевод: если валюты счёта-источника и счёта-получателя
    различаются, списывается amount (в валюте источника), а зачисляется
    target_amount (в валюте получателя) — её вводит пользователь, т.к.
    банковский курс с комиссией отличается от курса ЦБ. Для одновалютного
    перевода target_amount не нужен (зачисляется тот же amount).

  ВАЖНО (модель «opening_balance + движения», см. vkr/02_design.md):
  Транзакция влияет на balance счёта ТОЛЬКО если её occurred_at
  >= account.opening_date. Транзакции «до opening_date» сохраняются
  в истории, но не двигают balance — их эффект уже сидит в opening_balance.
  Все изменения баланса в этом модуле обёрнуты в _apply_signed_delta_to_account,
  который инкапсулирует эту проверку.
  """
from datetime import datetime, timezone
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
from app.schemas.transaction import (
      TransactionCreate,
      TransactionRead,
      TransactionUpdate,
  )
# Логика проводки баланса вынесена в общий сервис (app.services.ledger),
# чтобы её одинаково переиспользовали и обычные операции, и движок
# повторяющихся операций (DRY). Импортируем под прежними _-именами,
# чтобы остальной код модуля остался без изменений.
from app.services.ledger import (
      apply_signed_delta_to_account as _apply_signed_delta_to_account,
      ensure_aware_utc as _ensure_aware_utc,
      signed_delta_for_source as _signed_delta_for_source,
  )


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
      # 0. Дата операции не должна быть в будущем. Иначе balance показывал бы
      #    «будущее» состояние как текущее — это семантически некорректно.
      #    Планирование будущих платежей — отдельная фича (бюджеты),
      #    а не наложение на текущий баланс.
      if _ensure_aware_utc(payload.occurred_at) > datetime.now(timezone.utc):
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Дата операции не может быть в будущем",
          )

      # 1. Источник — обязательно наш (защита от IDOR).
      source = await _get_owned_account_or_404(
          payload.account_id, current_user, session
      )

      # 1.5. Если клиент явно передал currency_code — он должен совпадать
      #      с валютой счёта. Иначе balance += amount даёт математическую
      #      бессмыслицу (рубли + доллары). Через UI этого не сделать,
      #      но API без проверки = silent corruption при импорте/интеграциях.
      if (
          payload.currency_code is not None
          and payload.currency_code.upper() != source.currency_code
      ):
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail=(
                  f"Валюта операции ({payload.currency_code.upper()}) не совпадает "
                  f"с валютой счёта ({source.currency_code}). Для разных валют "
                  f"используйте отдельные счета."
              ),
          )

      # 2. Категория, если задана — обязательно наша, и её kind должен
      #    совпадать с kind транзакции (расходную транзакцию нельзя отнести
      #    к доходной категории). 400 (а не 404) — это валидация входа.
      if payload.category_id is not None:
            category = await session.get(Category, payload.category_id)
            if category is None or category.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Категория не найдена",
                )
            # Для transfer категория уже отвергается схемой и БД-CHECK'ом.
            # Здесь явная проверка соответствия kind для income/expense.
            if payload.kind in ("income", "expense") and category.kind != payload.kind:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Категория «{category.name}» предназначена для "
                        f"{category.kind}, а операция — {payload.kind}."
                    ),
                )

      # 3. Для перевода — получатель обязательно наш. Если валюты совпадают —
      #    зачисляется тот же amount (target_amount хранить не нужно). Если
      #    различаются — это кросс-валютный перевод: зачисляется введённый
      #    пользователем target_amount (в валюте получателя).
      target: Account | None = None
      # credited_amount — сколько зачислится на получателя; stored_target_amount
      # — что положим в колонку target_amount (NULL для одновалютных переводов).
      credited_amount: Decimal = payload.amount
      stored_target_amount: Decimal | None = None
      if payload.kind == "transfer":
          # transfer_account_id точно не None: проверено model_validator'ом схемы.
          assert payload.transfer_account_id is not None
          target = await _get_owned_account_or_404(
              payload.transfer_account_id, current_user, session
          )
          if target.currency_code == source.currency_code:
              # Одновалютный перевод. target_amount тут — лишнее поле; принимаем
              # только если он не противоречит amount, иначе — понятная 400
              # (а не тихое игнорирование переданного значения).
              if (
                  payload.target_amount is not None
                  and payload.target_amount != payload.amount
              ):
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail=(
                          "Для перевода в одной валюте сумма зачисления равна "
                          "сумме списания — не указывайте её отдельно."
                      ),
                  )
              credited_amount = payload.amount
              stored_target_amount = None
          else:
              # Кросс-валютный перевод: сумма зачисления обязательна.
              if payload.target_amount is None:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail=(
                          f"Перевод между счетами разных валют ({source.currency_code} "
                          f"→ {target.currency_code}): укажите сумму зачисления "
                          f"в {target.currency_code} (поле target_amount)."
                      ),
                  )
              credited_amount = payload.target_amount
              stored_target_amount = payload.target_amount

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
          target_amount=stored_target_amount,
          currency_code=currency,
          category_id=payload.category_id,
          transfer_account_id=payload.transfer_account_id,
          occurred_at=payload.occurred_at,
          note=payload.note,
      )
      session.add(transaction)

      # delta_source: знаковое изменение баланса счёта-источника при создании.
      delta_source = _signed_delta_for_source(payload.kind, payload.amount)

      # Применяем delta к balance, но только если occurred_at >= opening_date
      # источника. Для ретро-операций «до opening_date» balance не меняется —
      # их эффект уже учтён в opening_balance (см. vkr/02_design.md).
      # UPDATE атомарен на уровне строки в Postgres — защита от lost update.
      await _apply_signed_delta_to_account(
          source, delta_source, payload.occurred_at, session
      )

      if payload.kind == "transfer":
          assert target is not None  # установлен выше
          # Для перевода — независимая проверка для счёта-получателя:
          # его opening_date может отличаться от opening_date источника.
          # Зачисляем credited_amount: для одновалютного — это amount, для
          # кросс-валютного — target_amount в валюте получателя.
          await _apply_signed_delta_to_account(
              target, credited_amount, payload.occurred_at, session
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


@router.patch(
      "/{transaction_id}",
      response_model=TransactionRead,
      summary="Частично обновить транзакцию (только безопасные поля)",
  )
async def update_transaction(
      transaction_id: int,
      payload: TransactionUpdate,
      current_user: User = Depends(get_current_user),
      session: AsyncSession = Depends(get_session),
  ) -> Transaction:
      """Обновить категорию / дату / заметку транзакции.

      Балансы счетов НЕ трогаются — это инвариант, защищающий от
      рассинхрона истории и сумм на счетах. Чтобы поправить amount,
      account, kind или transfer_account_id — клиент удаляет старую
      операцию (DELETE откатит балансы) и создаёт новую (POST применит
      новые балансы). Двухшаговый сценарий по построению атомарен
      на уровне каждого шага.

      Используем model_fields_set, а не значения атрибутов, чтобы
      различать «поле не передано» (не трогаем) и «поле передано null»
      (например, снять категорию).
      """
      transaction = await _get_owned_transaction_or_404(
          transaction_id, current_user, session
      )

      fields = payload.model_fields_set

      if "category_id" in fields:
          if payload.category_id is not None:
              # Перевод не может иметь категорию (CHECK на БД-уровне).
              # Здесь — понятный 400 вместо 500 от БД.
              if transaction.kind == "transfer":
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail="Перевод не может иметь категорию",
                  )
              category = await session.get(Category, payload.category_id)
              if category is None or category.owner_id != current_user.id:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail="Категория не найдена",
                  )
              # kind транзакции в PATCH не меняется, поэтому достаточно
              # сверить с текущим kind операции.
              if category.kind != transaction.kind:
                  raise HTTPException(
                      status_code=status.HTTP_400_BAD_REQUEST,
                      detail=(
                          f"Категория «{category.name}» предназначена для "
                          f"{category.kind}, а операция — {transaction.kind}."
                      ),
                  )
          transaction.category_id = payload.category_id

      if "occurred_at" in fields:
          # occurred_at обнулять нельзя — поле NOT NULL.
          if payload.occurred_at is None:
              raise HTTPException(
                  status_code=status.HTTP_400_BAD_REQUEST,
                  detail="occurred_at не может быть null",
              )
          # И не может быть в будущем — то же правило, что в POST.
          if _ensure_aware_utc(payload.occurred_at) > datetime.now(timezone.utc):
              raise HTTPException(
                  status_code=status.HTTP_400_BAD_REQUEST,
                  detail="Дата операции не может быть в будущем",
              )
          # Если новая дата пересекает границу opening_date счёта —
          # нужно скорректировать balance: убрать delta (если ушла «до»)
          # или добавить (если пришла «после»). Делаем ДО изменения
          # самого поля, чтобы передать в helper и старое, и новое значения.
          old_occurred_at = transaction.occurred_at
          new_occurred_at = payload.occurred_at
          # Сравниваем по UTC-моменту, а не по «голому» значению с tzinfo.
          # Иначе naive 17:08 и aware 17:08+00:00 считались бы разными
          # и мы зря триггерили бы _shift_balance.
          if _ensure_aware_utc(old_occurred_at) != _ensure_aware_utc(
              new_occurred_at
          ):
              source_account = await session.get(Account, transaction.account_id)
              assert source_account is not None
              delta_source = _signed_delta_for_source(
                  transaction.kind, transaction.amount
              )
              await _shift_balance_for_date_change(
                  source_account,
                  delta_source,
                  old_occurred_at,
                  new_occurred_at,
                  session,
              )
              if transaction.kind == "transfer":
                  target_account = await session.get(
                      Account, transaction.transfer_account_id
                  )
                  assert target_account is not None
                  # Получателю при переводе зачислялся credited amount:
                  # target_amount для кросс-валютного, иначе amount.
                  credited = (
                      transaction.target_amount
                      if transaction.target_amount is not None
                      else transaction.amount
                  )
                  await _shift_balance_for_date_change(
                      target_account,
                      credited,
                      old_occurred_at,
                      new_occurred_at,
                      session,
                  )
          transaction.occurred_at = new_occurred_at

      if "note" in fields:
          # note nullable — null = снять заметку. Пустую строку
          # тоже трактуем как «снять», чтобы не хранить '' в БД.
          transaction.note = payload.note if payload.note else None

      await session.commit()
      await session.refresh(transaction)
      return transaction


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
      дополнительно вычитает зачисленную сумму из получателя (target_amount
      для кросс-валютного, иначе amount). Всё в одной БД-транзакции.
      """
      transaction = await _get_owned_transaction_or_404(
          transaction_id, current_user, session
      )

      # Загружаем счёт-источник как объект (а не апдейтим по id),
      # чтобы проверить opening_date в _apply_signed_delta_to_account.
      source_account = await session.get(Account, transaction.account_id)
      assert source_account is not None  # FK + IDOR-проверка выше гарантируют

      # Зеркальный эффект: применяем противоположный delta. Условие про
      # opening_date то же: если транзакция была «до opening_date»,
      # она не вкладывалась в balance — и убирать тоже нечего.
      delta_source = -_signed_delta_for_source(transaction.kind, transaction.amount)
      await _apply_signed_delta_to_account(
          source_account, delta_source, transaction.occurred_at, session
      )

      if transaction.kind == "transfer":
          target_account = await session.get(Account, transaction.transfer_account_id)
          assert target_account is not None
          # Откатываем именно ту сумму, что зачисляли получателю.
          credited = (
              transaction.target_amount
              if transaction.target_amount is not None
              else transaction.amount
          )
          await _apply_signed_delta_to_account(
              target_account,
              -credited,
              transaction.occurred_at,
              session,
          )

      await session.delete(transaction)
      await session.commit()
      return Response(status_code=status.HTTP_204_NO_CONTENT)


  # ─── Внутренние хелперы ─────────────────────────────────────────────────
  #
  # _ensure_aware_utc, _apply_signed_delta_to_account и _signed_delta_for_source
  # переехали в app.services.ledger (импортированы выше под теми же именами) —
  # чтобы движок повторяющихся операций использовал ту же логику без копипасты.


async def _shift_balance_for_date_change(
      account: Account,
      delta: Decimal,
      old_occurred_at: datetime,
      new_occurred_at: datetime,
      session: AsyncSession,
  ) -> None:
      """Скорректировать account.balance при смене даты транзакции через PATCH.

      delta — знаковое изменение balance, которое транзакция применяет,
      когда активна (т.е. occurred_at >= opening_date).

      4 случая:
      - был активен, остался активен  → delta уже применён, ничего не делаем.
      - был неактивен, остался неактивен → delta не применялся, ничего не делаем.
      - был активен, стал неактивен    → откатываем (применяем -delta).
      - был неактивен, стал активен    → применяем (применяем +delta).

      Это инкрементальная альтернатива recompute_account_balance —
      быстрее на больших объёмах транзакций (без полного scan'а).
      """
      old_active = _ensure_aware_utc(old_occurred_at) >= account.opening_date
      new_active = _ensure_aware_utc(new_occurred_at) >= account.opening_date
      if old_active == new_active:
          return
      sign = 1 if new_active else -1
      await session.execute(
          update(Account)
          .where(Account.id == account.id)
          .values(balance=Account.balance + sign * delta)
      )


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
