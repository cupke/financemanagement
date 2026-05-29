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


def _add_months(dt: datetime, months: int) -> datetime:
    """Прибавить months календарных месяцев, кламируя день к концу месяца.

    Пример: _add_months(31 января, 1) → 28/29 февраля.
    Время суток (часы/минуты) и tzinfo сохраняются.
    """
    # Переводим (год, месяц) в сквозной индекс месяцев, прибавляем, обратно.
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    # Кламп дня: в феврале нет 30/31 — берём последний реальный день месяца.
    last_day = monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(current: datetime, frequency: str, interval: int) -> datetime:
    """Следующий момент операции после current по правилу (frequency, interval).

    - daily   → +interval дней
    - weekly  → +interval недель
    - monthly → +interval месяцев (с клампингом дня)
    - yearly  → +interval лет (29 февраля → 28 февраля в невисокосный год)
    """
    if frequency == "daily":
        return current + timedelta(days=interval)
    if frequency == "weekly":
        return current + timedelta(weeks=interval)
    if frequency == "monthly":
        return _add_months(current, interval)
    if frequency == "yearly":
        return _add_months(current, interval * 12)
    raise ValueError(f"Неизвестная частота: {frequency!r}")
