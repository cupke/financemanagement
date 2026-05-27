import { useState } from 'react'
import {
  ActionIcon,
  Badge,
  Button,
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
import { MonthPickerInput } from '@mantine/dates'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  deleteBudgetRequest,
  listBudgetsRequest,
  type BudgetStatus,
  type BudgetWithProgress,
} from '../api/budgets'
import { BudgetFormModal } from '../components/BudgetFormModal'
import { formatMoney } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'

// Цвета прогресс-бара по статусу. Совпадают с бэк-статусами: ok=green,
// warning=yellow, exceeded=red.
const STATUS_COLOR: Record<BudgetStatus, string> = {
  ok: 'green',
  warning: 'yellow',
  exceeded: 'red',
}

const STATUS_LABEL: Record<BudgetStatus, string> = {
  ok: 'В норме',
  warning: 'Близко к лимиту',
  exceeded: 'Превышен',
}

const MONTH_NAMES = [
  '', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]

interface BudgetCardProps {
  budget: BudgetWithProgress
  onEdit: (b: BudgetWithProgress) => void
  onDelete: (b: BudgetWithProgress) => void
  deletingId: number | undefined
}

function BudgetCard({ budget, onEdit, onDelete, deletingId }: BudgetCardProps) {
  // Progress в Mantine ожидает значение 0-100. Если потратили > лимита,
  // percent может быть >100 — кэппим визуально, чтобы бар не «уезжал».
  const visualPercent = Math.min(budget.percent, 100)

  return (
    <Card withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600} size="lg" truncate style={{ flex: 1 }}>
            {budget.category_name}
          </Text>
          <Badge color={STATUS_COLOR[budget.status]} variant="light">
            {STATUS_LABEL[budget.status]}
          </Badge>
        </Group>

        <Progress
          value={visualPercent}
          color={STATUS_COLOR[budget.status]}
          size="lg"
          radius="md"
        />

        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            {formatMoney(budget.spent, 'RUB')} из {formatMoney(budget.amount, 'RUB')}
          </Text>
          <Text size="sm" fw={500} c={STATUS_COLOR[budget.status]}>
            {budget.percent.toFixed(1)}%
          </Text>
        </Group>

        <Group justify="flex-end" gap="xs">
          <ActionIcon
            variant="subtle"
            aria-label="Изменить бюджет"
            onClick={() => onEdit(budget)}
          >
            ✏️
          </ActionIcon>
          <ActionIcon
            variant="subtle"
            color="red"
            aria-label="Удалить бюджет"
            loading={deletingId === budget.id}
            onClick={() => onDelete(budget)}
          >
            🗑️
          </ActionIcon>
        </Group>
      </Stack>
    </Card>
  )
}

export function BudgetsPage() {
  useDocumentTitle('Бюджеты')
  const queryClient = useQueryClient()
  const [modalOpened, setModalOpened] = useState(false)
  const [editingBudget, setEditingBudget] = useState<BudgetWithProgress | null>(null)

  // По умолчанию показываем текущий месяц по локальному времени браузера.
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1) // JS: 0-11 → бэк: 1-12

  // MonthPickerInput в Mantine 9 работает со строкой 'YYYY-MM-DD', а не Date.
  const pickerValue = `${year}-${String(month).padStart(2, '0')}-01`

  const { data: budgets, isLoading, isError } = useQuery({
    queryKey: ['budgets', year, month],
    queryFn: () => listBudgetsRequest(year, month),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteBudgetRequest(id),
    onSuccess: () => {
      notifications.show({
        title: 'Бюджет удалён',
        message: 'Лимит больше не отслеживается',
        color: 'blue',
      })
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось удалить бюджет',
        color: 'red',
      })
    },
  })

  const handleDelete = (budget: BudgetWithProgress) => {
    modals.openConfirmModal({
      title: 'Удалить бюджет?',
      centered: true,
      children: (
        <Text size="sm">
          Удалить бюджет на «<strong>{budget.category_name}</strong>» в{' '}
          {MONTH_NAMES[budget.period_month]} {budget.period_year}? Сами транзакции
          останутся — удалится только лимит.
        </Text>
      ),
      labels: { confirm: 'Удалить', cancel: 'Отмена' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(budget.id),
    })
  }

  const handleEdit = (budget: BudgetWithProgress) => {
    setEditingBudget(budget)
    setModalOpened(true)
  }

  const handleCreate = () => {
    setEditingBudget(null)
    setModalOpened(true)
  }

  const handleCloseModal = () => {
    setModalOpened(false)
    setEditingBudget(null)
  }

  // Навигация по месяцам. Корректно прокручиваем границу года.
  const goToPrevMonth = () => {
    if (month === 1) {
      setYear(year - 1)
      setMonth(12)
    } else {
      setMonth(month - 1)
    }
  }
  const goToNextMonth = () => {
    if (month === 12) {
      setYear(year + 1)
      setMonth(1)
    } else {
      setMonth(month + 1)
    }
  }
  const goToCurrentMonth = () => {
    const today = new Date()
    setYear(today.getFullYear())
    setMonth(today.getMonth() + 1)
  }
  // Прямой выбор месяца через MonthPickerInput. value — Date локальной зоны,
  // извлекаем year/month. Если пользователь очистил поле — игнорируем
  // (оставляем текущий выбор), чтобы не оставаться в неопределённом состоянии.
  const handlePickMonth = (value: string | null) => {
    if (value === null) return
    // value формата 'YYYY-MM-DD' — парсим вручную, чтобы не зависеть от таймзоны.
    const [y, m] = value.split('-').map(Number)
    setYear(y)
    setMonth(m)
  }

  if (isLoading) {
    return (
      <Container py="xl">
        <Loader />
      </Container>
    )
  }

  if (isError || !budgets) {
    return (
      <Container py="xl">
        <Text c="red">Не удалось загрузить бюджеты.</Text>
      </Container>
    )
  }

  const existingCategoryIds = budgets.map((b) => b.category_id)
  const totalLimit = budgets.reduce((sum, b) => sum + Number(b.amount), 0)
  const totalSpent = budgets.reduce((sum, b) => sum + Number(b.spent), 0)

  return (
    <Container size="lg" py="xl">
      <Group justify="space-between" mb="lg">
        <Title order={2}>Бюджеты</Title>
        <Button onClick={handleCreate}>+ Добавить бюджет</Button>
      </Group>

      {/* Шапка периода: стрелки + month picker + кнопка «Текущий» */}
      <Card withBorder p="md" mb="lg">
        <Group justify="space-between">
          <Group gap="xs">
            <Button variant="subtle" size="sm" onClick={goToPrevMonth}>
              ← Пред.
            </Button>
            {/* MonthPickerInput позволяет прыгнуть на любой месяц одним кликом,
                а не листать стрелками по одному. Заменяет старый text-лейбл. */}
            <MonthPickerInput
              value={pickerValue}
              onChange={handlePickMonth}
              valueFormat="MMMM YYYY"
              size="sm"
              w={180}
              aria-label="Выбрать месяц"
              // popoverProps={{ withinPortal: true }} — на случай, если в
              // будущем добавится модальное окно поверх. Сейчас не нужно.
            />
            <Button variant="subtle" size="sm" onClick={goToNextMonth}>
              След. →
            </Button>
            <Button variant="light" size="xs" onClick={goToCurrentMonth}>
              Текущий
            </Button>
          </Group>
          {budgets.length > 0 && (
            <Text size="sm" c="dimmed">
              Итого: {formatMoney(totalSpent, 'RUB')} из {formatMoney(totalLimit, 'RUB')}
            </Text>
          )}
        </Group>
      </Card>

      {budgets.length === 0 ? (
        <Card withBorder p="xl">
          <Stack align="center" gap="xs">
            <Text c="dimmed" ta="center">
              На {MONTH_NAMES[month]} {year} бюджетов нет. Установите лимит на
              расходную категорию — приложение покажет, насколько вы укладываетесь в него.
            </Text>
            <Button variant="light" onClick={handleCreate}>
              Создать первый бюджет
            </Button>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {budgets.map((budget) => (
            <BudgetCard
              key={budget.id}
              budget={budget}
              onEdit={handleEdit}
              onDelete={handleDelete}
              deletingId={deleteMutation.variables}
            />
          ))}
        </SimpleGrid>
      )}

      <BudgetFormModal
        opened={modalOpened}
        onClose={handleCloseModal}
        periodYear={year}
        periodMonth={month}
        budget={editingBudget}
        existingCategoryIds={existingCategoryIds}
      />
    </Container>
  )
}
