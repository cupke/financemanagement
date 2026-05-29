"""Тесты кросс-валютных переводов (поле target_amount).

При переводе между счетами РАЗНЫХ валют со счёта-источника списывается amount
(в его валюте), а на счёт-получатель зачисляется target_amount (в его валюте) —
сумму зачисления задаёт пользователь, т.к. банковский курс отличается от ЦБ.
Для переводов в ОДНОЙ валюте target_amount не нужен (зачисляется тот же amount).
"""
from datetime import datetime, timezone

from httpx import AsyncClient


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
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _balance(
    client: AsyncClient, auth_headers: dict[str, str], account_id: int
) -> str:
    resp = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    return resp.json()["balance"]


async def test_cross_currency_transfer_uses_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 9000 ₽ → 100 $: со счёта-источника уходит 9000, на получателя приходит 100.
    rub = await _create_account(client, auth_headers, "Рубли", "50000", "RUB")
    usd = await _create_account(client, auth_headers, "Доллары", "200", "USD")

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": rub,
            "transfer_account_id": usd,
            "amount": "9000",
            "target_amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["amount"] == "9000.00"
    assert body["target_amount"] == "100.00"
    # currency_code транзакции — валюта источника (snapshot).
    assert body["currency_code"] == "RUB"

    assert await _balance(client, auth_headers, rub) == "41000.00"
    assert await _balance(client, auth_headers, usd) == "300.00"


async def test_cross_currency_transfer_requires_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    rub = await _create_account(client, auth_headers, "Рубли", "50000", "RUB")
    usd = await _create_account(client, auth_headers, "Доллары", "0", "USD")

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": rub,
            "transfer_account_id": usd,
            "amount": "9000",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    # Балансы не тронуты — операция отклонена целиком.
    assert await _balance(client, auth_headers, rub) == "50000.00"
    assert await _balance(client, auth_headers, usd) == "0.00"


async def test_delete_cross_currency_transfer_rolls_back_both(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    rub = await _create_account(client, auth_headers, "Рубли", "50000", "RUB")
    usd = await _create_account(client, auth_headers, "Доллары", "200", "USD")

    create = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": rub,
            "transfer_account_id": usd,
            "amount": "9000",
            "target_amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    tx_id = create.json()["id"]

    delete = await client.delete(
        f"/api/v1/transactions/{tx_id}", headers=auth_headers
    )
    assert delete.status_code == 204

    # Оба счёта вернулись к исходному состоянию (откат именно зачисленной суммы).
    assert await _balance(client, auth_headers, rub) == "50000.00"
    assert await _balance(client, auth_headers, usd) == "200.00"


async def test_same_currency_transfer_rejects_mismatched_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    a = await _create_account(client, auth_headers, "Счёт A", "1000", "RUB")
    b = await _create_account(client, auth_headers, "Счёт B", "0", "RUB")

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": a,
            "transfer_account_id": b,
            "amount": "400",
            "target_amount": "395",  # для одной валюты так нельзя
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_same_currency_transfer_stores_null_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    a = await _create_account(client, auth_headers, "Счёт A", "1000", "RUB")
    b = await _create_account(client, auth_headers, "Счёт B", "0", "RUB")

    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": a,
            "transfer_account_id": b,
            "amount": "400",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["target_amount"] is None
    assert await _balance(client, auth_headers, a) == "600.00"
    assert await _balance(client, auth_headers, b) == "400.00"


async def test_recompute_balance_uses_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Регрессия: полный пересчёт (recompute_account_balance) для счёта-получателя
    # должен брать target_amount, а не amount. Иначе после правки opening_balance
    # кросс-валютный перевод зачислит сумму в валюте источника (рубли как доллары).
    rub = await _create_account(client, auth_headers, "Рубли", "50000", "RUB")
    usd = await _create_account(client, auth_headers, "Доллары", "200", "USD")

    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "transfer",
            "account_id": rub,
            "transfer_account_id": usd,
            "amount": "9000",
            "target_amount": "100",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert await _balance(client, auth_headers, usd) == "300.00"

    # PATCH opening_balance (тем же значением) триггерит полный пересчёт.
    resp = await client.patch(
        f"/api/v1/accounts/{usd}",
        json={"opening_balance": "200"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # Должно остаться 300 (200 + 100 зачисленных), а НЕ 9200 (200 + 9000).
    assert await _balance(client, auth_headers, usd) == "300.00"


async def test_target_amount_rejected_for_income(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account = await _create_account(client, auth_headers, "Карта", "0", "RUB")
    resp = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "account_id": account,
            "amount": "500",
            "target_amount": "10",  # бессмысленно для дохода — 422 от схемы
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
