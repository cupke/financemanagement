"""Тесты CSV-экспорта операций (GET /api/v1/export/transactions.csv).

Главное, что проверяем после правки: в выгрузке есть колонка «Сумма зачисления»,
и для кросс-валютного перевода в неё попадает сумма в валюте счёта-получателя
(раньше эта сумма терялась — выгрузка была неполной).
"""
from datetime import datetime, timezone

from httpx import AsyncClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _account(client, h, name, currency="RUB", opening="0") -> int:
    r = await client.post(
        "/api/v1/accounts",
        json={"name": name, "opening_balance": opening, "currency_code": currency},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _export_lines(client, h) -> list[str]:
    resp = await client.get("/api/v1/export/transactions.csv", headers=h)
    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")  # срезаем BOM
    return text.splitlines()


# Порядок колонок выгрузки.
_DATE, _KIND, _AMOUNT, _CUR, _ACC, _CAT, _DST, _TARGET, _NOTE = range(9)


async def test_export_header_has_target_amount_column(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    lines = await _export_lines(client, auth_headers)
    header = lines[0].split(";")
    assert header[_TARGET] == "Сумма зачисления"
    assert len(header) == 9


async def test_export_cross_currency_transfer_writes_target_amount(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    rub = await _account(client, auth_headers, "Рубли", "RUB", "50000")
    usd = await _account(client, auth_headers, "Доллары", "USD", "200")
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

    lines = await _export_lines(client, auth_headers)
    transfer_rows = [ln for ln in lines[1:] if "перевод" in ln]
    assert len(transfer_rows) == 1
    cells = transfer_rows[0].split(";")
    assert cells[_AMOUNT] == "9000.00"   # списание (в рублях)
    assert cells[_TARGET] == "100.00"    # зачисление (в долларах) — раньше терялось


async def test_export_plain_operation_has_empty_target(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    acc = await _account(client, auth_headers, "Карта", "RUB", "0")
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "expense",
            "account_id": acc,
            "amount": "200",
            "occurred_at": _now_iso(),
        },
        headers=auth_headers,
    )
    lines = await _export_lines(client, auth_headers)
    expense_rows = [ln for ln in lines[1:] if "расход" in ln]
    assert len(expense_rows) == 1
    cells = expense_rows[0].split(";")
    assert cells[_TARGET] == ""  # у обычной операции колонка пустая
