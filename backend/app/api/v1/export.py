"""Роутер /export: выгрузка пользовательских данных в CSV.

Простая отдача файла CSV из памяти через StreamingResponse — для дипломного
проекта этого достаточно. Для больших объёмов (>100k операций) разумнее
было бы стримить построчно генератором, но MVP оптимизирует под читаемость
и редкие выгрузки, а не под highload.
"""
import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.category import Category
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session


router = APIRouter(prefix="/export", tags=["export"])


@router.get(
    "/transactions.csv",
    summary="Экспорт операций пользователя в CSV",
    response_class=Response,
)
async def export_transactions_csv(
    account_id: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    kind: Literal["income", "expense", "transfer"] | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Отдаёт CSV со всеми (или отфильтрованными) операциями пользователя.

    Поля: дата, тип, сумма, валюта, счёт, категория, счёт-получатель, заметка.
    Имена счетов и категорий подставляются вместо id — чтобы файл был
    самодостаточным, без необходимости отдельно экспортировать справочники.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.owner_id == current_user.id)
        .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
    )
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

    transactions = list((await session.scalars(stmt)).all())

    # Подтягиваем имена счетов/категорий одним батч-запросом, чтобы не делать
    # N+1 SELECT'ов в цикле ниже.
    account_ids = {tx.account_id for tx in transactions} | {
        tx.transfer_account_id for tx in transactions if tx.transfer_account_id
    }
    category_ids = {tx.category_id for tx in transactions if tx.category_id}

    accounts_map: dict[int, str] = {}
    if account_ids:
        rows = await session.execute(
            select(Account.id, Account.name).where(Account.id.in_(account_ids))
        )
        accounts_map = {aid: name for aid, name in rows.all()}

    categories_map: dict[int, str] = {}
    if category_ids:
        rows = await session.execute(
            select(Category.id, Category.name).where(Category.id.in_(category_ids))
        )
        categories_map = {cid: name for cid, name in rows.all()}

    # Пишем CSV в память (StringIO) — для дипломных объёмов это безопасно.
    # BOM в начале (﻿) — чтобы Excel правильно открывал кириллицу в UTF-8.
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Дата",
        "Тип",
        "Сумма",
        "Валюта",
        "Счёт",
        "Категория",
        "Счёт-получатель",
        "Заметка",
    ])
    for tx in transactions:
        writer.writerow([
            tx.occurred_at.strftime("%Y-%m-%d %H:%M"),
            {"income": "доход", "expense": "расход", "transfer": "перевод"}.get(
                tx.kind, tx.kind
            ),
            f"{tx.amount:.2f}",
            tx.currency_code,
            accounts_map.get(tx.account_id, ""),
            categories_map.get(tx.category_id, "") if tx.category_id else "",
            accounts_map.get(tx.transfer_account_id, "")
            if tx.transfer_account_id
            else "",
            tx.note or "",
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    filename = f"fintrack-transactions-{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
