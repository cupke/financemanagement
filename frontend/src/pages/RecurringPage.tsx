import { useState } from 'react'
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Container,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { listAccountsRequest } from '../api/accounts'
import { listCategoriesRequest } from '../api/categories'
import {
  deleteRecurringRequest,
  listRecurringRequest,
  runRecurringRequest,
  updateRecurringRequest,
  type RecurrenceFrequency,
  type RecurringKind,
  type RecurringTransactionRead,
} from '../api/recurring'
import { RecurringFormModal } from '../components/RecurringFormModal'
import { formatMoney, pluralRu } from '../lib/format'
import { useDocumentTitle } from '../lib/useDocumentTitle'

// «каждый день / каждую неделю / каждый месяц / каждый год» — для интервала 1.
const EVERY_SINGULAR: Record<RecurrenceFrequency, string> = {
  daily: 'каждый день',
  weekly: 'каждую неделю',
  monthly: 'каждый месяц',
  yearly: 'каждый год',
}

// Формы единицы для склонения с числом (1 / 2-4 / 5+): «2 недели», «5 недель».
const UNIT_FORMS: Record<RecurrenceFrequency, [string, string, string]> = {
  daily: ['день', 'дня', 'дней'],
  weekly: ['неделю', 'недели', 'недель'],
  monthly: ['месяц', 'месяца', 'месяцев'],
  yearly: ['год', 'года', 'лет'],
}

const KIND_META: Record<RecurringKind, { label: string; emoji: string; color: string }> = {
  income: { label: 'Доход', emoji: '💰', color: 'green' },
  expense: { label: 'Расход', emoji: '💸', color: 'red' },
  transfer: { label: 'Перевод', emoji: '🔁', color: 'blue' },
}

// «каждый месяц» / «каждые 2 недели» / «каждые 5 недель» — человекочитаемая
// частота со склонением единицы под число.
function frequencyText(freq: RecurrenceFrequency, interval: number): string {
  if (interval === 1) return EVERY_SINGULAR[freq]
  const [one, few, many] = UNIT_FORMS[freq]
  return `каждые ${interval} ${pluralRu(interval, one, few, many)}`
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function RecurringPage() {
  useDocumentTitle('Регулярные операции')
  const queryClient = useQueryClient()
  const [modalOpened, setModalOpened] = useState(false)
  const [editingRule, setEditingRule] = useState<RecurringTransactionRead | null>(null)

  const {
    data: rules,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['recurring'],
    queryFn: listRecurringRequest,
  })
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: listAccountsRequest,
  })
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => listCategoriesRequest(),
  })

  const accountName = (id: number) =>
    accounts.find((a) => a.id === id)?.name ?? `Счёт #${id}`
  const categoryName = (id: number | null) =>
    id === null ? null : (categories.find((c) => c.id === id)?.name ?? null)

  // Ручной прогон до-генерации. Тот же эндпоинт, что вызывается автоматически
  // при заходе в приложение, но здесь — по кнопке, с явным итогом.
  const runMutation = useMutation({
    mutationFn: runRecurringRequest,
    onSuccess: (result) => {
      notifications.show({
        title: 'Готово',
        message:
          result.created > 0
            ? `Создано операций: ${result.created}`
            : 'Новых операций по расписанию пока нет',
        color: result.created > 0 ? 'green' : 'blue',
      })
      // Создались операции → балансы, история, дашборд, отчёты и бюджеты
      // поменялись. Ключ дашборда — 'dashboard-summary' (а не 'dashboard',
      // под которым ничего не кэшируется).
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['transactions-stats'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
      queryClient.invalidateQueries({ queryKey: ['reports-overview'] })
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось выполнить',
        color: 'red',
      })
    },
  })

  // Пауза / возобновление через PATCH is_active.
  const toggleMutation = useMutation({
    mutationFn: (rule: RecurringTransactionRead) =>
      updateRecurringRequest(rule.id, { is_active: !rule.is_active }),
    onSuccess: (updated) => {
      notifications.show({
        title: updated.is_active ? 'Правило возобновлено' : 'Правило на паузе',
        message: updated.is_active
          ? 'Операции снова будут создаваться по расписанию'
          : 'Автосоздание операций приостановлено',
        color: 'blue',
      })
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message:
          error.response?.data?.detail || 'Не удалось изменить правило',
        color: 'red',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteRecurringRequest(id),
    onSuccess: () => {
      notifications.show({
        title: 'Правило удалено',
        message: 'Ранее созданные операции остались в истории',
        color: 'blue',
      })
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось удалить правило',
        color: 'red',
      })
    },
  })

  const handleDelete = (rule: RecurringTransactionRead) => {
    modals.openConfirmModal({
      title: 'Удалить правило?',
      centered: true,
      children: (
        <Text size="sm">
          Удалить правило «<strong>{rule.name}</strong>»? Новые операции по нему
          создаваться перестанут. Уже созданные операции останутся в истории.
        </Text>
      ),
      labels: { confirm: 'Удалить', cancel: 'Отмена' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(rule.id),
    })
  }

  const handleEdit = (rule: RecurringTransactionRead) => {
    setEditingRule(rule)
    setModalOpened(true)
  }
  const handleCreate = () => {
    setEditingRule(null)
    setModalOpened(true)
  }
  const handleCloseModal = () => {
    setModalOpened(false)
    setEditingRule(null)
  }

  if (isLoading) {
    return (
      <Container py="xl">
        <Loader />
      </Container>
    )
  }
  if (isError || !rules) {
    return (
      <Container py="xl">
        <Text c="red">Не удалось загрузить правила.</Text>
      </Container>
    )
  }

  return (
    <Container size="lg" py="xl">
      <Group justify="space-between" mb="xs">
        <Title order={2}>Регулярные операции</Title>
        <Group gap="xs">
          <Button
            variant="light"
            loading={runMutation.isPending}
            onClick={() => runMutation.mutate()}
          >
            ⚡ Выполнить запланированные
          </Button>
          <Button onClick={handleCreate}>+ Добавить правило</Button>
        </Group>
      </Group>

      <Text c="dimmed" size="sm" mb="lg">
        Правила автоматически создают операции по расписанию (зарплата,
        подписки, аренда). Пропущенные операции догенерируются при заходе
        в приложение.
      </Text>

      {rules.length === 0 ? (
        <Card withBorder p="xl">
          <Stack align="center" gap="xs">
            <Text c="dimmed" ta="center">
              Правил пока нет. Создайте первое — например, ежемесячную зарплату
              или подписку, — и приложение будет добавлять операции за вас.
            </Text>
            <Button variant="light" onClick={handleCreate}>
              Создать первое правило
            </Button>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {rules.map((rule) => {
            const meta = KIND_META[rule.kind]
            const catName = categoryName(rule.category_id)
            return (
              <Card key={rule.id} withBorder p="md" opacity={rule.is_active ? 1 : 0.65}>
                <Stack gap="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <Text fw={600} size="lg" truncate style={{ flex: 1 }}>
                      {meta.emoji} {rule.name}
                    </Text>
                    {rule.is_active ? (
                      <Badge color={meta.color} variant="light">
                        {meta.label}
                      </Badge>
                    ) : (
                      <Badge color="gray" variant="light">
                        На паузе
                      </Badge>
                    )}
                  </Group>

                  <Text size="xl" fw={700}>
                    {formatMoney(rule.amount, rule.currency_code)}
                  </Text>

                  <Stack gap={2}>
                    <Text size="sm" c="dimmed">
                      📅 {frequencyText(rule.frequency, rule.interval)}
                    </Text>
                    <Text size="sm" c="dimmed" truncate>
                      🏦 {accountName(rule.account_id)}
                      {rule.kind === 'transfer' && rule.transfer_account_id !== null
                        ? ` → ${accountName(rule.transfer_account_id)}`
                        : ''}
                    </Text>
                    {catName && (
                      <Text size="sm" c="dimmed" truncate>
                        📂 {catName}
                      </Text>
                    )}
                    {/* «Следующую» показываем только у активных правил. У
                        правила на паузе курсор next_run_at не двигается и
                        обычно «застрял» в прошлом — показывать его как
                        «следующую дату» вводит в заблуждение. */}
                    {rule.is_active ? (
                      <Text size="sm" c="dimmed">
                        ⏭ Следующая: {formatDateTime(rule.next_run_at)}
                      </Text>
                    ) : (
                      <Text size="sm" c="gray">
                        ⏸ На паузе
                      </Text>
                    )}
                    {rule.last_run_at && (
                      <Text size="sm" c="dimmed">
                        ✅ Последний запуск: {formatDateTime(rule.last_run_at)}
                      </Text>
                    )}
                    {rule.end_at && (
                      <Text size="sm" c="dimmed">
                        🏁 До: {formatDateTime(rule.end_at)}
                      </Text>
                    )}
                  </Stack>

                  <Group justify="flex-end" gap="xs">
                    <Tooltip label={rule.is_active ? 'Поставить на паузу' : 'Возобновить'}>
                      <ActionIcon
                        variant="subtle"
                        aria-label="Пауза/возобновление"
                        loading={toggleMutation.isPending && toggleMutation.variables?.id === rule.id}
                        onClick={() => toggleMutation.mutate(rule)}
                      >
                        {rule.is_active ? '⏸️' : '▶️'}
                      </ActionIcon>
                    </Tooltip>
                    <ActionIcon
                      variant="subtle"
                      aria-label="Изменить правило"
                      onClick={() => handleEdit(rule)}
                    >
                      ✏️
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label="Удалить правило"
                      loading={deleteMutation.variables === rule.id}
                      onClick={() => handleDelete(rule)}
                    >
                      🗑️
                    </ActionIcon>
                  </Group>
                </Stack>
              </Card>
            )
          })}
        </SimpleGrid>
      )}

      <RecurringFormModal
        opened={modalOpened}
        onClose={handleCloseModal}
        rule={editingRule}
      />
    </Container>
  )
}
