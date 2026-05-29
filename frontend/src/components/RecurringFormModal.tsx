import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Textarea,
  TextInput,
} from '@mantine/core'
import { DateTimePicker } from '@mantine/dates'
import { useForm } from '@mantine/form'
import { zodResolver } from 'mantine-form-zod-resolver'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import { listAccountsRequest } from '../api/accounts'
import { listCategoriesRequest } from '../api/categories'
import {
  createRecurringRequest,
  updateRecurringRequest,
  type RecurrenceFrequency,
  type RecurringTransactionRead,
} from '../api/recurring'
import { buildCategoryOptions } from '../lib/categoryTree'
import { localToUtcIso, utcToLocalIso } from '../lib/datetime'
import { pluralRu } from '../lib/format'
import { CategoryFormModal } from './CategoryFormModal'

// Частоты — метки на русском для Select. Значения совпадают с бэком.
const FREQUENCY_OPTIONS = [
  { value: 'daily', label: 'Ежедневно' },
  { value: 'weekly', label: 'Еженедельно' },
  { value: 'monthly', label: 'Ежемесячно' },
  { value: 'yearly', label: 'Ежегодно' },
]

// Формы единицы периода для склонения по числу: [1, 2-4, 5+].
// Используются как суффикс в поле «Повторять каждые» — единица подставляется
// автоматически под выбранную частоту и согласуется с числом (1 неделю /
// 2 недели / 5 недель).
const UNIT_FORMS: Record<RecurrenceFrequency, [string, string, string]> = {
  daily: ['день', 'дня', 'дней'],
  weekly: ['неделю', 'недели', 'недель'],
  monthly: ['месяц', 'месяца', 'месяцев'],
  yearly: ['год', 'года', 'лет'],
}

// Приблизительная длина периода в днях — для прикидки, сколько операций
// создастся при первом запуске, если дата начала в прошлом. Точную дату-
// арифметику делает бэк; здесь нужен лишь порядок величины для предупреждения.
const APPROX_PERIOD_DAYS: Record<RecurrenceFrequency, number> = {
  daily: 1,
  weekly: 7,
  monthly: 30,
  yearly: 365,
}

// Сколько операций примерно создастся за «нагон» от startIso до сейчас.
function estimateBackfill(
  startIso: string,
  frequency: RecurrenceFrequency,
  interval: number,
): number {
  const start = new Date(startIso).getTime()
  const now = Date.now()
  if (!Number.isFinite(start) || start > now) return 0
  const periodMs = APPROX_PERIOD_DAYS[frequency] * Math.max(interval, 1) * 86_400_000
  return Math.floor((now - start) / periodMs) + 1
}

// Zod-схема. Даты — строки (Mantine 9), кросс-полевые правила — через .refine().
const recurringSchema = z
  .object({
    name: z.string().min(1, 'Введите название').max(100),
    kind: z.enum(['income', 'expense', 'transfer']),
    account_id: z.string().min(1, 'Выберите счёт'),
    amount: z.number().gt(0, 'Сумма должна быть больше 0'),
    category_id: z.string().nullable(),
    transfer_account_id: z.string().nullable(),
    note: z.string().max(500).nullable(),
    frequency: z.enum(['daily', 'weekly', 'monthly', 'yearly']),
    interval: z.number().int().gte(1, 'Интервал ≥ 1'),
    start_at: z.string().min(1, 'Выберите дату начала'),
    // Пустая строка = «бессрочно».
    end_at: z.string().nullable(),
  })
  .refine(
    (data) => {
      if (data.kind === 'transfer') {
        if (!data.transfer_account_id) return false
        if (data.transfer_account_id === data.account_id) return false
      }
      return true
    },
    {
      message: 'Для перевода выберите другой счёт-получатель',
      path: ['transfer_account_id'],
    },
  )

type RecurringFormValues = z.infer<typeof recurringSchema>

interface Props {
  opened: boolean
  onClose: () => void
  // Если передан — режим редактирования: тип, счета и категория заблокированы
  // (это «другое правило»); меняются имя, сумма, частота, заметка, окончание,
  // пауза. Уже созданные ранее операции не пересчитываются.
  rule?: RecurringTransactionRead | null
}

function getInitialValues(
  rule: RecurringTransactionRead | null | undefined,
): RecurringFormValues {
  if (rule) {
    return {
      name: rule.name,
      kind: rule.kind,
      account_id: String(rule.account_id),
      amount: Number(rule.amount),
      category_id: rule.category_id !== null ? String(rule.category_id) : null,
      transfer_account_id:
        rule.transfer_account_id !== null
          ? String(rule.transfer_account_id)
          : null,
      note: rule.note ?? '',
      frequency: rule.frequency,
      interval: rule.interval,
      start_at: utcToLocalIso(rule.start_at),
      end_at: rule.end_at ? utcToLocalIso(rule.end_at) : null,
    }
  }
  return {
    name: '',
    kind: 'expense',
    account_id: '',
    amount: 0,
    category_id: null,
    transfer_account_id: null,
    note: '',
    frequency: 'monthly',
    interval: 1,
    start_at: utcToLocalIso(new Date().toISOString()),
    end_at: null,
  }
}

export function RecurringFormModal({ opened, onClose, rule }: Props) {
  const queryClient = useQueryClient()
  const isEditing = !!rule
  // Локальный state для вложенной модалки создания категории (открывается
  // ссылкой под Select-ом категории, как в форме операции).
  const [categoryModalOpened, setCategoryModalOpened] = useState(false)

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: listAccountsRequest,
  })
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => listCategoriesRequest(),
  })

  const form = useForm<RecurringFormValues>({
    initialValues: getInitialValues(rule),
    validate: zodResolver(recurringSchema),
  })

  useEffect(() => {
    if (opened) {
      form.setValues(getInitialValues(rule))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, rule?.id])

  // При смене типа чистим несовместимые поля (в режиме создания).
  useEffect(() => {
    if (isEditing) return
    form.setFieldValue('category_id', null)
    if (form.values.kind !== 'transfer') {
      form.setFieldValue('transfer_account_id', null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.values.kind])

  const saveMutation = useMutation({
    mutationFn: (values: RecurringFormValues) => {
      const startUtc = localToUtcIso(values.start_at)
      const endUtc = values.end_at ? localToUtcIso(values.end_at) : null
      if (rule) {
        // PATCH: только безопасные поля.
        return updateRecurringRequest(rule.id, {
          name: values.name,
          amount: values.amount,
          note: values.note || null,
          frequency: values.frequency,
          interval: values.interval,
          end_at: endUtc,
        })
      }
      return createRecurringRequest({
        name: values.name,
        kind: values.kind,
        account_id: Number(values.account_id),
        amount: values.amount,
        category_id:
          values.category_id !== null && values.category_id !== ''
            ? Number(values.category_id)
            : null,
        transfer_account_id:
          values.transfer_account_id !== null &&
          values.transfer_account_id !== ''
            ? Number(values.transfer_account_id)
            : null,
        note: values.note || null,
        frequency: values.frequency,
        interval: values.interval,
        start_at: startUtc,
        end_at: endUtc,
      })
    },
    onSuccess: () => {
      notifications.show({
        title: isEditing ? 'Правило обновлено' : 'Правило создано',
        message: isEditing
          ? 'Изменения сохранены'
          : 'Операции будут создаваться автоматически по расписанию',
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      form.reset()
      onClose()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const raw = error.response?.data?.detail
      const message =
        typeof raw === 'string'
          ? raw
          : Array.isArray(raw)
            ? raw.map((e) => e.msg).join('; ')
            : 'Не удалось сохранить правило'
      notifications.show({ title: 'Ошибка', message, color: 'red' })
    },
  })

  const accountOptions = accounts.map((a) => ({
    value: String(a.id),
    label: `${a.name} (${a.currency_code})`,
  }))
  const categoryOptions = buildCategoryOptions(
    categories,
    form.values.kind === 'transfer' ? undefined : form.values.kind,
  )

  // Единица периода для суффикса поля «Повторять каждые», согласованная с
  // текущими частотой и числом: «каждые 2 недели», «каждые 5 недель» и т.д.
  const intervalForms = UNIT_FORMS[form.values.frequency]
  const intervalUnit = pluralRu(
    Number(form.values.interval) || 1,
    intervalForms[0],
    intervalForms[1],
    intervalForms[2],
  )

  // ── Предупреждения для режима создания (в edit-режиме старт заблокирован) ──
  const sourceAccount =
    accounts.find((a) => String(a.id) === form.values.account_id) ?? null
  const targetAccount =
    accounts.find(
      (a) => String(a.id) === (form.values.transfer_account_id ?? ''),
    ) ?? null
  const startDate = form.values.start_at ? new Date(form.values.start_at) : null

  // 1) Дата начала раньше «даты остатка» счёта → ранние операции не повлияют
  //    на баланс (модель «opening_balance + движения»). Для перевода смотрим
  //    оба счёта.
  const startsBeforeOpening =
    !isEditing &&
    startDate !== null &&
    ((sourceAccount && startDate < new Date(sourceAccount.opening_date)) ||
      (form.values.kind === 'transfer' &&
        targetAccount &&
        startDate < new Date(targetAccount.opening_date)))

  // 2) Старт далеко в прошлом → при первом запуске создастся сразу много
  //    операций задним числом. Предупреждаем, если их больше нескольких.
  const backfillCount = !isEditing
    ? estimateBackfill(
        form.values.start_at,
        form.values.frequency,
        Number(form.values.interval) || 1,
      )
    : 0
  const manyBackfill = backfillCount > 6

  const handleClose = () => {
    form.reset()
    onClose()
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={isEditing ? 'Редактирование правила' : 'Новое правило'}
      centered
      size="md"
    >
      <form onSubmit={form.onSubmit((values) => saveMutation.mutate(values))}>
        <Stack>
          {isEditing && (
            <Alert color="blue" variant="light">
              Тип, счёт и категорию у существующего правила менять нельзя — для
              этого создайте новое правило. Уже созданные операции останутся
              в истории.
            </Alert>
          )}

          <TextInput
            label="Название"
            placeholder="Например, «Зарплата» или «Аренда»"
            required
            {...form.getInputProps('name')}
          />

          <SegmentedControl
            fullWidth
            data={[
              { label: '💰 Доход', value: 'income' },
              { label: '💸 Расход', value: 'expense' },
              { label: '🔁 Между счетами', value: 'transfer' },
            ]}
            disabled={isEditing}
            {...form.getInputProps('kind')}
          />

          <Select
            label={form.values.kind === 'transfer' ? 'Со счёта' : 'Счёт'}
            placeholder="Выберите счёт"
            data={accountOptions}
            required
            searchable
            allowDeselect={false}
            disabled={isEditing}
            {...form.getInputProps('account_id')}
          />

          {form.values.kind === 'transfer' && (
            <Select
              label="На счёт"
              placeholder="Выберите счёт-получатель"
              data={accountOptions.filter(
                (o) => o.value !== form.values.account_id,
              )}
              required
              searchable
              allowDeselect={false}
              disabled={isEditing}
              {...form.getInputProps('transfer_account_id')}
            />
          )}

          <NumberInput
            label="Сумма"
            decimalScale={2}
            fixedDecimalScale
            allowNegative={false}
            min={0.01}
            required
            {...form.getInputProps('amount')}
          />

          {form.values.kind !== 'transfer' && (
            <Stack gap={4}>
              <Select
                label="Категория"
                placeholder="Без категории"
                data={categoryOptions}
                clearable
                searchable
                disabled={isEditing}
                {...form.getInputProps('category_id')}
              />
              {/* В режиме редактирования категория заблокирована, поэтому
                  ссылку создания категории показываем только при создании. */}
              {!isEditing && (
                <Button
                  variant="subtle"
                  size="xs"
                  onClick={() => setCategoryModalOpened(true)}
                  style={{ alignSelf: 'flex-start' }}
                >
                  ➕ Создать новую категорию
                </Button>
              )}
            </Stack>
          )}

          <Group grow align="flex-start">
            <Select
              label="Частота"
              data={FREQUENCY_OPTIONS}
              allowDeselect={false}
              {...form.getInputProps('frequency')}
            />
            <NumberInput
              label="Повторять каждые"
              min={1}
              allowDecimal={false}
              // Суффикс автоподставляет единицу под выбранную частоту и
              // согласует её с числом: «1 неделю», «2 недели», «5 недель».
              suffix={` ${intervalUnit}`}
              {...form.getInputProps('interval')}
            />
          </Group>

          <DateTimePicker
            label="Начало"
            description="С какого момента отсчитывать повторы. Может быть в прошлом — тогда пропущенные операции догенерируются."
            valueFormat="DD.MM.YYYY HH:mm"
            required
            disabled={isEditing}
            {...form.getInputProps('start_at')}
          />

          {manyBackfill && (
            <Alert color="yellow" variant="light">
              Дата начала далеко в прошлом — при первом запуске создастся сразу
              много операций задним числом (примерно {backfillCount}). Если это
              не нужно, выберите дату поближе.
            </Alert>
          )}

          {startsBeforeOpening && (
            <Alert color="gray" variant="light">
              Дата начала раньше «даты остатка» счёта — операции до неё
              сохранятся в истории, но баланс не изменят (он уже учтён в
              начальном остатке счёта).
            </Alert>
          )}

          <DateTimePicker
            label="Окончание (необязательно)"
            description="После этой даты правило завершится. Пусто — бессрочно."
            valueFormat="DD.MM.YYYY HH:mm"
            clearable
            {...form.getInputProps('end_at')}
          />

          <Textarea
            label="Заметка"
            placeholder="Подставится в каждую созданную операцию"
            maxLength={500}
            autosize
            minRows={1}
            maxRows={3}
            {...form.getInputProps('note')}
          />

          <Button type="submit" loading={saveMutation.isPending}>
            {isEditing ? 'Сохранить' : 'Создать правило'}
          </Button>
        </Stack>
      </form>

      {/* Вложенная модалка создания категории — открывается ссылкой под Select-ом.
          Тип фиксируем под выбранный в правиле (доход/расход), чтобы нельзя было
          создать расходную категорию для доходного правила. После создания
          onCreated сразу подставляет новую категорию в Select. */}
      <CategoryFormModal
        opened={categoryModalOpened}
        onClose={() => setCategoryModalOpened(false)}
        initialKind={form.values.kind as 'income' | 'expense'}
        lockKind
        onCreated={(category) => {
          form.setFieldValue('category_id', String(category.id))
        }}
      />
    </Modal>
  )
}
