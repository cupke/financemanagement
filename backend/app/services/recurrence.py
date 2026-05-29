"""Чистая логика расписания повторяющихся операций.

Здесь только арифметика дат: «дано время операции и правило (частота +
интервал) — когда следующая». Никаких обращений к БД, поэтому функции
тривиально покрываются модульными тестами (раздел 4 ВКР).

Главная тонкость — перенос «дня месяца» при monthly/yearly: если правило
стартовало 31 января, то «через месяц» — это 28 (или 29) февраля, а не
несуществующее 31 февраля. Решаем клампингом дня к последнему дню целевого
месяца.
"""
from calendar import monthrange
from datetime import datetime, timedelta

# Защитный потолок на число операций, материализуемых за один прогон одного
# правила. Бережёт от «убегания» (например, ежедневное правило, стартовавшее
# годы назад, или испорченные данные). Хватает на ~2.7 года ежедневных
# операций; остаток догенерируется при следующем заходе.
MAX_OCCURRENCES_PER_RUN = 1000


def _add_months(
    dt: datetime, months: int, anchor_day: int | None = None
) -> datetime:
    """Прибавить months календарных месяцев, кламируя день к концу месяца.

    Пример: _add_months(31 января, 1) → 28/29 февраля.
    Время суток (часы/минуты) и tzinfo сохраняются.

    anchor_day — «желаемое» число месяца (день старта правила). Если задан,
    день берётся от него, а не от dt.day. Это лечит «сползание даты»: для
    правила с 31-го числа цепочка 31 янв → 28 фев → 31 мар (а не → 28 мар),
    потому что в марте мы снова целимся в 31, а не в обрезанное февральское 28.
    """
    # Переводим (год, месяц) в сквозной индекс месяцев, прибавляем, обратно.
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    # Кламп дня: в феврале нет 30/31 — берём последний реальный день месяца.
    # Целимся в anchor_day (исходное число старта), если он задан.
    last_day = monthrange(year, month)[1]
    day = min(anchor_day if anchor_day is not None else dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(
    current: datetime,
    frequency: str,
    interval: int,
    anchor_day: int | None = None,
) -> datetime:
    """Следующий момент операции после current по правилу (frequency, interval).

    - daily   → +interval дней
    - weekly  → +interval недель
    - monthly → +interval месяцев (с клампингом дня)
    - yearly  → +interval лет (29 февраля → 28 февраля в невисокосный год)

    anchor_day — исходное число дня месяца у правила (start_at.day). Передаётся
    для monthly/yearly, чтобы день не «сползал» после короткого месяца: без него
    31 янв → 28 фев → 28 мар; с ним 31 янв → 28 фев → 31 мар.
    """
    if frequency == "daily":
        return current + timedelta(days=interval)
    if frequency == "weekly":
        return current + timedelta(weeks=interval)
    if frequency == "monthly":
        return _add_months(current, interval, anchor_day)
    if frequency == "yearly":
        return _add_months(current, interval * 12, anchor_day)
    raise ValueError(f"Неизвестная частота: {frequency!r}")
