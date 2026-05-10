  // Утилиты форматирования. Пока маленькие — но в одном месте, чтобы потом
  // при добавлении новых форматов (даты, проценты) было куда складывать.

  // Форматирование суммы с учётом валюты: 99999.99 RUB → "99 999,99 ₽".
  // Intl.NumberFormat — стандарт ECMAScript, не требует библиотек. Для валют
  // без знака (например, нестандартный код) вернёт код в начале строки.
  export function formatMoney(amount: number | string, currencyCode: string): string {
    const num = typeof amount === 'string' ? Number(amount) : amount
    try {
      return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: currencyCode,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(num)
    } catch {
      // Если currencyCode невалидный (не ISO 4217) — fallback на просто число + код.
      return `${num.toFixed(2)} ${currencyCode}`
    }
  }

  // Список основных валют для Select-инпута. Расширим, когда понадобится.
  export const COMMON_CURRENCIES = [
    { value: 'RUB', label: 'RUB — Российский рубль' },
    { value: 'USD', label: 'USD — Доллар США' },
    { value: 'EUR', label: 'EUR — Евро' },
    { value: 'GBP', label: 'GBP — Фунт стерлингов' },
    { value: 'CNY', label: 'CNY — Юань' },
    { value: 'CHF', label: 'CHF — Швейцарский франк' },
  ]