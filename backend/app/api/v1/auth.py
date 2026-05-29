"""Роутер /auth: регистрация и вход.

Архитектурный комментарий: эндпоинты намеренно «тонкие» — вся бизнес-логика
(хэш пароля, проверка уникальности, выпуск токена) делается через сервисные
функции из app.security и прямые SQLAlchemy-запросы. Когда логики станет
больше, вынесем её в отдельный сервисный слой `app/services/auth_service.py`
(требование МУ: трёхзвенная архитектура контроллер → сервис → репозиторий,
п. 4.9.Б).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.token import TokenResponse
from app.schemas.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserRead,
    VerifyEmailRequest,
)
from app.security import create_access_token, hash_password, verify_password
# Импортируем модули целиком (а не функции по именам) — так их легко подменять
# в тестах (monkeypatch app.services.email.send_verification_email и т.п.).
from app.services import email as email_service
from app.services import tokens as token_service


router = APIRouter(prefix="/auth", tags=["auth"])

# Назначения токенов — строки, совпадающие с CHECK на модели EmailToken.
_PURPOSE_VERIFY = "verify_email"
_PURPOSE_RESET = "reset_password"


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Создать нового пользователя.

    Шаги:
    1. Проверить, что email ещё не занят (упреждающий запрос).
    2. Захэшировать пароль Argon2id.
    3. Сохранить пользователя в БД.
    4. Вернуть созданную запись (без password_hash — об этом заботится UserRead).

    Замечание о гонках: между шагом 1 и 3 теоретически кто-то ещё может
    зарегистрироваться на тот же email. От этого нас защищает UNIQUE-индекс
    в БД — второй запрос упадёт с IntegrityError. Здесь мы пока не ловим
    его специально (получится HTTP 500); добавим обработку, когда будет
    глобальный exception-handler.
    """
    existing = await session.scalar(
        select(User).where(User.email == payload.email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)  # подтянуть id и created_at, проставленные БД

    # Письмо для подтверждения почты при регистрации НЕ шлём автоматически:
    # пользователь запрашивает его сам кнопкой на странице профиля (эндпоинт
    # /resend-verification). Так не рассылаем писем тем, кто не собирается
    # подтверждать почту, и бережём лимиты почтового отправителя.
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход: обмен email+пароль на JWT access-токен",
)
async def login(
    payload: UserLogin,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Проверить учётные данные и выдать access-токен.

    Безопасность: в случае неверных email/пароля возвращаем одно и то же
    сообщение — иначе через различия в ответах злоумышленник может узнать,
    зарегистрирован ли email (user enumeration, OWASP).
    """
    user = await session.scalar(
        select(User).where(User.email == payload.email)
    )
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный email или пароль",
    )
    if user is None:
        raise invalid_credentials
    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials

    token = create_access_token(subject=user.id)
    return TokenResponse(access_token=token)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Подтвердить email по токену из письма",
)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Подтвердить почту: гасим токен и ставим email_verified=True.

    Идемпотентность: если пользователь уже подтверждён, повторный валидный
    переход (или ранее использованный токен) вернёт понятную 400 — это не
    мешает работе. Невалидный/просроченный токен — тоже 400.
    """
    owner_id = await token_service.consume_token(
        session, payload.token, _PURPOSE_VERIFY
    )
    if owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка недействительна или устарела",
        )
    user = await session.get(User, owner_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка недействительна или устарела",
        )
    user.email_verified = True
    await session.commit()
    return MessageResponse(detail="Почта подтверждена")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Повторно отправить письмо для подтверждения почты",
)
async def resend_verification(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Повторно выслать письмо подтверждения (для залогиненного пользователя)."""
    if current_user.email_verified:
        return MessageResponse(detail="Почта уже подтверждена")
    raw_token = await token_service.issue_token(
        session, current_user.id, _PURPOSE_VERIFY,
        settings.email_verify_token_ttl_hours,
    )
    await session.commit()
    await email_service.send_verification_email(current_user.email, raw_token)
    return MessageResponse(detail="Письмо отправлено")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Запросить ссылку для сброса пароля",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Отправить письмо со ссылкой сброса пароля.

    Безопасность (anti-enumeration, OWASP): ответ ВСЕГДА одинаковый, существует
    email или нет. Иначе по разнице ответов можно выяснить, какие адреса
    зарегистрированы. Письмо уходит только реально существующему пользователю.
    """
    user = await session.scalar(
        select(User).where(User.email == payload.email)
    )
    if user is not None:
        raw_token = await token_service.issue_token(
            session, user.id, _PURPOSE_RESET,
            settings.password_reset_token_ttl_hours,
        )
        await session.commit()
        await email_service.send_reset_email(user.email, raw_token)

    return MessageResponse(
        detail="Если такой email зарегистрирован, мы отправили на него ссылку для сброса пароля",
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Установить новый пароль по токену из письма",
)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Сбросить пароль по одноразовому токену из письма.

    Токен одноразовый: после успешного сброса повторно не сработает. Заодно
    считаем почту подтверждённой — раз человек получил письмо по этому адресу.
    """
    owner_id = await token_service.consume_token(
        session, payload.token, _PURPOSE_RESET
    )
    if owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка недействительна или устарела",
        )
    user = await session.get(User, owner_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка недействительна или устарела",
        )
    user.password_hash = hash_password(payload.new_password)
    # Успешный переход по ссылке из письма доказывает владение почтой.
    user.email_verified = True
    await session.commit()
    return MessageResponse(detail="Пароль изменён")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Сменить пароль (для залогиненного пользователя)",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Сменить пароль: проверяем текущий, сохраняем новый.

    Текущий пароль обязателен — чтобы при перехвате активной сессии нельзя было
    сменить пароль, не зная старого. JWT уже выданных токенов остаётся валидным
    до истечения (stateless) — это допустимое упрощение MVP.
    """
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текущий пароль неверен",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль должен отличаться от текущего",
        )
    current_user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return MessageResponse(detail="Пароль изменён")
