"""Отправка email через SMTP.

Реализация на stdlib `smtplib` (без сторонних зависимостей). Блокирующий вызов
выносим в пул потоков через `asyncio.to_thread`, чтобы не стопорить event loop.

Отправка — **best-effort**: при ошибке (SMTP недоступен и т.п.) функция вернёт
False и залогирует, но НЕ бросит исключение. Так регистрация и запрос сброса
пароля не падают из-за проблем с почтой; пользователь сможет повторить.

Письма строятся как простой текст (для учебного проекта достаточно; HTML-шаблоны
вынесены в «перспективы развития»). Высокоуровневые функции
`send_verification_email` / `send_reset_email` собирают ссылку на фронтенд и
вызываются из роутера через импорт модуля (`from app.services import email`),
что позволяет подменять их в тестах.
"""
import logging
import smtplib
from asyncio import to_thread
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("app.email")


def _send_sync(to: str, subject: str, body: str) -> None:
    """Синхронная отправка одного письма (выполняется в отдельном потоке)."""
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    # Implicit SSL (порт 465, напр. Яндекс) — соединение сразу шифрованное,
    # через SMTP_SSL. Иначе обычный SMTP, при необходимости STARTTLS (порт 587).
    if settings.smtp_use_ssl:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with server:
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


async def send_email(to: str, subject: str, body: str) -> bool:
    """Отправить письмо. Возвращает True при успехе, False при ошибке (best-effort)."""
    # Режим «в лог»: не трогаем SMTP, печатаем письмо в лог (см. config).
    # Уровень WARNING — чтобы строка точно прошла фильтр логов uvicorn (INFO
    # по умолчанию может быть скрыт). Это не ошибка, просто dev-режим.
    if settings.email_log_only:
        logger.warning(
            "[EMAIL (log-only) → %s] %s\n%s\n%s\n%s",
            to, subject, "-" * 50, body, "-" * 50,
        )
        return True
    try:
        await to_thread(_send_sync, to, subject, body)
        return True
    except Exception as exc:  # noqa: BLE001 — намеренно глушим любую ошибку SMTP
        logger.warning("Не удалось отправить письмо на %s: %r", to, exc)
        return False


async def send_verification_email(to: str, token: str) -> bool:
    """Письмо со ссылкой подтверждения почты."""
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    body = (
        "Здравствуйте!\n\n"
        "Вы зарегистрировались в FinTrack. Подтвердите адрес почты, перейдя "
        f"по ссылке:\n\n{link}\n\n"
        f"Ссылка действует {settings.email_verify_token_ttl_hours} ч. "
        "Если это были не вы — просто проигнорируйте письмо."
    )
    return await send_email(to, "Подтверждение почты — FinTrack", body)


async def send_reset_email(to: str, token: str) -> bool:
    """Письмо со ссылкой сброса пароля."""
    link = f"{settings.frontend_base_url}/reset-password?token={token}"
    body = (
        "Здравствуйте!\n\n"
        "Поступил запрос на сброс пароля в FinTrack. Чтобы задать новый "
        f"пароль, перейдите по ссылке:\n\n{link}\n\n"
        f"Ссылка действует {settings.password_reset_token_ttl_hours} ч. "
        "Если вы не запрашивали сброс — проигнорируйте письмо, пароль не изменится."
    )
    return await send_email(to, "Сброс пароля — FinTrack", body)
