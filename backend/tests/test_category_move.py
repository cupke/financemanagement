"""Тест переноса категории под другого родителя (PATCH parent_id).

Дополняет:
- test_categories.py::test_update_category_name — переименование;
- test_correctness_hardening.py::test_category_cannot_move_into_own_subtree — запрет цикла.
Здесь — успешный перенос и перенос в корень.
"""
from httpx import AsyncClient


async def _create(
    client: AsyncClient,
    auth_headers: dict[str, str],
    name: str,
    parent_id: int | None = None,
) -> int:
    body: dict[str, object] = {"name": name, "kind": "expense"}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = await client.post("/api/v1/categories", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_move_category_to_another_parent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    a = await _create(client, auth_headers, "A")
    b = await _create(client, auth_headers, "B")
    child = await _create(client, auth_headers, "Подкатегория", parent_id=a)

    # Переносим child из-под A под B.
    resp = await client.patch(
        f"/api/v1/categories/{child}",
        json={"parent_id": b},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["parent_id"] == b

    # Переносим child в корень (parent_id = null).
    resp = await client.patch(
        f"/api/v1/categories/{child}",
        json={"parent_id": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["parent_id"] is None
