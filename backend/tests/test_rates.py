"""Интеграционные тесты эндпоинтов /rates (курсы валют ЦБ РФ).

Курсы засеваются прямо в БД с fetched_at = сегодня, чтобы cache-aside
(app.services.cbr_rates.get_rates_for_today) считал кеш свежим и НЕ ходил в
сеть к ЦБ во время теста — тесты детерминированы и работают офлайн.

Закрывает трассировку ФТ-10 (получение курсов валют ЦБ РФ).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exchange_rate import ExchangeRate


async def _seed_rate(
    session: AsyncSession,
    *,
    char_code: str,
    num_code: str,
    name: str,
    vunit_rate: str,
    nominal: int = 1,
    on_date: date | None = None,
) -> None:
    """Положить курс в БД с fetched_at = сейчас (свежий кеш — фетча у ЦБ не будет)."""
    rate_date = on_date or date.today()
    session.add(
        ExchangeRate(
            char_code=char_code,
            num_code=num_code,
            name=name,
            nominal=nominal,
            value=Decimal(vunit_rate) * nominal,
            vunit_rate=Decimal(vunit_rate),
            rate_date=rate_date,
            fetched_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def test_rates_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/rates")).status_code == 401
    assert (await client.get("/api/v1/rates/USD")).status_code == 401


async def test_rates_list_returns_seeded_cache_sorted(
    client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession
) -> None:
    await _seed_rate(session, char_code="USD", num_code="840", name="Доллар США", vunit_rate="90.5000")
    await _seed_rate(session, char_code="EUR", num_code="978", name="Евро", vunit_rate="98.1234")

    resp = await client.get("/api/v1/rates", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Курсы отсортированы по char_code: EUR раньше USD.
    assert [item["char_code"] for item in data["items"]] == ["EUR", "USD"]
    assert data["rate_date"] == date.today().isoformat()
    usd = next(item for item in data["items"] if item["char_code"] == "USD")
    assert Decimal(usd["vunit_rate"]) == Decimal("90.5")


async def test_rate_by_code_is_case_insensitive(
    client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession
) -> None:
    await _seed_rate(session, char_code="USD", num_code="840", name="Доллар США", vunit_rate="90.5000")

    # Запрашиваем нижним регистром — должен найти.
    resp = await client.get("/api/v1/rates/usd", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["char_code"] == "USD"
    assert Decimal(data["vunit_rate"]) == Decimal("90.5")


async def test_rate_by_unknown_code_returns_404(
    client: AsyncClient, auth_headers: dict[str, str], session: AsyncSession
) -> None:
    # Сеем хотя бы один свежий курс, чтобы кеш считался актуальным (без сети к ЦБ),
    # но запрашиваем валюту, которой в фиде нет.
    await _seed_rate(session, char_code="USD", num_code="840", name="Доллар США", vunit_rate="90.5000")

    resp = await client.get("/api/v1/rates/JPY", headers=auth_headers)
    assert resp.status_code == 404
