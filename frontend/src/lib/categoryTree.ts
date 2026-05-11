    import type { CategoryKind, CategoryRead } from '../api/categories'
  
    // Строит данные для Mantine Select из плоского списка категорий: для каждой
    // категории формирует полный путь от корня через ' → '. Например:
    //   «Расходы» (root) → label "Расходы"
    //   «Продукты» (parent_id=Расходы) → label "Расходы → Продукты"
    //   «Бакалея» (parent_id=Продукты) → label "Расходы → Продукты → Бакалея"
    //
    // Опциональный filterKind ограничивает результат категориями указанного
    // типа (income/expense). Используется в форме транзакции: для расхода
    // показываем только расходные категории, для дохода — только доходные.
    export function buildCategoryOptions(
      categories: CategoryRead[],
      filterKind?: CategoryKind,
    ): { value: string; label: string }[] {
      // Индекс по id для быстрого доступа к родителю при построении пути.
      // Строим по ВСЕМ категориям (не отфильтрованным), потому что путь к
      // отфильтрованной категории может пролегать через её родителя — он
      // нужен для названия, даже если в Select его самого нет.
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
  
      const filtered = filterKind
        ? categories.filter((c) => c.kind === filterKind)
        : categories
  
      const options = filtered.map((c) => ({
        value: String(c.id),
        label: pathOf(c),
      }))
      options.sort((a, b) => a.label.localeCompare(b.label, 'ru'))
      return options
    }