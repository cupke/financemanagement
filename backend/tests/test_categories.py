from httpx import AsyncClient


async def test_create_expense_category(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Еда", "kind": "expense"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Еда"
    assert body["kind"] == "expense"
    assert body["parent_id"] is None


async def test_create_income_category(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Зарплата", "kind": "income"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "income"


async def test_create_subcategory(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    parent = await client.post(
        "/api/v1/categories",
        json={"name": "Еда", "kind": "expense"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]

    child = await client.post(
        "/api/v1/categories",
        json={"name": "Кафе", "kind": "expense", "parent_id": parent_id},
        headers=auth_headers,
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent_id


async def test_subcategory_kind_must_match_parent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    parent = await client.post(
        "/api/v1/categories",
        json={"name": "Расходы", "kind": "expense"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]

    bad = await client.post(
        "/api/v1/categories",
        json={"name": "Странная", "kind": "income", "parent_id": parent_id},
        headers=auth_headers,
    )
    assert bad.status_code == 400


async def test_duplicate_name_on_same_level_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"name": "Транспорт", "kind": "expense"}
    first = await client.post("/api/v1/categories", json=payload, headers=auth_headers)
    assert first.status_code == 201
    second = await client.post("/api/v1/categories", json=payload, headers=auth_headers)
    assert second.status_code == 409


async def test_list_categories_with_kind_filter(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/v1/categories",
        json={"name": "Зарплата", "kind": "income"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/categories",
        json={"name": "Еда", "kind": "expense"},
        headers=auth_headers,
    )

    all_resp = await client.get("/api/v1/categories", headers=auth_headers)
    assert len(all_resp.json()) == 2

    expense_only = await client.get(
        "/api/v1/categories?kind=expense", headers=auth_headers
    )
    body = expense_only.json()
    assert len(body) == 1
    assert body[0]["kind"] == "expense"


async def test_update_category_name(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/categories",
        json={"name": "Старое", "kind": "expense"},
        headers=auth_headers,
    )
    category_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"name": "Новое"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Новое"


async def test_category_cannot_be_own_parent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/v1/categories",
        json={"name": "Сама себе", "kind": "expense"},
        headers=auth_headers,
    )
    category_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"parent_id": category_id},
        headers=auth_headers,
    )
    assert response.status_code == 400


async def test_delete_category_cascades_children(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    parent = await client.post(
        "/api/v1/categories",
        json={"name": "Родитель", "kind": "expense"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        "/api/v1/categories",
        json={"name": "Ребёнок", "kind": "expense", "parent_id": parent_id},
        headers=auth_headers,
    )
    child_id = child.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/categories/{parent_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204

    # Ребёнок тоже должен исчезнуть (ON DELETE CASCADE)
    child_resp = await client.get(
        f"/api/v1/categories/{child_id}", headers=auth_headers
    )
    assert child_resp.status_code == 404


async def test_categories_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/categories")
    assert response.status_code == 401
