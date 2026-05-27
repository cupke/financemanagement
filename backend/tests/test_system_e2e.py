"""Системный (end-to-end) тест: полный пользовательский сценарий.

Имитирует реального пользователя от регистрации до удаления аккаунта,
проходя через все основные модули системы. В отличие от интеграционных
тестов, проверяющих один эндпоинт, системный тест верифицирует, что
модули работают согласованно вместе.
"""
from datetime import datetime, timezone

from httpx import AsyncClient


async def test_full_user_journey(client: AsyncClient) -> None:
    """Сценарий: регистрация → счёт → категории → доход → расход → бюджет → удаление."""
    # 1. Регистрация и логин
    await client.post(
        "/api/v1/auth/register",
        json={"email": "journey@example.com", "password": "Journey123!"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "journey@example.com", "password": "Journey123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Создаём счёт с начальным балансом
    account_resp = await client.post(
        "/api/v1/accounts",
        json={"name": "Карта Сбер", "opening_balance": "50000", "kind": "card"},
        headers=headers,
    )
    assert account_resp.status_code == 201
    account_id = account_resp.json()["id"]
    assert account_resp.json()["balance"] == "50000.00"

    # 3. Создаём категории
    salary_resp = await client.post(
        "/api/v1/categories",
        json={"name": "Зарплата", "kind": "income"},
        headers=headers,
    )
    food_resp = await client.post(
        "/api/v1/categories",
        json={"name": "Еда", "kind": "expense"},
        headers=headers,
    )
    salary_id = salary_resp.json()["id"]
    food_id = food_resp.json()["id"]

    # 4. Получаем зарплату (доход)
    now = datetime.now(timezone.utc).isoformat()
    await client.post(
        "/api/v1/transactions",
        json={
            "kind": "income",
            "account_id": account_id,
            "amount": "80000",
            "category_id": salary_id,
            "occurred_at": now,
        },
        headers=headers,
    )

    # 5. Тратим на еду
    for amount in ("3000", "1500", "2500"):
        await client.post(
            "/api/v1/transactions",
            json={
                "kind": "expense",
                "account_id": account_id,
                "amount": amount,
                "category_id": food_id,
                "occurred_at": now,
            },
            headers=headers,
        )

    # 6. Проверяем баланс: 50000 + 80000 − (3000 + 1500 + 2500) = 123000
    account = await client.get(f"/api/v1/accounts/{account_id}", headers=headers)
    assert account.json()["balance"] == "123000.00"

    # 7. Создаём бюджет на еду 10000 — мы уже потратили 7000, должно быть 70%, warning
    now_dt = datetime.now(timezone.utc)
    await client.post(
        "/api/v1/budgets",
        json={
            "category_id": food_id,
            "amount": "10000",
            "period_year": now_dt.year,
            "period_month": now_dt.month,
        },
        headers=headers,
    )
    budgets = await client.get("/api/v1/budgets", headers=headers)
    assert budgets.status_code == 200
    budget_item = budgets.json()[0]
    assert budget_item["spent"] == "7000.00"
    assert budget_item["status"] == "warning"

    # 8. Удаляем аккаунт (право на забвение, 152-ФЗ)
    delete_resp = await client.delete("/api/v1/users/me", headers=headers)
    assert delete_resp.status_code in (200, 204)

    # 9. После удаления — токен больше не работает
    me_resp = await client.get("/api/v1/users/me", headers=headers)
    assert me_resp.status_code in (401, 404)
