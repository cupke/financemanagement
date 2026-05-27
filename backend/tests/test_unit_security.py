"""Unit-тесты для модуля app.security — без БД, без HTTP.

Демонстрирует модульное тестирование чистых функций (изолированных от
внешних зависимостей). Запускаются за миллисекунды.
"""
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_returns_argon2_hash() -> None:
    """Хэш всегда начинается с маркера алгоритма Argon2id."""
    h = hash_password("MyStrongPass123!")
    assert h.startswith("$argon2id$")


def test_hash_password_is_non_deterministic() -> None:
    """Два хэша одного пароля разные — потому что соль внутри хэша случайная.
    Это защита от rainbow tables."""
    h1 = hash_password("samepass")
    h2 = hash_password("samepass")
    assert h1 != h2


def test_verify_password_accepts_correct() -> None:
    h = hash_password("correctPassword42")
    assert verify_password("correctPassword42", h) is True


def test_verify_password_rejects_wrong() -> None:
    h = hash_password("correctPassword42")
    assert verify_password("WRONG", h) is False


def test_jwt_roundtrip_preserves_subject() -> None:
    """Что положили в токен — то и достанем обратно после декодирования."""
    token = create_access_token(subject="42")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"


def test_decode_invalid_token_returns_none_or_raises() -> None:
    """Битый токен не должен молча проходить."""
    result = None
    try:
        result = decode_access_token("not.a.real.token")
    except Exception:
        return  # ок — выбросил исключение
    assert result is None  # ок — вернул None
