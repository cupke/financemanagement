"""Тесты подтверждения почты, сброса и смены пароля.

Сырой токен уходит только в письмо, поэтому в тестах подменяем отправители
(`send_verification_email` / `send_reset_email`) на перехватчики, которые
складывают (email, token) в список — так тест получает токен и идёт по ссылке.
"""
import pytest
from httpx import AsyncClient

from app.services import email as email_service


@pytest.fixture
def sent_emails(monkeypatch):
    """Перехватывает отправляемые письма; возвращает список их (kind, to, token)."""
    box: list[dict] = []

    async def fake_verify(to: str, token: str) -> bool:
        box.append({"kind": "verify", "to": to, "token": token})
        return True

    async def fake_reset(to: str, token: str) -> bool:
        box.append({"kind": "reset", "to": to, "token": token})
        return True

    monkeypatch.setattr(email_service, "send_verification_email", fake_verify)
    monkeypatch.setattr(email_service, "send_reset_email", fake_reset)
    return box


async def _register(client: AsyncClient, email: str, password: str) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert resp.status_code == 201


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _token_of(box: list[dict], kind: str) -> str:
    items = [e for e in box if e["kind"] == kind]
    assert items, f"письмо типа {kind} не отправлено"
    return items[-1]["token"]


# ─── Подтверждение почты ────────────────────────────────────────────────


async def test_register_does_not_send_email(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    """Регистрация НЕ шлёт письмо автоматически — пользователь запрашивает сам."""
    await _register(client, "newuser@example.com", "Password123")
    assert sent_emails == []


async def test_resend_then_verify_works(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    """Письмо уходит по кнопке (resend), и по ссылке почта подтверждается."""
    await _register(client, "newuser@example.com", "Password123")
    headers = await _login(client, "newuser@example.com", "Password123")

    resend = await client.post(
        "/api/v1/auth/resend-verification", headers=headers
    )
    assert resend.status_code == 200
    token = _token_of(sent_emails, "verify")

    verify = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify.status_code == 200

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["email_verified"] is True


async def test_new_user_is_unverified(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    await _register(client, "fresh@example.com", "Password123")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "fresh@example.com", "password": "Password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.json()["email_verified"] is False


async def test_verify_email_rejects_bad_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/verify-email", json={"token": "definitely-not-valid"}
    )
    assert resp.status_code == 400


async def test_verify_token_is_single_use(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    await _register(client, "once@example.com", "Password123")
    headers = await _login(client, "once@example.com", "Password123")
    await client.post("/api/v1/auth/resend-verification", headers=headers)
    token = _token_of(sent_emails, "verify")

    first = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 200
    # Повторное использование того же токена — отклоняется.
    second = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400


# ─── Сброс пароля ───────────────────────────────────────────────────────


async def test_forgot_password_unknown_email_does_not_leak(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    """Для несуществующего email — тот же 200, и письмо не уходит (anti-enumeration)."""
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 200
    assert not [e for e in sent_emails if e["kind"] == "reset"]


async def test_forgot_and_reset_password(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    await _register(client, "reset@example.com", "OldPassword123")

    forgot = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "reset@example.com"}
    )
    assert forgot.status_code == 200
    token = _token_of(sent_emails, "reset")

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "BrandNew456"},
    )
    assert reset.status_code == 200

    # Старый пароль больше не подходит, новый — работает.
    old = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "OldPassword123"},
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "BrandNew456"},
    )
    assert new.status_code == 200


async def test_reset_token_is_single_use(
    client: AsyncClient, sent_emails: list[dict]
) -> None:
    await _register(client, "reuse@example.com", "OldPassword123")
    await client.post(
        "/api/v1/auth/forgot-password", json={"email": "reuse@example.com"}
    )
    token = _token_of(sent_emails, "reset")

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "BrandNew456"},
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "Another789"},
    )
    assert second.status_code == 400


# ─── Смена пароля (для залогиненного) ─────────────────────────────────────


async def test_change_password(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # auth_headers заводит test@example.com / TestPassword123!
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "TestPassword123!",
            "new_password": "ChangedPass456",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    old = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "TestPassword123!"},
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "ChangedPass456"},
    )
    assert new.status_code == 200


async def test_change_password_wrong_current(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "WrongCurrent999",
            "new_password": "ChangedPass456",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_change_password_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "ChangedPass456"},
    )
    assert resp.status_code == 401


async def test_change_password_rejects_short_new(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Новый пароль короче 8 символов → 422 (Pydantic min_length)."""
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "TestPassword123!", "new_password": "short"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
