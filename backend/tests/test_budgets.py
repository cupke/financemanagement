from datetime import datetime, timezone

from httpx import AsyncClient


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_category(
    client: AsyncClient, auth_headers: dict[str, str], name: str, kind: str = "expense"
) -> int:
    resp = await client.post(
        "/api/v1/categories",
        json={"name": name, "kind": kind},
        headers=auth_headers,
    )
    return resp.json()["id"]


async def _create_account(
    client: AsyncClient, auth_headers: dict[str, str], opening: str = "100000"
) -> int:
    resp = await client.post(
        "/api/v1/accounts",
        json={"name": "Test", "opening_balance": opening},
        headers=auth_headers,
    )
    return resp.json()["id"]


async def test_create_budget(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    cat = await _create_category(client, auth_headers, "Еда")
    now = _now()
    response = await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "10000",
            "period_year": now.year,
            "period_month": now.month,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "10000.00"
    assert body["period_year"] == now.year
    assert body["period_month"] == now.month


async def test_cannot_create_budget_for_income_category(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    cat = await _create_category(client, auth_headers, "Зарплата", kind="income")
    response = await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "5000",
            "period_year": 2026,
            "period_month": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 400


async def test_duplicate_budget_per_month_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    cat = await _create_category(client, auth_headers, "Еда")
    payload = {
        "category_id": cat,
        "amount": "5000",
        "period_year": 2026,
        "period_month": 6,
    }
    first = await client.post("/api/v1/budgets", json=payload, headers=auth_headers)
    assert first.status_code == 201
    second = await client.post("/api/v1/budgets", json=payload, headers=auth_headers)
    assert second.status_code == 409


async def test_amount_must_be_positive(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    cat = await _create_category(client, auth_headers, "Еда")
    response = await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "0",
            "period_year": 2026,
            "period_month": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_list_budgets_with_progress(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account = await _create_account(client, auth_headers)
    cat = await _create_category(client, auth_headers, "Еда")
    now = _now()

    await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "10000",
            "period_year": now.year,
            "period_month": now.month,
        },
        headers=auth_headers,
    )
    # Тратим 2500 в этой категории — прогресс должен быть 25%, status ok.
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account,
            "amount": "2500",
            "category_id": cat,
            "occurred_at": now.isoformat(),
        },
        headers=auth_headers,
    )

    response = await client.get("/api/v1/budgets", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["spent"] == "2500.00"
    assert item["percent"] == 25.0
    assert item["status"] == "ok"
    assert item["category_name"] == "Еда"


async def test_budget_status_exceeded(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account = await _create_account(client, auth_headers)
    cat = await _create_category(client, auth_headers, "Развлечения")
    now = _now()

    await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "1000",
            "period_year": now.year,
            "period_month": now.month,
        },
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account,
            "amount": "1500",
            "category_id": cat,
            "occurred_at": now.isoformat(),
        },
        headers=auth_headers,
    )

    response = await client.get("/api/v1/budgets", headers=auth_headers)
    item = response.json()[0]
    assert item["status"] == "exceeded"
    assert item["percent"] >= 100


async def test_update_budget_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    cat = await _create_category(client, auth_headers, "Еда")
    created = await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "5000",
            "period_year": 2026,
            "period_month": 6,
        },
        headers=auth_headers,
    )
    budget_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/budgets/{budget_id}",
        json={"amount": "8000"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["amount"] == "8000.00"


async def test_delete_budget(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    cat = await _create_category(client, auth_headers, "Еда")
    created = await client.post(
        "/api/v1/budgets",
        json={
            "category_id": cat,
            "amount": "5000",
            "period_year": 2026,
            "period_month": 6,
        },
        headers=auth_headers,
    )
    budget_id = created.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/budgets/{budget_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204


async def test_budgets_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/budgets")
    assert response.status_code == 401
