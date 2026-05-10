  import { useEffect, useState } from 'react'
  import {
    Button,
    Card,
    Group,
    Modal,
    NumberInput,
    SegmentedControl,
    Select,
    Stack,
    Text,
    Textarea,
  } from '@mantine/core'
  import { DateTimePicker } from '@mantine/dates'
  import { useForm } from '@mantine/form'
  import { zodResolver } from 'mantine-form-zod-resolver'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
  import { z } from 'zod'

  import { listAccountsRequest, type AccountRead } from '../api/accounts'
  import { listCategoriesRequest } from '../api/categories'
  import { createTransactionRequest } from '../api/transactions'
  import { buildCategoryOptions } from '../lib/categoryTree'
  import { formatMoney } from '../lib/format'
  import { CategoryFormModal } from './CategoryFormModal'

  // Zod-схема. Mantine 9 dates возвращают строки ISO 8601, а не Date — поэтому
  // occurred_at это string. Кросс-полевые правила (transfer требует второй счёт,
  // и счета не должны совпадать) — через .refine() в конце.
  const transactionSchema = z
    .object({
      kind: z.enum(['income', 'expense', 'transfer']),
      account_id: z.string().min(1, 'Выберите счёт'),
      amount: z.number().gt(0, 'Сумма должна быть больше 0'),
      category_id: z.string().nullable(),
      transfer_account_id: z.string().nullable(),
      occurred_at: z.string().min(1, 'Выберите дату'),
      note: z.string().max(500).nullable(),
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

  type TransactionFormValues = z.infer<typeof transactionSchema>

  interface Props {
    opened: boolean
    onClose: () => void
  }

  export function TransactionFormModal({ opened, onClose }: Props) {
    const queryClient = useQueryClient()
    // Локальный state для вложенной модалки создания категории. Открывается
    // из ссылки под Select-ом категории. Не путать с opened-prop'ом самой
    // транзакционной модалки — это два независимых уровня.
    const [categoryModalOpened, setCategoryModalOpened] = useState(false)

    const { data: accounts = [] } = useQuery({
      queryKey: ['accounts'],
      queryFn: listAccountsRequest,
    })
    const { data: categories = [] } = useQuery({
      queryKey: ['categories'],
      queryFn: listCategoriesRequest,
    })

    const form = useForm<TransactionFormValues>({
      initialValues: {
        kind: 'expense',
        account_id: '',
        amount: 0,
        category_id: null,
        transfer_account_id: null,
        // ISO 8601 — Mantine 9 DateTimePicker работает со строками этого формата.
        occurred_at: new Date().toISOString(),
        note: '',
      },
      validate: zodResolver(transactionSchema),
    })

    // При смене kind очищаем «несовместимые» поля. Например, переход с income
    // на transfer обнуляет category_id (для перевода категории нет — иначе бэк
    // вернёт 422 от model_validator схемы).
    useEffect(() => {
      if (form.values.kind === 'transfer') {
        form.setFieldValue('category_id', null)
      } else {
        form.setFieldValue('transfer_account_id', null)
      }
      // Не добавляем form в deps — это вызовет infinite loop. Реагируем только на kind.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [form.values.kind])

    const createMutation = useMutation({
      mutationFn: (values: TransactionFormValues) =>
        createTransactionRequest({
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
          occurred_at: values.occurred_at,
          note: values.note || null,
        }),
      onSuccess: () => {
        notifications.show({
          title: 'Операция добавлена',
          message: 'Балансы счетов обновлены',
          color: 'green',
        })
        queryClient.invalidateQueries({ queryKey: ['transactions'] })
        // КРИТИЧЕСКАЯ строка: балансы счетов изменились на бэке — нужно
        // перезапросить /accounts, иначе страница счетов покажет старые суммы.
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
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
              : 'Не удалось создать операцию'
        notifications.show({
          title: 'Ошибка',
          message,
          color: 'red',
        })
      },
    })

    const accountOptions = accounts.map((a) => ({
      value: String(a.id),
      label: `${a.name} (${a.currency_code})`,
    }))
    const categoryOptions = buildCategoryOptions(categories)

    // Live-preview балансов: ищем выбранные счета по id и считаем «было → стало».
    // Если что-то не выбрано — соответствующие переменные останутся null и блок
    // превью просто не отрендерится.
    const sourceAccount =
      accounts.find((a) => String(a.id) === form.values.account_id) ?? null
    const targetAccount =
      accounts.find(
        (a) => String(a.id) === (form.values.transfer_account_id ?? ''),
      ) ?? null
    const amount = Number(form.values.amount) || 0

    function sourceBalanceAfter(): number | null {
      if (!sourceAccount || amount <= 0) return null
      const current = Number(sourceAccount.balance)
      if (form.values.kind === 'income') return current + amount
      // expense и transfer оба списывают со source.
      return current - amount
    }

    function targetBalanceAfter(): number | null {
      if (!targetAccount || amount <= 0) return null
      if (form.values.kind !== 'transfer') return null
      return Number(targetAccount.balance) + amount
    }

    const handleClose = () => {
      form.reset()
      onClose()
    }

    return (
      <Modal
        opened={opened}
        onClose={handleClose}
        title="Новая операция"
        centered
        size="md"
      >
        <form onSubmit={form.onSubmit((values) => createMutation.mutate(values))}>
          <Stack>
            <SegmentedControl
              fullWidth
              data={[
                { label: '💰 Доход', value: 'income' },
                { label: '💸 Расход', value: 'expense' },
                { label: '🔁 Между счетами', value: 'transfer' },
              ]}
              {...form.getInputProps('kind')}
            />

            <Select
              label={form.values.kind === 'transfer' ? 'Со счёта' : 'Счёт'}
              placeholder="Выберите счёт"
              data={accountOptions}
              required
              searchable
              allowDeselect={false}
              {...form.getInputProps('account_id')}
            />

            {/* Условное поле: получатель — только для перевода. И исключаем
                из опций счёт-источник, чтобы юзер не мог выбрать тот же. */}
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

            {/* Live-preview балансов. Показывается только когда счёт выбран
                и amount > 0 — иначе превью бессмысленно. Подсказывает
                пользователю результат до подтверждения операции. */}
            {sourceAccount && amount > 0 && (
              <BalancePreview
                source={sourceAccount}
                sourceAfter={sourceBalanceAfter()}
                target={targetAccount}
                targetAfter={targetBalanceAfter()}
                isTransfer={form.values.kind === 'transfer'}
              />
            )}

            {/* Условное поле: категория — для income/expense, не для transfer.
                Под Select — ссылка для создания новой категории не выходя из формы. */}
            {form.values.kind !== 'transfer' && (
              <Stack gap={4}>
                <Select
                  label="Категория"
                  placeholder="Без категории"
                  data={categoryOptions}
                  clearable
                  searchable
                  {...form.getInputProps('category_id')}
                />
                <Button
                  variant="subtle"
                  size="xs"
                  onClick={() => setCategoryModalOpened(true)}
                  style={{ alignSelf: 'flex-start' }}
                >
                  ➕ Создать новую категорию
                </Button>
              </Stack>
            )}

            <DateTimePicker
              label="Когда"
              description="По умолчанию — текущий момент"
              valueFormat="DD.MM.YYYY HH:mm"
              required
              {...form.getInputProps('occurred_at')}
            />

            <Textarea
              label="Заметка"
              placeholder="Например, «Зарплата за май»"
              maxLength={500}
              autosize
              minRows={1}
              maxRows={3}
              {...form.getInputProps('note')}
            />

            <Button type="submit" loading={createMutation.isPending}>
              Добавить операцию
            </Button>
          </Stack>
        </form>

        {/* Вложенная модалка создания категории. Mantine рендерит её через
            Portal с собственным z-index — корректно поверх родительской.
            После создания onCreated автоматически подставляет новую категорию
            в Select, экономя клик пользователю. */}
        <CategoryFormModal
          opened={categoryModalOpened}
          onClose={() => setCategoryModalOpened(false)}
          onCreated={(category) => {
            form.setFieldValue('category_id', String(category.id))
          }}
        />
      </Modal>
    )
  }

  // ─── Live-preview балансов ──────────────────────────────────────────────

  interface BalancePreviewProps {
    source: AccountRead
    sourceAfter: number | null
    target: AccountRead | null
    targetAfter: number | null
    isTransfer: boolean
  }

  function BalancePreview({
    source,
    sourceAfter,
    target,
    targetAfter,
    isTransfer,
  }: BalancePreviewProps) {
    return (
      <Card withBorder p="sm" bg="gray.0">
        <Stack gap={6}>
          <PreviewRow
            label={isTransfer ? 'Со счёта' : 'Счёт'}
            accountName={source.name}
            currentBalance={Number(source.balance)}
            newBalance={sourceAfter}
            currencyCode={source.currency_code}
          />
          {isTransfer && target && (
            <PreviewRow
              label="На счёт"
              accountName={target.name}
              currentBalance={Number(target.balance)}
              newBalance={targetAfter}
              currencyCode={target.currency_code}
            />
          )}
        </Stack>
      </Card>
    )
  }

  interface PreviewRowProps {
    label: string
    accountName: string
    currentBalance: number
    newBalance: number | null
    currencyCode: string
  }

  function PreviewRow({
    label,
    accountName,
    currentBalance,
    newBalance,
    currencyCode,
  }: PreviewRowProps) {
    // Если будущий баланс отрицательный — подсвечиваем красным как warning.
    // Не запрещаем (бывают кредитные карты, овердрафты), но обращаем внимание.
    const willBeNegative = newBalance !== null && newBalance < 0
    return (
      <Group justify="space-between" wrap="nowrap" gap="xs">
        <Stack gap={0} style={{ minWidth: 0, flex: 1 }}>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
          <Text size="sm" fw={500} truncate>
            {accountName}
          </Text>
        </Stack>
        <Group gap={4} wrap="nowrap">
          <Text size="sm" c="dimmed">
            {formatMoney(currentBalance, currencyCode)}
          </Text>
          <Text size="sm" c="dimmed">
            →
          </Text>
          <Text size="sm" fw={600} c={willBeNegative ? 'red' : undefined}>
            {newBalance !== null ? formatMoney(newBalance, currencyCode) : '—'}
          </Text>
        </Group>
      </Group>
    )
  }