"""Сервис одноразовых email-токенов (подтверждение почты, сброс пароля).

Поток:
- `issue_token` — сгенерировать криптослучайный токен, сохранить его SHA-256 хэш
  с назначением и сроком жизни, вернуть СЫРОЙ токен (он уйдёт в письмо-ссылку).
  Прежние неиспользованные токены того же назначения у пользователя гасятся,
  чтобы действовала только последняя ссылка.
- `consume_token` — по сырому токену из ссылки найти действующую запись
  (нужное назначение, не использован, не истёк), пометить использованной и
  вернуть owner_id. Если токен невалиден/просрочен/уже использован — вернуть None.

В БД хранится только хэш — см. docstring модели EmailToken.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.email_token import EmailToken


def _hash_token(raw_token: str) -> str:
    """SHA-256 хэш токена в hex (64 символа)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def issue_token(
    session: AsyncSession,
    owner_id: int,
    purpose: str,
    ttl_hours: int,
) -> str:
    """Выпустить новый одноразовый токен. Возвращает СЫРОЙ токен для ссылки.

    Не делает commit — вызывающий роутер коммитит сам (часто вместе с другими
    изменениями в той же транзакции).
    """
    # Гасим прежние неиспользованные токены того же назначения: после запроса
    # нового сброса старая ссылка не должна работать.
    await session.execute(
        update(EmailToken)
        .where(EmailToken.owner_id == owner_id)
        .where(EmailToken.purpose == purpose)
        .where(EmailToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )

    raw_token = secrets.token_urlsafe(32)
    token = EmailToken(
        owner_id=owner_id,
        token_hash=_hash_token(raw_token),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    session.add(token)
    return raw_token


async def consume_token(
    session: AsyncSession,
    raw_token: str,
    purpose: str,
) -> int | None:
    """Проверить и «погасить» токен. Возвращает owner_id или None.

    None — если токена нет, он другого назначения, уже использован или истёк.
    Не делает commit — коммитит роутер.
    """
    token_hash = _hash_token(raw_token)
    token = await session.scalar(
        select(EmailToken)
        .where(EmailToken.token_hash == token_hash)
        .where(EmailToken.purpose == purpose)
    )
    if token is None or token.used_at is not None:
        return None
    # expires_at из БД — tz-aware; сравниваем по UTC. Проверку срока оставляем
    # в Python (а не в SQL), чтобы не зависеть от того, как драйвер хранит
    # TIMESTAMPTZ (на SQLite — naive).
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None

    # Атомарное «застолбление»: помечаем used_at ТОЛЬКО если токен ещё не
    # использован. Условие `used_at IS NULL` в самом UPDATE + RETURNING
    # защищает от гонки двойного гашения: если два запроса пришли с одним
    # токеном одновременно, выиграет ровно один (его UPDATE затронет строку и
    # вернёт owner_id), второй получит 0 строк → None. Без этого оба прочитали
    # бы used_at=None и оба прошли бы (например, двойной сброс пароля).
    result = await session.execute(
        update(EmailToken)
        .where(EmailToken.id == token.id)
        .where(EmailToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
        .returning(EmailToken.owner_id)
    )
    return result.scalar_one_or_none()
