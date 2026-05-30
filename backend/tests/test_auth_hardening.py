"""Тесты усиления безопасности авторизации (этап 2 правок).

Покрывают:
- политику пароля (минимум одна буква и одна цифра) на регистрации;
- вход с НЕсуществующим email → 401 (ветка с фиктивным хэшем для защиты от
  тайминг-оракула не должна падать).
"""
from httpx import AsyncClient


async def test_register_rejects_password_without_digit(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "nodigit@example.com", "password": "OnlyLetters"},
    )
    assert resp.status_code == 422


async def test_register_rejects_password_without_letter(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "noletter@example.com", "password": "12345678"},
    )
    assert resp.status_code == 422


async def test_register_accepts_letter_and_digit(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "ok@example.com", "password": "Letters123"},
    )
    assert resp.status_code == 201


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    # Пользователя нет — попадаем в ветку с фиктивным verify_password.
    # Главное: ответ 401 (а не 500) и одинаковое сообщение, как при неверном пароле.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Whatever123"},
    )
    assert resp.status_code == 401
