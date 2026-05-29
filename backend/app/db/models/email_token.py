"""Модель EmailToken — одноразовый токен для подтверждения почты и сброса пароля.

Зачем отдельная таблица, а не stateless-JWT: токены должны быть **одноразовыми**
и иметь срок жизни. После использования (подтвердил почту / сменил пароль) токен
помечается used_at и больше не сработает; истёкшие — отсекаются по expires_at.
Stateless-токен так просто не «погасить».

Безопасность: в БД хранится НЕ сам токен, а его SHA-256 хэш (как с паролями —
не храним секрет в открытом виде). Сырой токен уходит только в письмо-ссылку;
при переходе по ссылке его хэшируют и ищут совпадение. Даже при утечке дампа БД
действующие токены по хэшу не восстановить.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


# native_enum=False — VARCHAR + CHECK (как у Transaction.kind): проще миграции,
# переносимо на любую SQL-БД.
EmailTokenPurpose = SAEnum(
    "verify_email",
    "reset_password",
    name="email_token_purpose",
    native_enum=False,
)


class EmailToken(Base):
    """Одноразовый токен, отправляемый на почту."""
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 хэш сырого токена (64 hex-символа). Индекс — поиск по нему при
    # переходе по ссылке.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    purpose: Mapped[str] = mapped_column(EmailTokenPurpose, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Когда токен был использован. NULL = ещё действует (если не истёк).
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<EmailToken id={self.id} owner_id={self.owner_id} "
            f"purpose={self.purpose} used={self.used_at is not None}>"
        )
