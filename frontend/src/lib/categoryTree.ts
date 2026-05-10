  import type { CategoryRead } from '../api/categories'

  // Строит данные для Mantine Select из плоского списка категорий: для каждой
  // категории формирует полный путь от корня через ' → '. Например:
  //   «Расходы» (root) → label "Расходы"
  //   «Продукты» (parent_id=Расходы) → label "Расходы → Продукты"
  //   «Бакалея» (parent_id=Продукты) → label "Расходы → Продукты → Бакалея"
  //
  // Преимущество перед отступами через пробелы: текст не «уезжает» в инпуте
  // после выбора, видно полный контекст категории, и поиск работает по любой
  // части пути (наберёшь "бакал" — найдёт всю цепочку).
  export function buildCategoryOptions(
    categories: CategoryRead[],
  ): { value: string; label: string }[] {
    // Индекс по id для быстрого доступа к родителю при построении пути.
    const byId = new Map<number, CategoryRead>()
    for (const cat of categories) byId.set(cat.id, cat)

    function pathOf(cat: CategoryRead): string {
      const parts: string[] = [cat.name]
      let currentParentId: number | null = cat.parent_id
      // Защита от потенциальных циклов (на бэке есть базовая защита от
      // самоссылок, но глубокие циклы не проверяются — см. раздел 22 контекста).
      // Лимит 10 уровней безопаснее, чем рисковать бесконечным циклом в UI.
      let safety = 0
      while (currentParentId !== null && safety < 10) {
        const parent = byId.get(currentParentId)
        if (!parent) break
        parts.unshift(parent.name)
        currentParentId = parent.parent_id
        safety++
      }
      return parts.join(' → ')
    }

    // Сортируем по полному пути алфавитно. Это группирует поддеревья:
    // "Расходы", "Расходы → Продукты", "Расходы → Продукты → Бакалея" идут подряд.
    const options = categories.map((c) => ({
      value: String(c.id),
      label: pathOf(c),
    }))
    options.sort((a, b) => a.label.localeCompare(b.label, 'ru'))
    return options
  }