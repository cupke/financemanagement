import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Container,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
  useMantineColorScheme,
} from '@mantine/core'
import { DatePickerInput } from '@mantine/dates'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'

import { getReportsOverviewRequest } from '../api/reports'
import { listAccountsRequest } from '../api/accounts'
import { useDocumentTitle } from '../lib/useDocumentTitle'

const GRANULARITY_LABEL: Record<string, string> = {
  day: 'по дням',
  week: 'по неделям',
  month: 'по месяцам',
}

// Подпись для «среднего расхода» — по выбранной гранулярности.
const AVG_LABEL: Record<string, string> = {
  day: 'Средний расход в день',
  week: 'Средний расход в неделю',
  month: 'Средний расход в месяц',
}

// Форматтер денег под валюту отчёта (RUB / USD / …). На неизвестном коде
// откатываемся к простому числу с кодом валюты.
function makeMoneyFormatter(currency: string): (v: number) => string {
  try {
    const nf = new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    })
    return (v) => nf.format(v)
  } catch {
    const nf = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
    return (v) => `${nf.format(v)} ${currency}`
  }
}

// Компактный формат для оси Y: 80000 -> «80к».
function compact(v: number): string {
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)}к`
  return String(v)
}

// Дата -> 'YYYY-MM-DD' по локальному времени (без сдвига на UTC).
function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// Диапазон [начало, сегодня] для кнопок-пресетов.
function rangeBack(unit: 'days' | 'months', amount: number): [string, string] {
  const to = new Date()
  const from = new Date()
  if (unit === 'days') from.setDate(from.getDate() - amount)
  else from.setMonth(from.getMonth() - amount)
  return [isoDate(from), isoDate(to)]
}

const SLICE_COLORS = [
  '#228be6', '#12b886', '#be4bdb', '#fd7e14', '#fa5252',
  '#15aabf', '#82c91e', '#e64980', '#4c6ef5', '#fab005',
]

interface Slice {
  name: string
  value: number
}

function DonutCard({
  title,
  slices,
  emptyText,
  format,
  note,
}: {
  title: string
  slices: Slice[]
  emptyText: string
  format: (v: number) => string
  note?: string
}) {
  const data = slices.map((s, i) => ({ ...s, color: SLICE_COLORS[i % SLICE_COLORS.length] }))
  const total = data.reduce((sum, s) => sum + s.value, 0)

  return (
    <Card withBorder p="lg">
      <Title order={4} mb="md">
        {title}
      </Title>
      {data.length === 0 ? (
        <Text c="dimmed" size="sm">
          {emptyText}
        </Text>
      ) : (
        <>
        <Group align="center" wrap="nowrap" gap="md">
          <PieChart width={180} height={180}>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={80}>
              {data.map((s) => (
                <Cell key={s.name} fill={s.color} />
              ))}
            </Pie>
            <Tooltip formatter={(value: number) => format(value)} />
          </PieChart>
          <Stack gap="xs" style={{ flex: 1, minWidth: 0 }}>
            {data.map((s) => {
              const percent = total ? Math.round((s.value / total) * 100) : 0
              return (
                <Group key={s.name} justify="space-between" wrap="nowrap">
                  <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                    <div
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: s.color,
                        flexShrink: 0,
                      }}
                    />
                    <Text size="sm" truncate>
                      {s.name}
                    </Text>
                  </Group>
                  <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                    {percent}% · {format(s.value)}
                  </Text>
                </Group>
              )
            })}
          </Stack>
        </Group>
        {note && (
          <Text size="xs" c="dimmed" mt="sm">
            {note}
          </Text>
        )}
        </>
      )}
    </Card>
  )
}

function StatCard({
  label,
  value,
  format,
  color,
}: {
  label: string
  value: number
  format: (v: number) => string
  color?: string
}) {
  return (
    <Card withBorder p="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="xl" fw={700} mt={4} c={color}>
        {format(value)}
      </Text>
    </Card>
  )
}

export function ReportsPage() {
  useDocumentTitle('Отчёты')
  const { colorScheme } = useMantineColorScheme()
  const axisColor = colorScheme === 'dark' ? '#909296' : '#495057'
  const gridColor = colorScheme === 'dark' ? '#373a40' : '#dee2e6'

  // Диапазон дат — пара строк 'YYYY-MM-DD'. По умолчанию ~6 месяцев.
  const [range, setRange] = useState<[string | null, string | null]>(() => rangeBack('months', 6))
  const [from, to] = range

  const [accountValue, setAccountValue] = useState('')
  const accountId = accountValue === '' ? null : Number(accountValue)

  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: () => listAccountsRequest(),
  })

  const overview = useQuery({
    queryKey: ['reports-overview', from, to, accountValue],
    queryFn: () => getReportsOverviewRequest(from!, to!, accountId),
    enabled: !!from && !!to,
  })

  const currency = overview.data?.currency ?? 'RUB'
  const money = useMemo(() => makeMoneyFormatter(currency), [currency])

  const accountOptions = [
    { value: '', label: 'Все счета' },
    ...(accounts.data ?? []).map((a) => ({ value: String(a.id), label: a.name })),
  ]

  const header = (
    <Stack gap="sm" mb="lg">
      <Title order={2}>Отчёты</Title>
      <Group gap="sm" wrap="wrap" align="center">
        <Select
          data={accountOptions}
          value={accountValue}
          onChange={(v) => setAccountValue(v ?? '')}
          allowDeselect={false}
          searchable
          nothingFoundMessage="Счёт не найден"
          w={200}
          aria-label="Счёт"
        />
        <Button.Group>
          <Button variant="default" size="xs" onClick={() => setRange(rangeBack('days', 7))}>
            Неделя
          </Button>
          <Button variant="default" size="xs" onClick={() => setRange(rangeBack('months', 1))}>
            Месяц
          </Button>
          <Button variant="default" size="xs" onClick={() => setRange(rangeBack('months', 3))}>
            3 мес
          </Button>
          <Button variant="default" size="xs" onClick={() => setRange(rangeBack('months', 6))}>
            6 мес
          </Button>
          <Button variant="default" size="xs" onClick={() => setRange(rangeBack('months', 12))}>
            Год
          </Button>
        </Button.Group>
        <DatePickerInput
          type="range"
          value={range}
          onChange={setRange}
          valueFormat="DD.MM.YYYY"
          allowSingleDateInRange
          w={260}
          aria-label="Диапазон дат"
        />
      </Group>
    </Stack>
  )

  if (!from || !to) {
    return (
      <Container size="lg" py="xl">
        {header}
        <Card withBorder p="xl">
          <Text c="dimmed" ta="center">
            Выберите период — кнопкой или диапазоном дат.
          </Text>
        </Card>
      </Container>
    )
  }

  if (overview.isLoading) {
    return (
      <Container size="lg" py="xl">
        {header}
        <Loader />
      </Container>
    )
  }

  if (overview.isError || !overview.data) {
    return (
      <Container size="lg" py="xl">
        {header}
        <Text c="red">Не удалось загрузить отчёты</Text>
      </Container>
    )
  }

  const { points, expense_by_category, income_by_category, capital_by_account, summary, granularity } =
    overview.data

  const barData = points.map((p) => ({
    label: p.label,
    Доходы: Number(p.income),
    Расходы: Number(p.expense),
  }))

  const balanceData = points.map((p) => ({
    label: p.label,
    Баланс: Number(p.balance),
  }))

  const expenseSlices: Slice[] = expense_by_category.map((c) => ({
    name: c.category_name,
    value: Number(c.amount),
  }))
  const incomeSlices: Slice[] = income_by_category.map((c) => ({
    name: c.category_name,
    value: Number(c.amount),
  }))
  const capitalSlices: Slice[] = capital_by_account
    .map((a) => ({ name: a.account_name, value: Number(a.balance) }))
    .filter((s) => s.value > 0)

  // Сколько счетов не попало в кольцо капитала (нулевой/отрицательный баланс).
  const hiddenAccounts = capital_by_account.length - capitalSlices.length
  const capitalNote =
    hiddenAccounts > 0
      ? `Не показаны счета с нулевым или отрицательным балансом: ${hiddenAccounts}.`
      : undefined

  // Прореживание подписей оси X: показываем не больше ~12, иначе даты налезают.
  const xInterval = barData.length > 12 ? Math.ceil(barData.length / 12) - 1 : 0

  const hasData = barData.some((d) => d.Доходы > 0 || d.Расходы > 0)
  const isSingleAccount = accountId !== null
  const balanceTitle = isSingleAccount ? 'Баланс счёта' : 'Динамика капитала'

  return (
    <Container size="lg" py="xl">
      {header}

      <SimpleGrid cols={{ base: 2, md: 4 }} mb="xl">
        <StatCard label="Доходы за период" value={Number(summary.total_income)} format={money} color="green" />
        <StatCard label="Расходы за период" value={Number(summary.total_expense)} format={money} color="red" />
        <StatCard
          label="Разница (сбережения)"
          value={Number(summary.net)}
          format={money}
          color={Number(summary.net) < 0 ? 'red' : undefined}
        />
        <StatCard
          label={AVG_LABEL[granularity] ?? 'Средний расход'}
          value={Number(summary.avg_expense_per_bucket)}
          format={money}
        />
      </SimpleGrid>

      {!hasData ? (
        <Card withBorder p="xl">
          <Text c="dimmed" ta="center">
            За выбранный период операций нет. Добавьте доходы и расходы или выберите
            другой период.
          </Text>
        </Card>
      ) : (
        <Stack gap="xl">
          <Card withBorder p="lg">
            <Group justify="space-between" mb="md">
              <Title order={4}>Доходы и расходы</Title>
              <Text size="xs" c="dimmed">
                {GRANULARITY_LABEL[granularity] ?? ''}
              </Text>
            </Group>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="label" stroke={axisColor} fontSize={12} interval={xInterval} minTickGap={16} />
                <YAxis stroke={axisColor} fontSize={12} tickFormatter={compact} />
                <Tooltip formatter={(value: number) => money(value)} contentStyle={{ fontSize: 13 }} />
                <Legend />
                <Bar dataKey="Доходы" fill="#40c057" radius={[3, 3, 0, 0]} />
                <Bar dataKey="Расходы" fill="#fa5252" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <DonutCard
              title="Структура расходов"
              slices={expenseSlices}
              emptyText="Расходов с категориями за период нет."
              format={money}
            />
            <DonutCard
              title="Структура доходов"
              slices={incomeSlices}
              emptyText="Доходов с категориями за период нет."
              format={money}
            />
          </SimpleGrid>

          <SimpleGrid cols={{ base: 1, md: 2 }}>
            {!isSingleAccount && (
              <DonutCard
                title="Капитал по счетам"
                slices={capitalSlices}
                emptyText="Нет счетов с положительным балансом."
                format={money}
                note={capitalNote}
              />
            )}
            <Card withBorder p="lg">
              <Title order={4} mb="md">
                {balanceTitle}
              </Title>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={balanceData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                  <XAxis dataKey="label" stroke={axisColor} fontSize={12} interval={xInterval} minTickGap={16} />
                  <YAxis stroke={axisColor} fontSize={12} tickFormatter={compact} />
                  <Tooltip formatter={(value: number) => money(value)} />
                  <Area type="linear" dataKey="Баланс" stroke="#228be6" fill="#228be6" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
              <Text size="xs" c="dimmed" mt="sm">
                {isSingleAccount
                  ? 'Реальный баланс счёта на конец каждой корзины (с учётом переводов).'
                  : 'Суммарный капитал по всем счетам на конец каждой корзины.'}
              </Text>
            </Card>
          </SimpleGrid>
        </Stack>
      )}
    </Container>
  )
}
