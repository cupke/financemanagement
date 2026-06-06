"""Интеграционные тесты эндпоинта /dashboard/summary (BFF-сводка главной).

Денежные суммы проверяем в рублях — для RUB пересчёт является тождеством, и
тест не зависит от наличия курсов ЦБ. Сценарий с валютным счётом отдельно
сеет курс USD прямо в БД (fetched_at = сегодня), чтобы cache-aside отдал кеш
и не ходил в сеть к ЦБ (см. app.services.cbr_rates.get_rates_for_today).

Закрывает трассировку ФТ-12 (дашборд) и ФТ-10 (капитал в рублях по курсу ЦБ).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exchange_rate import ExchangeRate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _create_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
    name: str,
    opening: str = "0",
    currency: str = "RUB",
) -> int:
    resp = await client.post(
        "/api/v1/accounts",
        json={"name": name, "opening_balance": opening, "currency_code": currency},
        headers=auth_headers,
    )
    return resp.json()["id"]


async def _create_category(
    client: AsyncClient, auth_headers: dict[str, str], name: str, kind: str
) -> int:
    resp = await client.post(
        "/api/v1/categories",
        json={"name": name, "kind": kind},
        headers=auth_headers,
    )
    return resp.json()["id"]


async def _add_expense(
    client: AsyncClient,
    auth_headers: dict[str, str],
    account_id: int,
    amount: str,
    category_id: int,
) -> None:
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": amount,
            "category_id": category_id,
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )


async def _seed_usd_rate(session: AsyncSession, vunit_rate: str = "90.0000") -> None:
    """Засеять курс USD на сегодня. fetched_at=сейчас => cache-aside не идёт в сеть."""
    session.add(
        ExchangeRate(
            char_code="USD",
            num_code="840",
            name="Доллар США",
            nominal=1,
            value=Decimal(vunit_rate),
            vunit_rate=Decimal(vunit_rate),
            rate_date=date.today(),
            fetched_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dashboard/summary")
    assert response.status_code == 401


async def test_dashboard_summary_aggregates_capital_and_spending(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    card = await _create_account(client, auth_headers, "Карта", opening="100000")
    await _create_account(client, auth_headers, "Наличные", opening="5000")
    food = await _create_category(client, auth_headers, "Еда", "expense")
    transport = await _create_category(client, auth_headers, "Транспорт", "expense")
    await _add_expense(client, auth_headers, card, "3000", food)
    await _add_expense(client, auth_headers, card, "1500", food)
    await _add_expense(client, auth_headers, card, "800", transport)

    data = (
        await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    ).json()

    assert data["accounts_count"] == 2
    # Капитал = начальные остатки (100000 + 5000) − расходы (3000 + 1500 + 800).
    assert Decimal(data["total_capital_rub"]) == Decimal("99700.00")
    assert data["capital_incomplete"] is False
    assert Decimal(data["spent_this_month_rub"]) == Decimal("5300.00")
    assert data["expenses_this_month"] == 3
    # Топ категорий по убыванию: Еда (4500) > Транспорт (800).
    names = [c["category_name"] for c in data["top_categories"]]
    assert names == ["Еда", "Транспорт"]
    assert Decimal(data["top_categories"][0]["spent_rub"]) == Decimal("4500.00")


async def test_dashboard_empty_user_has_zero_capital(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    data = (
        await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    ).json()
    assert data["accounts_count"] == 0
    assert Decimal(data["total_capital_rub"]) == Decimal("0.00")
    assert data["capital_incomplete"] is False
    assert data["expenses_this_month"] == 0
    assert data["top_categories"] == []


async def test_dashboard_capital_incomplete_when_rate_missing(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _create_account(client, auth_headers, "Рубли", opening="10000")
    await _create_account(client, auth_headers, "Доллары", opening="100", currency="USD")
    # Курс USD НЕ засеян: валютный счёт пересчитать не во что.

    data = (
        await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    ).json()

    assert data["capital_incomplete"] is True
    # USD-счёт дал вклад 0, в капитал вошёл только рублёвый счёт.
    assert Decimal(data["total_capital_rub"]) == Decimal("10000.00")


async def test_dashboard_capital_includes_currency_with_rate(
    client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession
) -> None:
    await _create_account(client, auth_headers, "Рубли", opening="10000")
    await _create_account(client, auth_headers, "Доллары", opening="100", currency="USD")
    await _seed_usd_rate(session, vunit_rate="90.0000")  # 1 USD = 90 ₽

    data = (
        await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    ).json()

    assert data["capital_incomplete"] is False
    # 10000 ₽ + 100 USD × 90 = 10000 + 9000 = 19000 ₽.
    assert Decimal(data["total_capital_rub"]) == Decimal("19000.00")
