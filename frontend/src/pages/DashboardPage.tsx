import {
  Badge,
  Card,
  Container,
  Group,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { getDashboardSummaryRequest } from '../api/dashboard'
import { listTransactionsRequest } from '../api/transactions'
import { listAccountsRequest } from '../api/accounts'
import { listCategoriesRequest } from '../api/categories'
import { listBudgetsRequest } from '../api/budgets'
import { useDocumentTitle } from '../lib/useDocumentTitle'
import { pluralRu } from '../lib/format'

const RUB = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

const MONTH_NAMES = [
  '', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]

const KIND_LABEL: Record<string, { label: string; color: string }> = {
  income: { label: 'доход', color: 'green' },
  expense: { label: 'расход', color: 'red' },
  transfer: { label: 'перевод', color: 'blue' },
}

const STATUS_COLOR: Record<string, string> = {
  ok: 'green',
  warning: 'yellow',
  exceeded: 'red',
}

export function DashboardPage() {
  useDocumentTitle('Главная')
  const now = new Date()
  const monthLabel = `${MONTH_NAMES[now.getMonth() + 1]} ${now.getFullYear()}`

  const summary = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummaryRequest,
  })

  const recentTx = useQuery({
    queryKey: ['transactions', { limit: 5 }],
    queryFn: () => listTransactionsRequest({ limit: 5 }),
  })

  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: () => listAccountsRequest(),
  })

  const categories = useQuery({
    queryKey: ['categories'],
    queryFn: () => listCategoriesRequest(),
  })

  const budgets = useQuery({
    queryKey: ['budgets', now.getFullYear(), now.getMonth() + 1],
    queryFn: () => listBudgetsRequest(now.getFullYear(), now.getMonth() + 1),
  })

  if (summary.isLoading) {
    return (
      <Container py="xl">
        <Loader />
      </Container>
    )
  }

  if (summary.isError || !summary.data) {
    return (
      <Container py="xl">
        <Text c="red">Не удалось загрузить сводку</Text>
      </Container>
    )
  }

  const accountById = new Map((accounts.data ?? []).map((a) => [a.id, a]))
  const categoryById = new Map((categories.data ?? []).map((c) => [c.id, c]))

  return (
    <Container size="lg" py="xl">
      <Title order={2} mb="lg">
        Главная
      </Title>

      {/* Три верхние карточки — общая сводка */}
      <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} mb="xl">
        <Card withBorder p="lg">
          <Text size="sm" c="dimmed">
            Общий капитал
          </Text>
          <Text size="xl" fw={700} mt="xs">
            {RUB.format(Number(summary.data.total_capital_rub))}
          </Text>
          <Text size="xs" c="dimmed" mt="xs">
            по {summary.data.accounts_count}{' '}
            {pluralRu(summary.data.accounts_count, 'счёту', 'счетам', 'счетам')},
            курс ЦБ РФ
          </Text>
          {summary.data.capital_incomplete && (
            <Text size="xs" c="orange" mt={4}>
              ⚠ Для части валютных счетов нет курса ЦБ — сумма занижена.
              Загляните на страницу «Курсы».
            </Text>
          )}
        </Card>

        <Card withBorder p="lg">
          <Text size="sm" c="dimmed">
            Потрачено за {monthLabel}
          </Text>
          <Text size="xl" fw={700} mt="xs">
            {RUB.format(Number(summary.data.spent_this_month_rub))}
          </Text>
          <Text size="xs" c="dimmed" mt="xs">
            {summary.data.expenses_this_month}{' '}
            {pluralRu(
              summary.data.expenses_this_month,
              'расход',
              'расхода',
              'расходов',
            )}
          </Text>
        </Card>

        <Card withBorder p="lg">
          <Text size="sm" c="dimmed">
            Топ категорий расходов
          </Text>
          {summary.data.top_categories.length === 0 ? (
            <Text size="sm" c="dimmed" mt="xs">
              В этом месяце расходов нет
            </Text>
          ) : (
            <Stack gap="xs" mt="xs">
              {summary.data.top_categories.map((cat, idx) => (
                <Group key={cat.category_id} justify="space-between">
                  <Text size="sm">
                    {idx + 1}. {cat.category_name}
                  </Text>
                  <Text size="sm" fw={600}>
                    {RUB.format(Number(cat.spent_rub))}
                  </Text>
                </Group>
              ))}
            </Stack>
          )}
        </Card>
      </SimpleGrid>

      {/* Две колонки снизу: последние операции и бюджеты */}
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Card withBorder p="lg">
          <Group justify="space-between" mb="md">
            <Title order={4}>Последние операции</Title>
            <Text size="xs" component={Link} to="/transactions" c="blue">
              все →
            </Text>
          </Group>
          {recentTx.isLoading && <Loader size="sm" />}
          {recentTx.data && recentTx.data.length === 0 && (
            <Text size="sm" c="dimmed">
              Операций пока нет.{' '}
              <Text component={Link} to="/transactions" c="blue" inherit>
                Добавить первую
              </Text>
            </Text>
          )}
          {recentTx.data && recentTx.data.length > 0 && (
            <Stack gap="xs">
              {recentTx.data.map((tx) => {
                const kind = KIND_LABEL[tx.kind] ?? { label: tx.kind, color: 'gray' }
                const account = accountById.get(tx.account_id)
                const category = tx.category_id ? categoryById.get(tx.category_id) : null
                // Под названием категории показываем счёт — единообразно для всех,
                // и сразу видно, откуда списано / на что приходило.
                const detail = account?.name || ''
                const dateStr = new Date(tx.occurred_at).toLocaleDateString('ru-RU', {
                  day: 'numeric',
                  month: 'short',
                })
                return (
                  <Group key={tx.id} justify="space-between" wrap="nowrap" align="flex-start">
                    <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }} align="flex-start">
                      <Badge color={kind.color} variant="light" size="sm">
                        {kind.label}
                      </Badge>
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Text size="sm" truncate>
                          {category?.name || account?.name || '—'}
                        </Text>
                        {detail && (
                          <Text size="xs" c="dimmed" truncate>
                            {detail}
                          </Text>
                        )}
                      </Stack>
                    </Group>
                    <Group gap="md" wrap="nowrap">
                      <Text size="xs" c="dimmed">
                        {dateStr}
                      </Text>
                      <Text size="sm" fw={600}>
                        {Number(tx.amount).toLocaleString('ru-RU')} {tx.currency_code}
                      </Text>
                    </Group>
                  </Group>
                )
              })}
            </Stack>
          )}
        </Card>

        <Card withBorder p="lg">
          <Group justify="space-between" mb="md">
            <Title order={4}>Бюджеты на {monthLabel}</Title>
            <Text size="xs" component={Link} to="/budgets" c="blue">
              все →
            </Text>
          </Group>
          {budgets.isLoading && <Loader size="sm" />}
          {budgets.data && budgets.data.length === 0 && (
            <Text size="sm" c="dimmed">
              На этот месяц бюджеты не заданы.{' '}
              <Text component={Link} to="/budgets" c="blue" inherit>
                Создать
              </Text>
            </Text>
          )}
          {budgets.data && budgets.data.length > 0 && (
            <Stack gap="md">
              {budgets.data.slice(0, 5).map((b) => (
                <div key={b.id}>
                  <Group justify="space-between" mb={4}>
                    <Text size="sm">{b.category_name}</Text>
                    <Text size="xs" c="dimmed">
                      {RUB.format(Number(b.spent))} / {RUB.format(Number(b.amount))}
                    </Text>
                  </Group>
                  <Progress
                    value={Math.min(b.percent, 100)}
                    color={STATUS_COLOR[b.status] ?? 'gray'}
                    size="sm"
                  />
                </div>
              ))}
            </Stack>
          )}
        </Card>
      </SimpleGrid>
    </Container>
  )
}
