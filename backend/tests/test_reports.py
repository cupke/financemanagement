"""Интеграционные тесты эндпоинта /reports/overview.

Денежные проверки идут в рублях — чтобы не зависеть от наличия курсов ЦБ в
тестовой БД (для RUB конверсия — тождество). Отдельный тест проверяет, что в
режиме одного валютного счёта валюта отчёта = валюта счёта (там пересчёт тоже
не нужен: суммы уже в этой валюте).
"""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _date_str(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()


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


async def _add_tx(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    kind: str,
    account_id: int,
    amount: str,
    category_id: int | None = None,
    occurred_at: str | None = None,
) -> None:
    body: dict = {
        "kind": kind,
        "account_id": account_id,
        "amount": amount,
        "occurred_at": occurred_at or _now_iso(),
    }
    if category_id is not None:
        body["category_id"] = category_id
    await client.post("/api/v1/transactions", json=body, headers=auth_headers)


async def test_reports_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/reports/overview")
    assert response.status_code == 401


async def test_reports_summary_totals_rub(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта")
    salary = await _create_category(client, auth_headers, "Зарплата", "income")
    food = await _create_category(client, auth_headers, "Еда", "expense")
    await _add_tx(client, auth_headers, kind="income", account_id=account_id, amount="80000", category_id=salary)
    await _add_tx(client, auth_headers, kind="expense", account_id=account_id, amount="30000", category_id=food)

    response = await client.get("/api/v1/reports/overview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["currency"] == "RUB"
    assert data["account_id"] is None
    assert data["summary"]["total_income"] == "80000.00"
    assert data["summary"]["total_expense"] == "30000.00"
    assert data["summary"]["net"] == "50000.00"


async def test_reports_by_category(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта")
    salary = await _create_category(client, auth_headers, "Зарплата", "income")
    food = await _create_category(client, auth_headers, "Еда", "expense")
    rent = await _create_category(client, auth_headers, "Жильё", "expense")
    await _add_tx(client, auth_headers, kind="income", account_id=account_id, amount="50000", category_id=salary)
    await _add_tx(client, auth_headers, kind="expense", account_id=account_id, amount="20000", category_id=rent)
    await _add_tx(client, auth_headers, kind="expense", account_id=account_id, amount="5000", category_id=food)

    data = (await client.get("/api/v1/reports/overview", headers=auth_headers)).json()

    expense = {c["category_name"]: c["amount"] for c in data["expense_by_category"]}
    income = {c["category_name"]: c["amount"] for c in data["income_by_category"]}
    assert expense == {"Жильё": "20000.00", "Еда": "5000.00"}
    assert income == {"Зарплата": "50000.00"}
    # Сортировка расходов по убыванию: первым — самая крупная категория.
    assert data["expense_by_category"][0]["category_name"] == "Жильё"


async def test_reports_account_filter(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc_a = await _create_account(client, auth_headers, "Карта A")
    acc_b = await _create_account(client, auth_headers, "Карта B")
    food = await _create_category(client, auth_headers, "Еда", "expense")
    await _add_tx(client, auth_headers, kind="expense", account_id=acc_a, amount="100", category_id=food)
    await _add_tx(client, auth_headers, kind="expense", account_id=acc_b, amount="200", category_id=food)

    # Все счета: 100 + 200 = 300.
    all_acc = (await client.get("/api/v1/reports/overview", headers=auth_headers)).json()
    assert all_acc["summary"]["total_expense"] == "300.00"

    # Только счёт A: 100.
    only_a = (
        await client.get(
            "/api/v1/reports/overview", params={"account_id": acc_a}, headers=auth_headers
        )
    ).json()
    assert only_a["account_id"] == acc_a
    assert only_a["summary"]["total_expense"] == "100.00"


async def test_reports_balance_includes_opening_and_movements(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", opening="1000")
    salary = await _create_category(client, auth_headers, "Зарплата", "income")
    await _add_tx(client, auth_headers, kind="income", account_id=account_id, amount="500", category_id=salary)

    data = (await client.get("/api/v1/reports/overview", headers=auth_headers)).json()
    # Баланс на конец периода = начальный остаток + движения = 1000 + 500.
    assert data["points"][-1]["balance"] == "1500.00"


async def test_reports_date_range_excludes_outside(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта")
    food = await _create_category(client, auth_headers, "Еда", "expense")
    # Старый расход (год назад) и свежий (сегодня).
    await _add_tx(
        client, auth_headers, kind="expense", account_id=account_id, amount="100",
        category_id=food, occurred_at=_days_ago_iso(400),
    )
    await _add_tx(client, auth_headers, kind="expense", account_id=account_id, amount="50", category_id=food)

    # Узкое окно — последние 30 дней: старый расход не должен попасть.
    data = (
        await client.get(
            "/api/v1/reports/overview",
            params={"from_date": _date_str(30), "to_date": _date_str(0)},
            headers=auth_headers,
        )
    ).json()
    assert data["summary"]["total_expense"] == "50.00"
    assert data["granularity"] == "day"  # 30 дней -> корзины по дням


async def test_reports_single_account_uses_its_currency(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    usd_account = await _create_account(client, auth_headers, "USD-карта", currency="USD")
    freelance = await _create_category(client, auth_headers, "Фриланс", "income")
    await _add_tx(client, auth_headers, kind="income", account_id=usd_account, amount="100", category_id=freelance)

    data = (
        await client.get(
            "/api/v1/reports/overview", params={"account_id": usd_account}, headers=auth_headers
        )
    ).json()
    # Валюта отчёта = валюта счёта; сумма не пересчитывается в рубли.
    assert data["currency"] == "USD"
    assert data["summary"]["total_income"] == "100.00"
