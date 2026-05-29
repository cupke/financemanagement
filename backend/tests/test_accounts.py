from datetime import datetime, timezone

from httpx import AsyncClient


async def test_change_currency_with_transactions_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # По счёту с операциями менять валюту нельзя: суммы операций хранятся в
    # прежней валюте (snapshot), иначе капитал/баланс исказятся.
    acc = (
        await client.post(
            "/api/v1/accounts",
            json={"name": "Счёт", "currency_code": "RUB"},
            headers=auth_headers,
        )
    ).json()["id"]
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "account_id": acc,
            "amount": "100",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=auth_headers,
    )
    resp = await client.patch(
        f"/api/v1/accounts/{acc}",
        json={"currency_code": "USD"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_change_currency_empty_account_allowed(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # На пустом счёте (без операций) сменить валюту можно.
    acc = (
        await client.post(
            "/api/v1/accounts",
            json={"name": "Пустой", "currency_code": "RUB"},
            headers=auth_headers,
        )
    ).json()["id"]
    resp = await client.patch(
        f"/api/v1/accounts/{acc}",
        json={"currency_code": "usd"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["currency_code"] == "USD"


async def test_create_account_minimal(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Карта Сбер"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Карта Сбер"
    assert body["kind"] == "other"
    assert body["currency_code"] == "RUB"
    assert body["balance"] == "0.00"


async def test_create_account_full(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/accounts",
        json={
            "name": "Наличные USD",
            "kind": "cash",
            "note": "заначка",
            "opening_balance": "500.00",
            "currency_code": "usd",  # проверим, что код приводится к верхнему регистру
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "cash"
    assert body["note"] == "заначка"
    assert body["opening_balance"] == "500.00"
    assert body["balance"] == "500.00"  # = opening_balance для нового счёта
    assert body["currency_code"] == "USD"


async def test_create_account_duplicate_name_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"name": "Главный счёт"}
    first = await client.post("/api/v1/accounts", json=payload, headers=auth_headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/accounts", json=payload, headers=auth_headers)
    assert second.status_code == 409


async def test_list_accounts_returns_only_owned(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post("/api/v1/accounts", json={"name": "A"}, headers=auth_headers)
    await client.post("/api/v1/accounts", json={"name": "B"}, headers=auth_headers)

    response = await client.get("/api/v1/accounts", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    names = {a["name"] for a in body}
    assert names == {"A", "B"}


async def test_get_account_by_id(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/accounts", json={"name": "Test"}, headers=auth_headers
    )
    account_id = created.json()["id"]

    response = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == account_id


async def test_get_account_404_for_unknown_id(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/accounts/999999", headers=auth_headers)
    assert response.status_code == 404


async def test_update_account_partial(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/v1/accounts", json={"name": "Старое имя"}, headers=auth_headers
    )
    account_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"name": "Новое имя", "note": "обновлено"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Новое имя"
    assert body["note"] == "обновлено"


async def test_delete_account(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/accounts", json={"name": "На удаление"}, headers=auth_headers
    )
    account_id = created.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/accounts/{account_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/accounts/{account_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


async def test_accounts_require_auth(client: AsyncClient) -> None:
    """Без JWT-заголовка должна быть 401."""
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 401


async def test_other_user_cannot_access_account(client: AsyncClient) -> None:
    """IDOR-проверка: чужой счёт даёт 404, а не 403 — не утекаем существование."""
    # Юзер A создаёт счёт
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user_a@example.com", "password": "PassA12345!"},
    )
    login_a = await client.post(
        "/api/v1/auth/login",
        json={"email": "user_a@example.com", "password": "PassA12345!"},
    )
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    created = await client.post(
        "/api/v1/accounts", json={"name": "Счёт А"}, headers=headers_a
    )
    a_id = created.json()["id"]

    # Юзер B пытается прочитать
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user_b@example.com", "password": "PassB12345!"},
    )
    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": "user_b@example.com", "password": "PassB12345!"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    response = await client.get(f"/api/v1/accounts/{a_id}", headers=headers_b)
    assert response.status_code == 404
