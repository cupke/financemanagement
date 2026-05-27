  import { useEffect, useState } from 'react'
  import {
    ActionIcon,
    Badge,
    Button,
    Card,
    Container,
    Group,
    Loader,
    Select,
    Stack,
    Text,
    TextInput,
    Title,
    Tooltip,
  } from '@mantine/core'
  import { DatePickerInput } from '@mantine/dates'
  import { modals } from '@mantine/modals'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

  import { apiClient } from '../api/client'
  import { listAccountsRequest, type AccountRead } from '../api/accounts'
  import { listCategoriesRequest, type CategoryRead } from '../api/categories'
  import {
    deleteTransactionRequest,
    listTransactionsRequest,
    type TransactionKind,
    type TransactionListFilters,
    type TransactionRead,
  } from '../api/transactions'
  import { TransactionFormModal } from '../components/TransactionFormModal'
  import { localToUtcIso, utcToLocalDay } from '../lib/datetime'
  import { formatMoney } from '../lib/format'

  // Метаданные для отображения — цвет, знак, человекочитаемая метка.
  const KIND_META: Record<
    TransactionKind,
    { label: string; color: string; sign: string }
  > = {
    income: { label: 'Доход', color: 'green', sign: '+' },
    expense: { label: 'Расход', color: 'red', sign: '−' },
    transfer: { label: 'Перевод', color: 'blue', sign: '±' },
  }

  // Ключ группировки: "YYYY-MM-DD" в локальной зоне юзера (а не UTC) — чтобы
  // "сегодняшние" операции группировались по календарю пользователя.
  function dateKey(iso: string): string {
    const d = new Date(iso)
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  // Заголовок для группы: «Сегодня» / «Вчера» / «10 мая 2026».
  function formatDateHeader(key: string): string {
    const today = dateKey(new Date().toISOString())
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    const yesterdayKey = dateKey(yesterday.toISOString())

    if (key === today) return 'Сегодня'
    if (key === yesterdayKey) return 'Вчера'

    // Парсим обратно YYYY-MM-DD в Date через локальный конструктор (Y, M-1, D).
    // Не используем new Date(key) — он трактует "YYYY-MM-DD" как UTC, что
    // приводит к смещению на часовой пояс.
    const [y, m, d] = key.split('-').map(Number)
    return new Date(y, m - 1, d).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
  }

  // Группирует транзакции по дате (локальной). Возвращает массив пар
  // [dateKey, transactions[]] в порядке убывания даты — свежие группы первыми.
  function groupByDate(
    transactions: TransactionRead[],
  ): Array<[string, TransactionRead[]]> {
    const map = new Map<string, TransactionRead[]>()
    for (const tx of transactions) {
      const key = dateKey(tx.occurred_at)
      const arr = map.get(key) ?? []
      arr.push(tx)
      map.set(key, arr)
    }
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0]))
  }

  // Сводка доход/расход по валютам. Переводы не считаем — общий капитал
  // пользователя при переводе между его счетами не меняется.
  function computeTotals(
    transactions: TransactionRead[],
  ): Map<string, { income: number; expense: number }> {
    const totals = new Map<string, { income: number; expense: number }>()
    for (const tx of transactions) {
      if (tx.kind === 'transfer') continue
      const current = totals.get(tx.currency_code) ?? { income: 0, expense: 0 }
      if (tx.kind === 'income') current.income += Number(tx.amount)
      else current.expense += Number(tx.amount)
      totals.set(tx.currency_code, current)
    }
    return totals
  }

  export function TransactionsPage() {
    const [modalOpened, setModalOpened] = useState(false)
      // editingTx === null → модалка в режиме «создать новую» (или закрыта).
      // editingTx === TransactionRead → модалка в режиме «редактировать».
      // Хранятся отдельно от modalOpened, чтобы после закрытия плавно очистить
      // (иначе на исчезающей модалке моргнул бы режим «создать»).
      const [editingTx, setEditingTx] = useState<TransactionRead | null>(null)
      // Фильтры сохраняются в sessionStorage — между переходами на другие
      // страницы и обратно настройка не теряется. При запуске нового
      // браузерного сеанса возвращается дефолт «Этот месяц».
      const [filters, setFilters] = useState<TransactionListFilters>(() => {
        const saved = sessionStorage.getItem(TX_FILTERS_STORAGE_KEY)
        if (saved) {
          try {
            return JSON.parse(saved) as TransactionListFilters
          } catch {
            // повреждённое значение — игнорируем, идём в дефолт
          }
        }
        return getDefaultFilters()
      })

      // Каждое изменение фильтров пишем в sessionStorage, чтобы при возврате
      // на страницу (или открытии в новой вкладке того же сеанса) увидеть то же.
      useEffect(() => {
        sessionStorage.setItem(TX_FILTERS_STORAGE_KEY, JSON.stringify(filters))
      }, [filters])
    // Локальный поиск по заметкам — фильтрация на клиенте без перезапроса.
    const [searchQuery, setSearchQuery] = useState('')
    const queryClient = useQueryClient()

    const { data: transactions, isLoading, isError } = useQuery({
      queryKey: ['transactions', filters],
      queryFn: () => listTransactionsRequest(filters),
    })

    const { data: accounts = [] } = useQuery({
      queryKey: ['accounts'],
      queryFn: listAccountsRequest,
    })
     const { data: categories = [] } = useQuery({
        queryKey: ['categories'],
        queryFn: () => listCategoriesRequest(),
      })

    const accountById = new Map(accounts.map((a) => [a.id, a]))
    const categoryById = new Map(categories.map((c) => [c.id, c]))

    // Клиентская фильтрация по поисковому запросу (note). Не отправляем на бэк —
    // поиск интерактивный, не хотим дёргать сервер на каждое нажатие клавиши.
    const filteredTransactions = transactions
      ? searchQuery.trim() === ''
        ? transactions
        : transactions.filter((tx) =>
            (tx.note || '')
              .toLowerCase()
              .includes(searchQuery.trim().toLowerCase()),
          )
      : []

    const totals = computeTotals(filteredTransactions)

    const deleteMutation = useMutation({
      mutationFn: (id: number) => deleteTransactionRequest(id),
      onSuccess: () => {
        notifications.show({
          title: 'Операция удалена',
          message: 'Балансы счетов восстановлены',
          color: 'blue',
        })
        queryClient.invalidateQueries({ queryKey: ['transactions'] })
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onError: (error: any) => {
        notifications.show({
          title: 'Ошибка',
          message:
            error.response?.data?.detail || 'Не удалось удалить операцию',
          color: 'red',
        })
      },
    })

    const handleEdit = (tx: TransactionRead) => {
      setEditingTx(tx)
      setModalOpened(true)
    }

    const handleCreate = () => {
      setEditingTx(null)
      setModalOpened(true)
    }

    const handleExportCsv = async () => {
      try {
        // Передаём бэку те же фильтры, что применены на странице —
        // экспортируется ровно то, что юзер сейчас видит. limit/offset
        // выкидываем: пагинация в экспорт не нужна, нужны все совпадающие строки.
        const exportParams = Object.fromEntries(
          Object.entries(filters).filter(
            ([k, v]) =>
              k !== 'limit' &&
              k !== 'offset' &&
              v !== undefined &&
              v !== null &&
              v !== '',
          ),
        )
        const response = await apiClient.get('/api/v1/export/transactions.csv', {
          params: exportParams,
          responseType: 'blob',
        })
        const url = window.URL.createObjectURL(new Blob([response.data]))
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', 'fintrack-transactions.csv')
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
      } catch {
        notifications.show({
          title: 'Ошибка',
          message: 'Не удалось скачать CSV',
          color: 'red',
        })
      }
    }

    const handleModalClose = () => {
      setModalOpened(false)
      // Сбрасываем editingTx с задержкой, чтобы при закрытии модалки её
      // содержимое не моргнуло из «редактирования» в «создание» во время
      // анимации закрытия.
      setTimeout(() => setEditingTx(null), 200)
    }

    const handleDelete = (tx: TransactionRead) => {
      modals.openConfirmModal({
        title: 'Удалить операцию?',
        centered: true,
        children: (
          <Text size="sm">
            Удалить операцию на сумму{' '}
            <strong>{formatMoney(tx.amount, tx.currency_code)}</strong>? Балансы
            счетов будут восстановлены до этой операции.
          </Text>
        ),
        labels: { confirm: 'Удалить', cancel: 'Отмена' },
        confirmProps: { color: 'red' },
        onConfirm: () => deleteMutation.mutate(tx.id),
      })
    }

    return (
      <Container size="md" py="xl">
        <Group justify="space-between" mb="lg">
          <Title order={2}>История операций</Title>
          <Group gap="xs">
            <Button variant="light" onClick={handleExportCsv}>
              Экспорт CSV
            </Button>
            <Button onClick={handleCreate}>
              + Добавить операцию
            </Button>
          </Group>
        </Group>

        <FilterPanel
          filters={filters}
          onChange={setFilters}
          accounts={accounts}
          categories={categories}
        />

        <TextInput
          placeholder="Поиск по заметкам..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
          mt="md"
        />

        {/* Сводка дохода/расхода по валютам. Показывается только когда есть
            транзакции для подсчёта. Переводы в сводку не входят. */}
        {filteredTransactions.length > 0 && totals.size > 0 && (
          <Card withBorder p="md" mt="md" bg="light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))">
            <Stack gap="xs">
              <Text size="sm" c="dimmed" fw={500}>
                  Сводка · {formatPeriodLabel(filters)}
                </Text>
              {Array.from(totals.entries()).map(([currency, { income, expense }]) => {
                const net = income - expense
                return (
                  <Group key={currency} justify="space-between" wrap="wrap" gap="md">
                    <Group gap="lg" wrap="wrap">
                      <SummaryItem
                        label="Доход"
                        value={income}
                        currency={currency}
                        color="green"
                        sign="+"
                      />
                      <SummaryItem
                        label="Расход"
                        value={expense}
                        currency={currency}
                        color="red"
                        sign="−"
                      />
                    </Group>
                    <SummaryItem
                      label="Итого"
                      value={Math.abs(net)}
                      currency={currency}
                      color={net >= 0 ? 'green' : 'red'}
                      sign={net >= 0 ? '+' : '−'}
                    />
                  </Group>
                )
              })}
            </Stack>
          </Card>
        )}

        {isLoading && (
          <Container py="md">
            <Loader />
          </Container>
        )}

        {isError && (
          <Text c="red" mt="md">
            Не удалось загрузить операции.
          </Text>
        )}

        {transactions && filteredTransactions.length === 0 && !isLoading && (
          <Card withBorder p="xl" mt="md">
            <Stack align="center" gap="xs">
              <Text c="dimmed">
                {searchQuery.trim() !== ''
                  ? `Ничего не найдено по запросу «${searchQuery}»`
                  : 'Пока нет операций по выбранным фильтрам.'}
              </Text>
              {searchQuery.trim() === '' && (
                <Button variant="light" onClick={handleCreate}>
                  Добавить первую
                </Button>
              )}
            </Stack>
          </Card>
        )}

        {filteredTransactions.length > 0 && (
          <Stack gap="lg" mt="md">
            {groupByDate(filteredTransactions).map(([key, txs]) => (
              <Stack key={key} gap="xs">
                <Text fw={600} size="sm" c="dimmed">
                  {formatDateHeader(key)}
                </Text>
                {txs.map((tx) => (
                  <TransactionCard
                    key={tx.id}
                    tx={tx}
                    accountById={accountById}
                    categoryById={categoryById}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                    deletingId={deleteMutation.variables}
                  />
                ))}
              </Stack>
            ))}
          </Stack>
        )}

        <TransactionFormModal
          opened={modalOpened}
          onClose={handleModalClose}
          transaction={editingTx}
        />
      </Container>
    )
  }

  // ─── Сводка: один элемент (Доход/Расход/Чистый) ─────────────────────────

  interface SummaryItemProps {
    label: string
    value: number
    currency: string
    color: string
    sign: string
  }

  function SummaryItem({ label, value, currency, color, sign }: SummaryItemProps) {
    return (
      <Stack gap={0}>
        <Text size="xs" c="dimmed">
          {label}
        </Text>
        <Text fw={700} c={color}>
          {sign}
          {formatMoney(value, currency)}
        </Text>
      </Stack>
    )
  }

  // ─── Карточка одной операции ────────────────────────────────────────────

  interface CardProps {
    tx: TransactionRead
    accountById: Map<number, AccountRead>
    categoryById: Map<number, CategoryRead>
    onEdit: (tx: TransactionRead) => void
    onDelete: (tx: TransactionRead) => void
    deletingId: number | undefined
  }

  function TransactionCard({
    tx,
    accountById,
    categoryById,
    onEdit,
    onDelete,
    deletingId,
  }: CardProps) {
    const meta = KIND_META[tx.kind]
    const fromAccount = accountById.get(tx.account_id)
    const toAccount = tx.transfer_account_id
      ? accountById.get(tx.transfer_account_id)
      : null
    const category = tx.category_id ? categoryById.get(tx.category_id) : null

    const accountLine =
      tx.kind === 'transfer'
        ? `${fromAccount?.name ?? `#${tx.account_id}`} → ${
            toAccount?.name ?? `#${tx.transfer_account_id}`
          }`
        : `${fromAccount?.name ?? `#${tx.account_id}`}${
            category ? ` · ${category.name}` : ''
          }`

    // Транзакция «не влияет на баланс», если её дата раньше opening_date
    // ХОТЯ БЫ ОДНОГО из затронутых счетов (источник, а для перевода — ещё
    // и получатель). Это объясняет пользователю, почему сумма видна,
    // но balance счёта не сдвинулся. См. vkr/02_design.md.
    const txDate = new Date(tx.occurred_at)
    const beforeSourceOpening =
      fromAccount && txDate < new Date(fromAccount.opening_date)
    const beforeTargetOpening =
      toAccount && txDate < new Date(toAccount.opening_date)
    const notAffectingBalance = beforeSourceOpening || beforeTargetOpening

    return (
      <Card withBorder p="md">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
            <Group gap="xs" wrap="nowrap">
              <Text fw={500} truncate>
                {tx.note || meta.label}
              </Text>
              {notAffectingBalance && (
                <Tooltip
                  label="Дата операции раньше «даты остатка» счёта — её эффект уже учтён в начальном остатке"
                  multiline
                  w={260}
                  withArrow
                >
                  <Badge size="xs" color="gray" variant="light">
                    не в балансе
                  </Badge>
                </Tooltip>
              )}
            </Group>
            <Text size="xs" c="dimmed" truncate>
              {accountLine}
            </Text>
            {/* Только время — дата теперь в заголовке группы. */}
            <Text size="xs" c="dimmed">
              {new Date(tx.occurred_at).toLocaleTimeString('ru-RU', {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </Stack>
          <Group gap="md" wrap="nowrap">
            <Stack gap={0} align="flex-end">
              <Text fw={700} c={meta.color} size="lg">
                {meta.sign}
                {formatMoney(tx.amount, tx.currency_code)}
              </Text>
              <Text size="xs" c="dimmed">
                {meta.label}
              </Text>
            </Stack>
            <ActionIcon
              variant="subtle"
              aria-label="Редактировать операцию"
              onClick={() => onEdit(tx)}
            >
              ✏️
            </ActionIcon>
            <ActionIcon
              variant="subtle"
              color="red"
              aria-label="Удалить операцию"
              onClick={() => onDelete(tx)}
              loading={deletingId === tx.id}
            >
              🗑️
            </ActionIcon>
          </Group>
        </Group>
      </Card>
    )
  }

  // ─── Панель фильтров ────────────────────────────────────────────────────

  interface FilterPanelProps {
    filters: TransactionListFilters
    onChange: (f: TransactionListFilters) => void
    accounts: AccountRead[]
    categories: CategoryRead[]
  }

  // Готовые периоды для shortcut-кнопок. Каждая функция возвращает {from, to}
  // в локальной зоне юзера, чтобы фильтрация совпадала с его календарём.
  const PERIOD_SHORTCUTS: Array<{
    label: string
    compute: () => { from: Date; to: Date }
  }> = [
    {
      label: 'Сегодня',
      compute: () => {
        const now = new Date()
        const from = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        const to = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
          23,
          59,
          59,
        )
        return { from, to }
      },
    },
    {
      label: '7 дней',
      compute: () => {
        const now = new Date()
        const from = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6)
        const to = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
          23,
          59,
          59,
        )
        return { from, to }
      },
    },
    {
      label: 'Этот месяц',
      compute: () => {
        const now = new Date()
        const from = new Date(now.getFullYear(), now.getMonth(), 1)
        // День 0 следующего месяца = последний день текущего.
        const to = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59)
        return { from, to }
      },
    },
    {
      label: 'Прошлый месяц',
      compute: () => {
        const now = new Date()
        const from = new Date(now.getFullYear(), now.getMonth() - 1, 1)
        const to = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59)
        return { from, to }
      },
    },
    {
      label: 'Этот год',
      compute: () => {
        const now = new Date()
        const from = new Date(now.getFullYear(), 0, 1)
        const to = new Date(now.getFullYear(), 11, 31, 23, 59, 59)
        return { from, to }
      },
    },
  ]

  // Локальный день в формате "YYYY-MM-DD" из UTC ISO. Нужен для сравнения
  // активного периода с shortcut-ами и для отображения в DatePickerInput.
  // Реализация в lib/datetime.ts; здесь короткий alias для читаемости.
  const toLocalDay = utcToLocalDay

      // День в формате "1 мая 2026" из ключа "YYYY-MM-DD".
    function formatLocalDay(dayKey: string): string {
      const [y, m, d] = dayKey.split('-').map(Number)
      return new Date(y, m - 1, d).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    }

    // Подпись к плашке сводки: «Этот месяц», «За всё время», или «1 — 7 мая 2026».
    // Если диапазон from/to совпадает с одним из shortcut-периодов, используем его
    // короткое название — так нагляднее, чем дата-дата.
    function formatPeriodLabel(filters: TransactionListFilters): string {
      if (!filters.from_date && !filters.to_date) return 'За всё время'
      if (filters.from_date && filters.to_date) {
        const fromDay = toLocalDay(filters.from_date)
        const toDay = toLocalDay(filters.to_date)
        for (const p of PERIOD_SHORTCUTS) {
          const { from, to } = p.compute()
          if (
            toLocalDay(from.toISOString()) === fromDay &&
            toLocalDay(to.toISOString()) === toDay
          ) {
            return p.label
          }
        }
        return `${formatLocalDay(fromDay)} — ${formatLocalDay(toDay)}`
      }
      if (filters.from_date) return `с ${formatLocalDay(toLocalDay(filters.from_date))}`
      return `по ${formatLocalDay(toLocalDay(filters.to_date!))}`
    }

        // Ключ в sessionStorage для фильтров истории. Префикс fintrack: на случай,
    // если на этом домене когда-нибудь появятся другие приложения.
    const TX_FILTERS_STORAGE_KEY = 'fintrack:tx-filters'

    // Дефолт «Этот месяц» — выносим в отдельную функцию, чтобы переиспользовать
    // в инициализаторе useState (при первом заходе без сохранённых фильтров).
    function getDefaultFilters(): TransactionListFilters {
      const now = new Date()
      const from = new Date(now.getFullYear(), now.getMonth(), 1)
      const to = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59)
      // .toISOString() конвертирует local Date → UTC ISO с Z. Так бэк
      // правильно сравнит с полями transactions.occurred_at (тоже UTC).
      // Раньше тут было «оборачивание в local naive строку» — баг,
      // который сдвигал период на величину таймзоны юзера.
      return {
        from_date: from.toISOString(),
        to_date: to.toISOString(),
      }
    }

  function FilterPanel({
    filters,
    onChange,
    accounts,
    categories,
  }: FilterPanelProps) {
    function update<K extends keyof TransactionListFilters>(
      key: K,
      value: TransactionListFilters[K] | undefined,
    ) {
      const next = { ...filters }
      if (value === undefined) {
        delete next[key]
      } else {
        next[key] = value
      }
      onChange(next)
    }

    // Установить период (from + to) одним вызовом — для shortcut-чипов.
    function applyPeriod(from: Date, to: Date) {
      onChange({
        ...filters,
        from_date: from.toISOString(),
        to_date: to.toISOString(),
      })
    }

    // Какой shortcut сейчас «активен» — для подсветки соответствующего Chip.
    // Сравниваем по локальному дню (YYYY-MM-DD), без секунд и таймзоны.
    function getActiveShortcut(): string | null {
      if (!filters.from_date || !filters.to_date) return null
      const fromDay = toLocalDay(filters.from_date)
      const toDay = toLocalDay(filters.to_date)
      for (const p of PERIOD_SHORTCUTS) {
        const { from, to } = p.compute()
        if (toLocalDay(from.toISOString()) === fromDay && toLocalDay(to.toISOString()) === toDay) {
          return p.label
        }
      }
      return null
    }

    const accountOptions = accounts.map((a) => ({
      value: String(a.id),
      label: a.name,
    }))
    const categoryOptions = categories.map((c) => ({
      value: String(c.id),
      label: c.name,
    }))

    const hasFilters = Object.keys(filters).length > 0
    const activeShortcut = getActiveShortcut()

    return (
      <Card withBorder p="md">
        <Stack gap="sm">
          <Group grow>
            <Select
              label="Счёт"
              placeholder="Все"
              data={accountOptions}
              value={
                filters.account_id !== undefined ? String(filters.account_id) : null
              }
              onChange={(val) =>
                update('account_id', val ? Number(val) : undefined)
              }
              clearable
              searchable
            />
            <Select
              label="Категория"
              placeholder="Все"
              data={categoryOptions}
              value={
                filters.category_id !== undefined
                  ? String(filters.category_id)
                  : null
              }
              onChange={(val) =>
                update('category_id', val ? Number(val) : undefined)
              }
              clearable
              searchable
            />
            <Select
              label="Тип"
              placeholder="Все"
              data={[
                { value: 'income', label: 'Доход' },
                { value: 'expense', label: 'Расход' },
                { value: 'transfer', label: 'Перевод' },
              ]}
              value={filters.kind ?? null}
              onChange={(val) =>
                update('kind', (val as TransactionKind) || undefined)
              }
              clearable
            />
          </Group>

          <Group grow align="flex-end">
            {/* value/onChange проходят через UTC↔local конверсию:
                - filters.* хранится в UTC ISO,
                - DatePickerInput работает с локальным "YYYY-MM-DD".
                Без конверсии юзер в МСК у границы суток видел бы «не тот» день
                (например, 1 мая 00:00 МСК = 30 апр 21:00 UTC → отобразилось бы как 30 апр). */}
            <DatePickerInput
              label="С даты"
              placeholder="Все даты"
              value={filters.from_date ? utcToLocalDay(filters.from_date) : null}
              onChange={(val) =>
                update(
                  'from_date',
                  val ? localToUtcIso(`${val}T00:00:00`) : undefined,
                )
              }
              clearable
            />
            <DatePickerInput
              label="По дату"
              placeholder="Все даты"
              value={filters.to_date ? utcToLocalDay(filters.to_date) : null}
              onChange={(val) =>
                update(
                  'to_date',
                  val ? localToUtcIso(`${val}T23:59:59`) : undefined,
                )
              }
              clearable
            />
            <Select
              label="Период"
              placeholder="Все даты"
              data={PERIOD_SHORTCUTS.map((p) => ({ value: p.label, label: p.label }))}
              value={activeShortcut ?? null}
              onChange={(label) => {
                if (!label) {
                  const next = { ...filters }
                  delete next.from_date
                  delete next.to_date
                  onChange(next)
                  return
                }
                const shortcut = PERIOD_SHORTCUTS.find((p) => p.label === label)
                if (!shortcut) return
                const { from, to } = shortcut.compute()
                applyPeriod(from, to)
              }}
              clearable
            />
            <Button
              variant="subtle"
              onClick={() => onChange({})}
              disabled={!hasFilters}
            >
              Сбросить
            </Button>
          </Group>
        </Stack>
      </Card>
    )
  }