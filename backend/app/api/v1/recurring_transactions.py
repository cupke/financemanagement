"""Роутер /recurring-transactions: правила автоповтора операций + движок их генерации.

CRUD правил + эндпоинт POST /run, который «доматериализует» все назревшие
операции (см. docstring модели RecurringTransaction про catch-up без планировщика).

Логику проводки баланса берём из общего сервиса app.services.ledger — той же,
что использует роутер /transactions (DRY). Арифметику дат — из
app.services.recurrence.

Все эндпоинты требуют авторизации и фильтруют по owner_id (защита от IDOR,
OWASP A01). Паттерн 404-вместо-403 — как в остальных роутерах.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.category import Category
from app.db.models.recurring_transaction import RecurringTransaction
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.recurring_transaction import (
    RecurringTransactionCreate,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
    RunResult,
)
from app.services.ledger import (
    apply_signed_delta_to_account,
    ensure_aware_utc,
    signed_delta_for_source,
)
from app.services.recurrence import MAX_OCCURRENCES_PER_RUN, next_occurrence

router = APIRouter(prefix="/recurring-transactions", tags=["recurring"])


@router.post(
    "",
    response_model=RecurringTransactionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать правило автоповтора операции",
)
async def create_recurring(
    payload: RecurringTransactionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringTransaction:
    # 1. Счёт-источник — обязательно наш (защита от IDOR).
    source = await _get_owned_account_or_404(
        payload.account_id, current_user, session
    )

    # 1.5. Если явно передан currency_code — должен совпадать с валютой счёта.
    if (
        payload.currency_code is not None
        and payload.currency_code.upper() != source.currency_code
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Валюта правила ({payload.currency_code.upper()}) не совпадает "
                f"с валютой счёта ({source.currency_code})."
            ),
        )

    # 2. Категория, если задана — наша и совпадает по kind с операцией.
    if payload.category_id is not None:
        category = await session.get(Category, payload.category_id)
        if category is None or category.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Категория не найдена",
            )
        if payload.kind in ("income", "expense") and category.kind != payload.kind:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Категория «{category.name}» предназначена для "
                    f"{category.kind}, а операция — {payload.kind}."
                ),
            )

    # 3. Для перевода — получатель наш и одной валюты с источником.
    if payload.kind == "transfer":
        assert payload.transfer_account_id is not None  # гарантирует схема
        target = await _get_owned_account_or_404(
            payload.transfer_account_id, current_user, session
        )
        if target.currency_code != source.currency_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Перевод между счетами разных валют пока не поддерживается."
                ),
            )

    currency = (payload.currency_code or source.currency_code).upper()

    rule = RecurringTransaction(
        owner_id=current_user.id,
        name=payload.name,
        kind=payload.kind,
        account_id=payload.account_id,
        amount=payload.amount,
        currency_code=currency,
        category_id=payload.category_id,
        transfer_account_id=payload.transfer_account_id,
        note=payload.note,
        frequency=payload.frequency,
        interval=payload.interval,
        start_at=payload.start_at,
        end_at=payload.end_at,
        # Курсор движка стартует с первой даты — первый /run догенерит всё
        # назревшее от start_at до «сейчас».
        next_run_at=payload.start_at,
        is_active=True,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.get(
    "",
    response_model=list[RecurringTransactionRead],
    summary="Список правил автоповтора",
)
async def list_recurring(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RecurringTransaction]:
    """Все правила пользователя. Активные — первыми, дальше по ближайшему запуску."""
    stmt = (
        select(RecurringTransaction)
        .where(RecurringTransaction.owner_id == current_user.id)
        .order_by(
            RecurringTransaction.is_active.desc(),
            RecurringTransaction.next_run_at.asc(),
            RecurringTransaction.id.desc(),
        )
    )
    result = await session.scalars(stmt)
    return list(result)


@router.post(
    "/run",
    response_model=RunResult,
    summary="Догенерировать все назревшие операции по правилам",
)
async def run_due(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunResult:
    """Материализовать все операции, чьё время уже наступило.

    Идемпотентно по смыслу: повторный вызов сразу ничего не создаст, пока не
    наступит срок следующей операции. Фронт дёргает этот эндпоинт при заходе
    в приложение; также доступна ручная кнопка «Выполнить сейчас».
    """
    now = datetime.now(timezone.utc)

    # Берём только активные правила, у которых уже наступил срок.
    stmt = (
        select(RecurringTransaction)
        .where(RecurringTransaction.owner_id == current_user.id)
        .where(RecurringTransaction.is_active.is_(True))
        .where(RecurringTransaction.next_run_at <= now)
    )
    rules = list(await session.scalars(stmt))

    created = 0
    deactivated = 0
    rules_processed = 0

    for rule in rules:
        rules_processed += 1
        source = await session.get(Account, rule.account_id)
        target = (
            await session.get(Account, rule.transfer_account_id)
            if rule.kind == "transfer"
            else None
        )
        # Счёт точно существует (FK + CASCADE), но подстрахуемся: без него
        # генерить операцию некуда — деактивируем правило.
        if source is None or (rule.kind == "transfer" and target is None):
            rule.is_active = False
            deactivated += 1
            continue

        guard = 0
        while (
            rule.is_active
            and ensure_aware_utc(rule.next_run_at) <= now
            and guard < MAX_OCCURRENCES_PER_RUN
        ):
            # Перешагнули дату окончания → правило завершилось.
            if rule.end_at is not None and ensure_aware_utc(
                rule.next_run_at
            ) > ensure_aware_utc(rule.end_at):
                rule.is_active = False
                deactivated += 1
                break

            # Если валюта счетов перевода разошлась (юзер сменил валюту счёта
            # после создания правила) — безопасно остановить правило, а не
            # создавать математически бессмысленную проводку «рубли+доллары».
            if rule.kind == "transfer" and target.currency_code != source.currency_code:
                rule.is_active = False
                deactivated += 1
                break

            occurred_at = rule.next_run_at
            # Валюту берём из счёта актуально (а не из снимка правила).
            currency = source.currency_code

            tx = Transaction(
                owner_id=rule.owner_id,
                account_id=rule.account_id,
                kind=rule.kind,
                amount=rule.amount,
                currency_code=currency,
                category_id=rule.category_id,
                transfer_account_id=rule.transfer_account_id,
                occurred_at=occurred_at,
                note=rule.note,
            )
            session.add(tx)

            delta_source = signed_delta_for_source(rule.kind, rule.amount)
            await apply_signed_delta_to_account(
                source, delta_source, occurred_at, session
            )
            if rule.kind == "transfer":
                await apply_signed_delta_to_account(
                    target, rule.amount, occurred_at, session
                )

            created += 1
            rule.last_run_at = occurred_at
            rule.next_run_at = next_occurrence(
                occurred_at, rule.frequency, rule.interval
            )
            guard += 1

        # Если после материализации курсор ушёл за дату окончания —
        # завершаем правило (на случай, когда цикл вышел по другому условию).
        if rule.is_active and rule.end_at is not None and ensure_aware_utc(
            rule.next_run_at
        ) > ensure_aware_utc(rule.end_at):
            rule.is_active = False
            deactivated += 1

    await session.commit()
    return RunResult(
        created=created,
        rules_processed=rules_processed,
        deactivated=deactivated,
    )


@router.get(
    "/{rule_id}",
    response_model=RecurringTransactionRead,
    summary="Получить правило по id",
)
async def get_recurring(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringTransaction:
    return await _get_owned_rule_or_404(rule_id, current_user, session)


@router.patch(
    "/{rule_id}",
    response_model=RecurringTransactionRead,
    summary="Обновить правило (безопасные поля)",
)
async def update_recurring(
    rule_id: int,
    payload: RecurringTransactionUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringTransaction:
    """Правим имя/сумму/заметку/частоту/интервал/дату окончания/активность.

    Тип, счета и категорию не трогаем — это «другое правило». Уже
    сгенерированные ранее операции не меняются (они уже в истории).
    """
    rule = await _get_owned_rule_or_404(rule_id, current_user, session)

    fields = payload.model_fields_set

    if "name" in fields and payload.name is not None:
        rule.name = payload.name
    if "amount" in fields and payload.amount is not None:
        rule.amount = payload.amount
    if "note" in fields:
        rule.note = payload.note if payload.note else None
    # Смена частоты/интервала применяется со СЛЕДУЮЩЕГО цикла: уже
    # запланированный next_run_at не сдвигаем (он сработает по старому
    # расписанию), а дальше движок считает по новым frequency/interval.
    if "frequency" in fields and payload.frequency is not None:
        rule.frequency = payload.frequency
    if "interval" in fields and payload.interval is not None:
        rule.interval = payload.interval
    if "end_at" in fields:
        # end_at можно как задать, так и снять (null = снова бессрочно).
        if payload.end_at is not None and ensure_aware_utc(
            payload.end_at
        ) < ensure_aware_utc(rule.start_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Дата окончания не может быть раньше даты начала",
            )
        rule.end_at = payload.end_at
        # Если новая дата окончания уже позади ближайшего запуска — правило
        # завершено, гасим сразу (не дожидаясь /run), чтобы статус в UI был
        # консистентным.
        if (
            rule.end_at is not None
            and ensure_aware_utc(rule.next_run_at) > ensure_aware_utc(rule.end_at)
        ):
            rule.is_active = False
    if "is_active" in fields and payload.is_active is not None:
        was_active = rule.is_active
        rule.is_active = payload.is_active
        # Возобновление паузы (False → True): «пауза = пропуск периодов».
        # Перематываем курсор next_run_at на ближайшую БУДУЩУЮ дату, чтобы при
        # возобновлении НЕ создавать операции задним числом за время простоя.
        # (Это отличается от обычного catch-up «не заходил в приложение» —
        # там пропуски доганяются специально; пауза же — намеренный перерыв.)
        if payload.is_active and not was_active:
            now = datetime.now(timezone.utc)
            guard = 0
            while (
                ensure_aware_utc(rule.next_run_at) <= now
                and guard < MAX_OCCURRENCES_PER_RUN
            ):
                # Если перемотка вышла за дату окончания — правило завершено,
                # возобновлять нечего.
                if rule.end_at is not None and ensure_aware_utc(
                    rule.next_run_at
                ) > ensure_aware_utc(rule.end_at):
                    rule.is_active = False
                    break
                rule.next_run_at = next_occurrence(
                    rule.next_run_at, rule.frequency, rule.interval
                )
                guard += 1
            if rule.is_active and rule.end_at is not None and ensure_aware_utc(
                rule.next_run_at
            ) > ensure_aware_utc(rule.end_at):
                rule.is_active = False

    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить правило (уже созданные операции остаются)",
)
async def delete_recurring(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rule = await _get_owned_rule_or_404(rule_id, current_user, session)
    await session.delete(rule)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Внутренние хелперы ─────────────────────────────────────────────────


async def _get_owned_account_or_404(
    account_id: int,
    current_user: User,
    session: AsyncSession,
) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Счёт не найден",
        )
    return account


async def _get_owned_rule_or_404(
    rule_id: int,
    current_user: User,
    session: AsyncSession,
) -> RecurringTransaction:
    rule = await session.get(RecurringTransaction, rule_id)
    if rule is None or rule.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Правило не найдено",
        )
    return rule
