  import { useState } from 'react'
  import {
    ActionIcon,
    Button,
    Card,
    Container,
    Group,
    Loader,
    Select,
    Stack,
    Text,
    Title,
  } from '@mantine/core'
  import { DatePickerInput } from '@mantine/dates'
  import { modals } from '@mantine/modals'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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

  export function TransactionsPage() {
    const [modalOpened, setModalOpened] = useState(false)
    // filters — единый объект с применёнными фильтрами. Каждое изменение
    // меняет queryKey TanStack Query, и список перезапрашивается.
    const [filters, setFilters] = useState<TransactionListFilters>({})
    const queryClient = useQueryClient()

    const { data: transactions, isLoading, isError } = useQuery({
      queryKey: ['transactions', filters],
      queryFn: () => listTransactionsRequest(filters),
    })

    // Загружаем счета и категории, чтобы показывать имена вместо id.
    // Эти запросы кешируются — при переключении страниц данные мгновенные.
    const { data: accounts = [] } = useQuery({
      queryKey: ['accounts'],
      queryFn: listAccountsRequest,
    })
    const { data: categories = [] } = useQuery({
      queryKey: ['categories'],
      queryFn: listCategoriesRequest,
    })

    // Lookup-таблицы для O(1)-доступа по id.
    const accountById = new Map(accounts.map((a) => [a.id, a]))
    const categoryById = new Map(categories.map((c) => [c.id, c]))

    const deleteMutation = useMutation({
      mutationFn: (id: number) => deleteTransactionRequest(id),
      onSuccess: () => {
        notifications.show({
          title: 'Операция удалена',
          message: 'Балансы счетов восстановлены',
          color: 'blue',
        })
        queryClient.invalidateQueries({ queryKey: ['transactions'] })
        // Балансы откатились — обновляем кеш счетов тоже.
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
          <Button onClick={() => setModalOpened(true)}>
            + Добавить операцию
          </Button>
        </Group>

        <FilterPanel
          filters={filters}
          onChange={setFilters}
          accounts={accounts}
          categories={categories}
        />

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

        {transactions && transactions.length === 0 && (
          <Card withBorder p="xl" mt="md">
            <Stack align="center" gap="xs">
              <Text c="dimmed">Пока нет операций по выбранным фильтрам.</Text>
              <Button variant="light" onClick={() => setModalOpened(true)}>
                Добавить первую
              </Button>
            </Stack>
          </Card>
        )}

        {transactions && transactions.length > 0 && (
          <Stack gap="xs" mt="md">
            {transactions.map((tx) => (
              <TransactionCard
                key={tx.id}
                tx={tx}
                accountById={accountById}
                categoryById={categoryById}
                onDelete={handleDelete}
                deletingId={deleteMutation.variables}
              />
            ))}
          </Stack>
        )}

        <TransactionFormModal
          opened={modalOpened}
          onClose={() => setModalOpened(false)}
        />
      </Container>
    )
  }

  // ─── Карточка одной операции ────────────────────────────────────────────

  interface CardProps {
    tx: TransactionRead
    accountById: Map<number, AccountRead>
    categoryById: Map<number, CategoryRead>
    onDelete: (tx: TransactionRead) => void
    deletingId: number | undefined
  }

  function TransactionCard({
    tx,
    accountById,
    categoryById,
    onDelete,
    deletingId,
  }: CardProps) {
    const meta = KIND_META[tx.kind]
    const fromAccount = accountById.get(tx.account_id)
    const toAccount = tx.transfer_account_id
      ? accountById.get(tx.transfer_account_id)
      : null
    const category = tx.category_id ? categoryById.get(tx.category_id) : null

    // Строка под заголовком: для перевода — «Сбер карта → Тинькофф»,
    // для дохода/расхода — «Сбер карта · Бакалея».
    const accountLine =
      tx.kind === 'transfer'
        ? `${fromAccount?.name ?? `#${tx.account_id}`} → ${
            toAccount?.name ?? `#${tx.transfer_account_id}`
          }`
        : `${fromAccount?.name ?? `#${tx.account_id}`}${
            category ? ` · ${category.name}` : ''
          }`

    return (
      <Card withBorder p="md">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
            <Text fw={500} truncate>
              {tx.note || meta.label}
            </Text>
            <Text size="xs" c="dimmed" truncate>
              {accountLine}
            </Text>
            <Text size="xs" c="dimmed">
              {new Date(tx.occurred_at).toLocaleString('ru-RU', {
                dateStyle: 'medium',
                timeStyle: 'short',
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

  function FilterPanel({
    filters,
    onChange,
    accounts,
    categories,
  }: FilterPanelProps) {
    // Хелпер для immutable-обновления одного поля. undefined удаляет фильтр.
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

    const accountOptions = accounts.map((a) => ({
      value: String(a.id),
      label: a.name,
    }))
    const categoryOptions = categories.map((c) => ({
      value: String(c.id),
      label: c.name,
    }))

    const hasFilters = Object.keys(filters).length > 0

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
            <DatePickerInput
              label="С даты"
              placeholder="Все даты"
              value={filters.from_date ? filters.from_date.slice(0, 10) : null}
              onChange={(val) =>
                update('from_date', val ? `${val}T00:00:00` : undefined)
              }
              clearable
            />
            <DatePickerInput
              label="По дату"
              placeholder="Все даты"
              value={filters.to_date ? filters.to_date.slice(0, 10) : null}
              onChange={(val) =>
                update('to_date', val ? `${val}T23:59:59` : undefined)
              }
              clearable
            />
            <Button variant="subtle" onClick={() => onChange({})} disabled={!hasFilters}>
              Сбросить
            </Button>
          </Group>
        </Stack>
      </Card>
    )
  }