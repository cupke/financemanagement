from datetime import datetime, timezone

from httpx import AsyncClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _create_account(
    client: AsyncClient, auth_headers: dict[str, str], name: str, opening: str = "0"
) -> int:
    resp = await client.post(
        "/api/v1/accounts",
        json={"name": name, "opening_balance": opening},
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


async def test_create_income_increases_balance(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    category_id = await _create_category(client, auth_headers, "Зарплата", "income")

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "account_id": account_id,
            "amount": "500",
            "category_id": category_id,
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "1500.00"


async def test_create_expense_decreases_balance(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    category_id = await _create_category(client, auth_headers, "Еда", "expense")

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "300",
            "category_id": category_id,
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "700.00"


async def test_create_transfer_moves_money(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    source_id = await _create_account(client, auth_headers, "Источник", "1000")
    target_id = await _create_account(client, auth_headers, "Получатель", "0")

    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": source_id,
            "transfer_account_id": target_id,
            "amount": "400",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    source = await client.get(f"/api/v1/accounts/{source_id}", headers=auth_headers)
    target = await client.get(f"/api/v1/accounts/{target_id}", headers=auth_headers)
    assert source.json()["balance"] == "600.00"
    assert target.json()["balance"] == "400.00"


async def test_transfer_requires_target_account(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": account_id,
            "amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422  # Pydantic-валидация


async def test_transfer_to_same_account_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": account_id,
            "transfer_account_id": account_id,
            "amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_expense_cannot_have_no_category_when_required(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Расход без категории — для нашей схемы это допустимо (category nullable),
    но если фронт отправит income с transfer_account_id — это уже 422."""
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    other_id = await _create_account(client, auth_headers, "Другой", "0")
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "account_id": account_id,
            "transfer_account_id": other_id,
            "amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_amount_must_be_positive(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "-50",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_list_transactions(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    cat = await _create_category(client, auth_headers, "Еда", "expense")
    for amount in ("100", "200", "50"):
        await client.post(
            "/api/v1/transactions",
            json={
                "kind": "expense",
                "account_id": account_id,
                "amount": amount,
                "category_id": cat,
                "occurred_at": _now_iso(),
            },
            headers=auth_headers,
        )

    response = await client.get("/api/v1/transactions", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    # ответ может быть либо list, либо обёрткой с пагинацией — поддержим оба
    items = body if isinstance(body, list) else body.get("items", [])
    assert len(items) == 3


async def test_delete_transaction_restores_balance(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    cat = await _create_category(client, auth_headers, "Еда", "expense")

    created = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": account_id,
            "amount": "300",
            "category_id": cat,
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    tx_id = created.json()["id"]

    # До удаления
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "700.00"

    delete_resp = await client.delete(
        f"/api/v1/transactions/{tx_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204

    # После удаления баланс восстановился
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "1000.00"


async def test_transactions_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/transactions")
    assert response.status_code == 401
