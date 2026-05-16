// Конвертация дат между «как видит юзер» (local) и «как хранит бэк» (UTC).
//
// Зачем нужно: Mantine 9 DateTimePicker / DatePickerInput работают с naive ISO
// строками ("2026-05-16T17:08:00", без Z/offset) и интерпретируют их как
// локальное время пользователя. Бэк хранит все даты в TIMESTAMPTZ и через
// _ensure_aware_utc трактует naive как UTC. Если фронт отправит naive
// без конвертации — для юзера в МСК (+3) случится сдвиг на 3 часа:
// «сегодня 23:00 МСК» → бэк думает «23:00 UTC = 02:00 завтра МСК»,
// что может всплыть как ошибка «дата в будущем» или как неправильный
// эффект на balance относительно opening_date.
//
// Правило:
// - При ОТПРАВКЕ на бэк (POST/PATCH): localToUtcIso(values.field).
// - При ПОДГРУЗКЕ в picker для отображения: utcToLocalIso(api.field).
// - Picker не понимает таймзону, ему нужна local строка.


// Naive local ISO ("2026-05-16T17:00:00") → UTC ISO с Z.
// new Date(naiveIso) парсит как local time, .toISOString() даёт UTC.
// Если на входе уже aware ISO (с Z или offset) — корректно нормализуется в UTC.
export function localToUtcIso(localIso: string): string {
  return new Date(localIso).toISOString()
}


// UTC ISO (с Z или offset) → naive local ISO для DateTimePicker.
// new Date(utcIso) корректно парсит aware строку, дальше извлекаем
// локальные компоненты и склеиваем без таймзоны.
export function utcToLocalIso(utcIso: string): string {
  const d = new Date(utcIso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}


// UTC ISO → локальный день в формате "YYYY-MM-DD".
// Используется для DatePickerInput (он работает с date-only без времени).
// Например, фильтр транзакций «с 01.05» — picker ожидает "2026-05-01",
// а в filters.from_date хранится UTC "2026-04-30T21:00:00.000Z" (для МСК).
export function utcToLocalDay(utcIso: string): string {
  const d = new Date(utcIso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
