"""Криптографические утилиты: хэширование паролей и JWT-токены.

Этот модуль изолирует все операции с криптографией в одном месте:
- хэширование/проверка паролей (Argon2id),
- выпуск/декодирование JWT access-токенов.

Все функции — чистые (без обращений к БД), что упрощает их тестирование
unit-тестами (требование МУ ВКР, раздел 4 «Тестирование»).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import settings


# Один экземпляр PasswordHasher на процесс (паттерн Singleton).
# Параметры по умолчанию у argon2-cffi соответствуют рекомендациям OWASP 2023:
# time_cost=3, memory_cost=64 MiB, parallelism=4.
_password_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Захэшировать пароль алгоритмом Argon2id.

    Возвращает строку вида `$argon2id$v=19$m=65536,t=3,p=4$...$...`,
    в которой уже зашита соль, параметры и сам хэш — отдельно соль хранить
    не нужно. Это и пишем в `users.password_hash`.
    """
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Проверить, что пароль соответствует ранее сохранённому хэшу.

    Возвращает True, если совпадает, иначе False. Никогда не выбрасывает
    исключений наружу — это удобнее для вызывающего кода.
    """
    try:
        _password_hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Любая другая ошибка (повреждённый хэш и т.п.) — тоже неуспешная проверка.
        return False
    return True


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    """Выпустить JWT access-токен.

    Параметр `subject` — то, что мы хотим зашифровать в токене как идентификатор
    пользователя (обычно user_id). Кладём его в стандартное claim `sub`.

    Также добавляем `exp` (срок истечения) и `iat` (момент выпуска) — это
    стандартные JWT-claims, которые библиотека PyJWT понимает автоматически
    (например, при декодировании сама проверяет, не истёк ли токен).
    """
    expires_minutes = expires_minutes or settings.jwt_access_token_expires_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Расшифровать и проверить JWT access-токен.

    При успехе возвращает payload — словарь с claims (`sub`, `iat`, `exp`).
    При проблемах (плохая подпись, истёк срок, мусор вместо токена) выбросит
    `jwt.PyJWTError` или одного из его наследников. Вызывающий код (например,
    зависимость get_current_user) должен это перехватить и вернуть HTTP 401.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
