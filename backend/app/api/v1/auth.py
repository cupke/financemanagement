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

from app.db.models.user import User
from app.db.session import get_session
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.security import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


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
