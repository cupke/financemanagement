"""Роутер /rates: чтение курсов валют ЦБ РФ.

  Только GET-эндпоинты — данные читаются у ЦБ, пользователь их не редактирует.
  Авторизация требуется (как и для всего остального API), хотя курсы — публичная
  информация: единый стиль защиты упрощает аудит.
  """
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.rate import RateRead, RatesListResponse
from app.services.cbr_rates import get_rate_by_code, get_rates_for_today


router = APIRouter(prefix="/rates", tags=["rates"])


@router.get(
      "",
      response_model=RatesListResponse,
      summary="Все актуальные курсы валют по данным ЦБ РФ",
  )
async def list_rates(
      session: AsyncSession = Depends(get_session),
      _: User = Depends(get_current_user),
  ) -> RatesListResponse:
      """Вернуть список всех валют с курсом к рублю на актуальную дату ЦБ.

      Источник — ежедневный фид https://www.cbr.ru/scripts/XML_daily.asp,
      кешируется в БД (см. app.services.cbr_rates). В выходные ЦБ отдаёт курсы
      последнего рабочего дня — в `rate_date` это будет видно.

      Возможные коды:
      - 200 — есть актуальные курсы (или fallback на последний кеш).
      - 503 — ЦБ недоступен И в БД нет ни одной строки (первый запуск без сети).
      """
      try:
          rates = await get_rates_for_today(session)
      except Exception as exc:
          raise HTTPException(
              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
              detail=f"Курсы ЦБ временно недоступны: {exc.__class__.__name__}",
          ) from exc

      if not rates:
          raise HTTPException(
              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
              detail="Курсы ЦБ ещё не загружены",
          )

      return RatesListResponse(
          rate_date=rates[0].rate_date,
          fetched_at=rates[0].fetched_at,
          items=[RateRead.model_validate(r) for r in rates],
      )


@router.get(
      "/{char_code}",
      response_model=RateRead,
      summary="Курс конкретной валюты по буквенному коду (USD, EUR, ...)",
  )
async def get_rate(
      char_code: str,
      session: AsyncSession = Depends(get_session),
      _: User = Depends(get_current_user),
  ) -> RateRead:
      """Вернуть актуальный курс одной валюты. char_code регистронезависимый."""
      rate = await get_rate_by_code(session, char_code)
      if rate is None:
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail=f"Валюта {char_code.upper()} не найдена в фиде ЦБ",
          )
      return RateRead.model_validate(rate)