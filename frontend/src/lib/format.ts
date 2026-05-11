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

    // Русская плюрализация: возвращает правильное окончание для числа.
  // Примеры:
  //   pluralRu(1, 'счёт', 'счёта', 'счетов')   → 'счёт'
  //   pluralRu(2, 'счёт', 'счёта', 'счетов')   → 'счёта'
  //   pluralRu(11, 'счёт', 'счёта', 'счетов')  → 'счетов'
  //
  // Правила: формы зависят от двух последних цифр.
  export function pluralRu(
    count: number,
    one: string,
    few: string,
    many: string,
  ): string {
    const mod10 = count % 10
    const mod100 = count % 100
    if (mod10 === 1 && mod100 !== 11) return one
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
    return many
  }

      // Мета-описание типов счёта: метка для UI и эмодзи для иконки.
    // Локализовано на русском, потому что отображается прямо в формах
    // и карточках счетов.
    export const ACCOUNT_KIND_META: Record<
      'card' | 'cash' | 'savings' | 'credit' | 'e_wallet' | 'other',
      { label: string; emoji: string }
    > = {
      card: { label: 'Банковская карта', emoji: '💳' },
      cash: { label: 'Наличные', emoji: '💵' },
      savings: { label: 'Накопительный', emoji: '🏦' },
      credit: { label: 'Кредитная карта', emoji: '💰' },
      e_wallet: { label: 'Электронный кошелёк', emoji: '📱' },
      other: { label: 'Прочее', emoji: '📦' },
    }

    // Опции для Mantine Select: { value, label } — формат, который ждёт компонент.
    // Эмодзи приклеиваем к label, чтобы было видно прямо в выпадающем списке.
    export const ACCOUNT_KIND_OPTIONS = (
      Object.keys(ACCOUNT_KIND_META) as Array<keyof typeof ACCOUNT_KIND_META>
    ).map((value) => ({
      value,
      label: `${ACCOUNT_KIND_META[value].emoji} ${ACCOUNT_KIND_META[value].label}`,
    }))