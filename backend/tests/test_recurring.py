"""Тесты повторяющихся операций: правила (CRUD) + движок до-генерации /run.

Ключевой нюанс с балансами: операция двигает balance счёта только если её
occurred_at >= opening_date (модель «opening_balance + движения»). Поэтому
счета здесь создаём с opening_date заведомо в прошлом — чтобы сгенерированные
ретро-операции реально меняли баланс и это можно было проверить.
"""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from app.services.recurrence import next_occurrence


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _create_account(
    client: AsyncClient,
    auth_headers: dict[str, str],
    name: str,
    opening: str = "0",
    opening_date: str | None = None,
) -> int:
    body: dict[str, object] = {"name": name, "opening_balance": opening}
    if opening_date is not None:
        body["opening_date"] = opening_date
    resp = await client.post("/api/v1/accounts", json=body, headers=auth_headers)
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


# Заведомо «старая» дата открытия счёта — чтобы любые ретро-операции
# попадали в баланс.
_OLD_OPENING = "2020-01-01T00:00:00+00:00"


# ─── Чистая логика расписания (модульный тест без БД) ─────────────────────


def test_next_occurrence_clamps_month_end() -> None:
    """31 января + 1 месяц → 28 февраля (в феврале нет 31-го)."""
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc)
    feb = next_occurrence(jan31, "monthly", 1)
    assert (feb.year, feb.month, feb.day) == (2026, 2, 28)
    # Время суток сохраняется.
    assert (feb.hour, feb.minute) == (9, 0)


def test_next_occurrence_weekly_interval() -> None:
    """Каждые 2 недели = +14 дней."""
    d = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert next_occurrence(d, "weekly", 2) == d + timedelta(days=14)


# ─── Эндпоинты ────────────────────────────────────────────────────────────


async def test_run_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/recurring-transactions/run")
    assert response.status_code == 401


async def test_create_rule(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    category_id = await _create_category(client, auth_headers, "Зарплата", "income")
    start = datetime.now(timezone.utc) + timedelta(days=5)  # будущий старт

    response = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Зарплата",
            "kind": "income",
            "account_id": account_id,
            "amount": "50000",
            "category_id": category_id,
            "frequency": "monthly",
            "interval": 1,
            "start_at": _iso(start),
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Зарплата"
    assert body["is_active"] is True
    # Курсор движка стартует с даты начала.
    assert body["next_run_at"] == body["start_at"]


async def test_future_rule_generates_nothing(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Правило со стартом в будущем при /run не создаёт операций и не трогает баланс."""
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    start = datetime.now(timezone.utc) + timedelta(days=10)
    await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Будущее",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(start),
        },
        headers=auth_headers,
    )
    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert run.status_code == 200
    assert run.json()["created"] == 0
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "1000.00"


async def test_run_generates_due_and_updates_balance(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Ежедневный расход со стартом 2 дня назад → 3 операции (-2д, -1д, сегодня),
    баланс уменьшается на 3×amount, next_run_at уходит в будущее."""
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    start = datetime.now(timezone.utc) - timedelta(days=2)
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кофе",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(start),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert run.status_code == 200
    assert run.json()["created"] == 3

    # Баланс: 1000 - 3×100 = 700.
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "700.00"

    # next_run_at теперь в будущем.
    rule = await client.get(
        f"/api/v1/recurring-transactions/{rule_id}", headers=auth_headers
    )
    next_run = datetime.fromisoformat(rule.json()["next_run_at"])
    assert next_run > datetime.now(timezone.utc)

    # Сгенерированы 3 обычные операции.
    txs = await client.get(
        "/api/v1/transactions", params={"account_id": account_id}, headers=auth_headers
    )
    assert len(txs.json()) == 3


async def test_run_is_idempotent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Повторный /run сразу после первого не создаёт новых операций."""
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кофе",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc) - timedelta(days=1)),
        },
        headers=auth_headers,
    )
    first = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert first.json()["created"] >= 1
    second = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert second.json()["created"] == 0


async def test_end_at_deactivates_rule(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Правило с датой окончания в прошлом догенерит операции до end_at
    включительно, затем само деактивируется."""
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    now = datetime.now(timezone.utc)
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Ограниченное",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(now - timedelta(days=5)),
            "end_at": _iso(now - timedelta(days=3)),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    # Операции на -5, -4, -3 дня = 3 штуки.
    assert run.json()["created"] == 3
    assert run.json()["deactivated"] == 1

    rule = await client.get(
        f"/api/v1/recurring-transactions/{rule_id}", headers=auth_headers
    )
    assert rule.json()["is_active"] is False


async def test_transfer_rule_moves_money(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    source_id = await _create_account(
        client, auth_headers, "Зарплатная", "1000", opening_date=_OLD_OPENING
    )
    target_id = await _create_account(
        client, auth_headers, "Накопления", "0", opening_date=_OLD_OPENING
    )
    await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "В копилку",
            "kind": "transfer",
            "account_id": source_id,
            "transfer_account_id": target_id,
            "amount": "200",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc) - timedelta(days=1)),
        },
        headers=auth_headers,
    )
    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    created = run.json()["created"]
    assert created == 2  # -1 день и сегодня

    source = await client.get(f"/api/v1/accounts/{source_id}", headers=auth_headers)
    target = await client.get(f"/api/v1/accounts/{target_id}", headers=auth_headers)
    assert source.json()["balance"] == f"{1000 - 200 * created}.00"
    assert target.json()["balance"] == f"{200 * created}.00"


async def test_paused_rule_skipped(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кофе",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc) - timedelta(days=2)),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    # Ставим на паузу.
    patch = await client.patch(
        f"/api/v1/recurring-transactions/{rule_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert patch.status_code == 200

    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert run.json()["created"] == 0
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "1000.00"


async def test_resume_skips_paused_periods(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Пауза = пропуск: при возобновлении пропущенные за паузу операции НЕ
    создаются, а next_run_at перематывается на будущее."""
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    # Старт 5 дней назад, но сразу ставим на паузу (правило не запускаем).
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кофе",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc) - timedelta(days=5)),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]
    await client.patch(
        f"/api/v1/recurring-transactions/{rule_id}",
        json={"is_active": False},
        headers=auth_headers,
    )

    # Возобновляем — next_run_at должен уйти в будущее (периоды паузы пропущены).
    resume = await client.patch(
        f"/api/v1/recurring-transactions/{rule_id}",
        json={"is_active": True},
        headers=auth_headers,
    )
    assert resume.status_code == 200
    assert resume.json()["is_active"] is True
    next_run = datetime.fromisoformat(resume.json()["next_run_at"])
    assert next_run > datetime.now(timezone.utc)

    # Прогон после возобновления не создаёт операций задним числом.
    run = await client.post(
        "/api/v1/recurring-transactions/run", headers=auth_headers
    )
    assert run.json()["created"] == 0
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=auth_headers)
    assert account.json()["balance"] == "1000.00"


async def test_update_and_delete_rule(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Подписка",
            "kind": "expense",
            "account_id": account_id,
            "amount": "299",
            "frequency": "monthly",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc) + timedelta(days=3)),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    patch = await client.patch(
        f"/api/v1/recurring-transactions/{rule_id}",
        json={"amount": "399", "name": "Подписка Premium"},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    assert patch.json()["amount"] == "399.00"
    assert patch.json()["name"] == "Подписка Premium"

    delete = await client.delete(
        f"/api/v1/recurring-transactions/{rule_id}", headers=auth_headers
    )
    assert delete.status_code == 204

    missing = await client.get(
        f"/api/v1/recurring-transactions/{rule_id}", headers=auth_headers
    )
    assert missing.status_code == 404


async def test_patch_end_at_in_past_deactivates_rule(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Если задать дату окончания, которая уже позади ближайшего запуска,
    правило деактивируется сразу в PATCH (а не ждёт следующего /run)."""
    account_id = await _create_account(
        client, auth_headers, "Карта", "1000", opening_date=_OLD_OPENING
    )
    now = datetime.now(timezone.utc)
    create = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кофе",
            "kind": "expense",
            "account_id": account_id,
            "amount": "100",
            "frequency": "daily",
            "interval": 1,
            "start_at": _iso(now - timedelta(days=3)),
        },
        headers=auth_headers,
    )
    rule_id = create.json()["id"]
    # Прогон сдвигает next_run_at в будущее.
    await client.post("/api/v1/recurring-transactions/run", headers=auth_headers)

    # Дата окончания «вчера» (>= start_at, но < next_run_at) → правило завершено.
    patch = await client.patch(
        f"/api/v1/recurring-transactions/{rule_id}",
        json={"end_at": _iso(now - timedelta(days=1))},
        headers=auth_headers,
    )
    assert patch.status_code == 200
    assert patch.json()["is_active"] is False


async def test_transfer_requires_target(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    account_id = await _create_account(client, auth_headers, "Карта", "1000")
    response = await client.post(
        "/api/v1/recurring-transactions",
        json={
            "name": "Кривой перевод",
            "kind": "transfer",
            "account_id": account_id,
            "amount": "100",
            "frequency": "monthly",
            "interval": 1,
            "start_at": _iso(datetime.now(timezone.utc)),
        },
        headers=auth_headers,
    )
    assert response.status_code == 422  # Pydantic: перевод без получателя
