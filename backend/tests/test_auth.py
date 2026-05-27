from httpx import AsyncClient


async def test_register_creates_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "id" in body
    assert "password_hash" not in body  # пароль не должен утекать наружу


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "bob@example.com", "password": "StrongPass123!"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_returns_jwt(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "StrongPass123!"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"].lower() == "bearer"


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "StrongPass123!"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
