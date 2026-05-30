"""Тесты исправлений корректности/валидации (этап 3 правок): M1, B1, C1."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from tests.conftest import test_engine


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ─── M1: ограничение знаков после запятой у суммы ──────────────────────────


async def test_transaction_amount_rejects_more_than_two_decimals(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc = await client.post(
        "/api/v1/accounts",
        json={"name": "Карта", "opening_balance": "0", "currency_code": "RUB"},
        headers=auth_headers,
    )
    account_id = acc.json()["id"]
    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "10.123",  # 3 знака после запятой — должно отклониться
            "occurred_at": _iso(datetime.now(timezone.utc)),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ─── C1: запрет цикла в иерархии категорий ─────────────────────────────────


async def test_category_cannot_move_into_own_subtree(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    root = await client.post(
        "/api/v1/categories",
        json={"name": "Расходы", "kind": "expense"},
        headers=auth_headers,
    )
    root_id = root.json()["id"]
    child = await client.post(
        "/api/v1/categories",
        json={"name": "Продукты", "kind": "expense", "parent_id": root_id},
        headers=auth_headers,
    )
    child_id = child.json()["id"]

    # Пытаемся сделать корень потомком его собственного ребёнка → цикл → 400.
    resp = await client.patch(
        f"/api/v1/categories/{root_id}",
        json={"parent_id": child_id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ─── B1: линия баланса в отчётах не учитывает операции до opening_date ──────


async def test_reports_balance_excludes_pre_opening_movements(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    if test_engine.dialect.name != "postgresql":
        import pytest

        pytest.skip("Отчёты используют TIMESTAMPTZ-сравнения — проверяем на PostgreSQL")

    now = datetime.now(timezone.utc)
    # Счёт с остатком 1000 и датой остатка 2 дня назад.
    acc = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Карта",
            "opening_balance": "1000",
            "currency_code": "RUB",
            "opening_date": _iso(now - timedelta(days=2)),
        },
        headers=auth_headers,
    )
    account_id = acc.json()["id"]

    # Ретро-расход ДО opening_date (5 дней назад) — в баланс не входит.
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "occurred_at": _iso(now - timedelta(days=5)),
        },
        headers=auth_headers,
    )
    # Обычный расход ПОСЛЕ opening_date (1 день назад) — в баланс входит.
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "200",
            "occurred_at": _iso(now - timedelta(days=1)),
        },
        headers=auth_headers,
    )

    # Реальный баланс счёта = 1000 - 200 = 800 (ретро -100 не учтён).
    acc_now = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert acc_now.json()["balance"] == "800.00"

    # Линия баланса в отчёте на конец периода должна совпасть с 800, а НЕ 700
    # (что было бы при двойном учёте ретро-операции — находка B1).
    report = await client.get(
        "/api/v1/reports/overview",
        params={
            "from_date": (now - timedelta(days=10)).date().isoformat(),
            "to_date": now.date().isoformat(),
            "account_id": account_id,
        },
        headers=auth_headers,
    )
    assert report.status_code == 200
    points = report.json()["points"]
    assert points, "ожидались корзины в отчёте"
    assert points[-1]["balance"] == "800.00"
