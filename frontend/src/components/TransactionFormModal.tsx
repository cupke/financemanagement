  import { useEffect, useState } from 'react'
  import {
    Alert,
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
  import { listRatesRequest } from '../api/rates'
  import {
    createTransactionRequest,
    updateTransactionRequest,
    type TransactionRead,
  } from '../api/transactions'
  import { buildCategoryOptions } from '../lib/categoryTree'
  import { localToUtcIso, utcToLocalIso } from '../lib/datetime'
  import { formatMoney } from '../lib/format'
  import { CategoryFormModal } from './CategoryFormModal'

  // Zod-схема. Mantine 9 dates возвращают строки ISO 8601, а не Date — поэтому
  // occurred_at это string. Кросс-полевые правила (transfer требует второй счёт,
  // и счета не должны совпадать) — через .refine() в конце.
  // target_amount (сумма зачисления для кросс-валютного перевода) проверяется
  // не здесь, а в компоненте: zod не знает валют выбранных счетов (они приходят
  // из отдельного запроса /accounts, а не из значений формы).
  const transactionSchema = z
    .object({
      kind: z.enum(['income', 'expense', 'transfer']),
      account_id: z.string().min(1, 'Выберите счёт'),
      amount: z.number().gt(0, 'Сумма должна быть больше 0'),
      target_amount: z.number().nullable(),
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
    // Если передан — режим редактирования. Правятся только «безопасные» поля
    // (категория, дата, заметка); сумма/счёт/тип/получатель заблокированы.
    // Чтобы поменять заблокированные поля — удалить операцию и создать новую
    // (см. docstring модуля transactions.py на бэке).
    transaction?: TransactionRead | null
  }

  // Начальные значения формы. Выносим из компонента, чтобы переиспользовать
  // в useEffect для синхронизации при смене editing-транзакции.
  function getInitialValues(
    tx: TransactionRead | null | undefined,
  ): TransactionFormValues {
    if (tx) {
      return {
        kind: tx.kind,
        account_id: String(tx.account_id),
        amount: Number(tx.amount),
        target_amount: tx.target_amount !== null ? Number(tx.target_amount) : null,
        category_id: tx.category_id !== null ? String(tx.category_id) : null,
        transfer_account_id:
          tx.transfer_account_id !== null ? String(tx.transfer_account_id) : null,
        // Бэк хранит в UTC, picker'у даём local — иначе юзер в МСК (+3)
        // увидит время на 3 часа меньше («23:00 → 20:00»).
        occurred_at: utcToLocalIso(tx.occurred_at),
        note: tx.note ?? '',
      }
    }
    return {
      kind: 'expense',
      account_id: '',
      amount: 0,
      target_amount: null,
      category_id: null,
      transfer_account_id: null,
      // Picker'у даём текущий момент в local-формате (без таймзоны).
      // При сабмите конвертируем обратно в UTC через localToUtcIso.
      occurred_at: utcToLocalIso(new Date().toISOString()),
      note: '',
    }
  }

  export function TransactionFormModal({ opened, onClose, transaction }: Props) {
    const queryClient = useQueryClient()
    const isEditing = !!transaction
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
      queryFn: () => listCategoriesRequest(),
    })

    const form = useForm<TransactionFormValues>({
      initialValues: getInitialValues(transaction),
      validate: zodResolver(transactionSchema),
    })

    // При открытии модалки с другой операцией (или переход create → edit)
    // подтягиваем актуальные значения. Зависим только от transaction?.id и opened,
    // чтобы не перезаписывать форму на каждом ререндере родителя.
    useEffect(() => {
      if (opened) {
        form.setValues(getInitialValues(transaction))
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [opened, transaction?.id])

     // При смене kind очищаем «несовместимые» поля. В режиме редактирования
      // kind заблокирован — этот эффект на edit-сценарий не сработает.
      // - category_id всегда — потому что категории разделены по kind
      //   (после deepening category-feature: расходную нельзя для дохода).
      // - transfer_account_id и target_amount только когда не transfer.
      useEffect(() => {
        if (isEditing) return
        form.setFieldValue('category_id', null)
        if (form.values.kind !== 'transfer') {
          form.setFieldValue('transfer_account_id', null)
          form.setFieldValue('target_amount', null)
        }
        // Не добавляем form в deps — это вызовет infinite loop. Реагируем только на kind.
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [form.values.kind])

    const saveMutation = useMutation({
      mutationFn: (values: TransactionFormValues) => {
        // Picker отдаёт naive local ISO ("2026-05-16T17:08:00") —
        // конвертируем в UTC ISO с Z перед отправкой, чтобы бэк
        // правильно понял момент времени независимо от таймзоны юзера.
        const occurredAtUtc = localToUtcIso(values.occurred_at)
        if (transaction) {
          // PATCH: только безопасные поля. Сумма/счёт/тип/получатель не
          // передаём — бэк их и не примет в TransactionUpdate.
          return updateTransactionRequest(transaction.id, {
            category_id:
              values.category_id !== null && values.category_id !== ''
                ? Number(values.category_id)
                : null,
            occurred_at: occurredAtUtc,
            note: values.note || null,
          })
        }
        return createTransactionRequest({
          kind: values.kind,
          account_id: Number(values.account_id),
          amount: values.amount,
          // target_amount шлём только для кросс-валютного перевода. Для
          // одновалютного и income/expense бэк ожидает его отсутствие.
          target_amount: isCrossCurrency ? values.target_amount : null,
          category_id:
            values.category_id !== null && values.category_id !== ''
              ? Number(values.category_id)
              : null,
          transfer_account_id:
            values.transfer_account_id !== null &&
            values.transfer_account_id !== ''
              ? Number(values.transfer_account_id)
              : null,
          occurred_at: occurredAtUtc,
          note: values.note || null,
        })
      },
      onSuccess: () => {
        notifications.show({
          title: isEditing ? 'Операция обновлена' : 'Операция добавлена',
          message: isEditing
            ? 'Изменения сохранены. Балансы не затронуты.'
            : 'Балансы счетов обновлены',
          color: 'green',
        })
        queryClient.invalidateQueries({ queryKey: ['transactions'] })
        // Производные виджеты зависят от операций: дашборд, отчёты, бюджеты,
        // статистика истории. Инвалидируем их и при create, и при edit
        // (правка категории/даты меняет разбивку по категориям и периодам).
        queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
        queryClient.invalidateQueries({ queryKey: ['reports-overview'] })
        queryClient.invalidateQueries({ queryKey: ['budgets'] })
        queryClient.invalidateQueries({ queryKey: ['transactions-stats'] })
        // При CREATE балансы изменились на бэке — нужно перезапросить
        // /accounts, иначе страница счетов покажет старые суммы. При PATCH
        // балансы не трогаются, но invalidate безвреден (просто лишний GET).
        if (!isEditing) {
          queryClient.invalidateQueries({ queryKey: ['accounts'] })
        }
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
              : isEditing
                ? 'Не удалось сохранить операцию'
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
      // Категории фильтруются по типу операции: для расхода — только расходные,
      // для дохода — только доходные. Для перевода Select категории скрыт.
      const categoryOptions = buildCategoryOptions(
        categories,
        form.values.kind === 'transfer' ? undefined : form.values.kind,
      )

    // Live-preview балансов: ищем выбранные счета по id и считаем «было → стало».
    // Если что-то не выбрано — соответствующие переменные останутся null и блок
    // превью просто не отрендерится. В режиме редактирования превью скрыто:
    // PATCH не меняет балансы, поэтому «было → стало» бессмысленно.
    const sourceAccount =
      accounts.find((a) => String(a.id) === form.values.account_id) ?? null
    const targetAccount =
      accounts.find(
        (a) => String(a.id) === (form.values.transfer_account_id ?? ''),
      ) ?? null
    const amount = Number(form.values.amount) || 0
    const isTransfer = form.values.kind === 'transfer'
    // Кросс-валютный перевод: выбраны оба счёта и их валюты различаются.
    // Тогда показываем поле «Сумма зачисления» (в валюте получателя).
    const isCrossCurrency =
      isTransfer &&
      !!sourceAccount &&
      !!targetAccount &&
      sourceAccount.currency_code !== targetAccount.currency_code
    const targetAmount = Number(form.values.target_amount) || 0

    // Курсы ЦБ — нужны только для предзаполнения суммы зачисления. Тянем лениво
    // (enabled), кешируем надолго: курс за день не меняется.
    const { data: ratesData } = useQuery({
      queryKey: ['rates'],
      queryFn: listRatesRequest,
      enabled: isCrossCurrency && !isEditing,
      staleTime: 1000 * 60 * 60,
    })

    // Курс «рублей за 1 единицу валюты» по данным ЦБ. RUB — база (=1), его в
    // фиде ЦБ нет. Для прочих валют берём vunit_rate. null — курса пока нет.
    function vunitOf(code: string): number | null {
      if (code.toUpperCase() === 'RUB') return 1
      const r = ratesData?.items.find(
        (i) => i.char_code === code.toUpperCase(),
      )
      return r ? Number(r.vunit_rate) : null
    }

    // «1 единица валюты получателя = сколько в валюте источника» по курсу ЦБ.
    // Например, для RUB→USD это «90 ₽ за 1 $».
    function oneTargetInSource(): number | null {
      if (!sourceAccount || !targetAccount) return null
      const sv = vunitOf(sourceAccount.currency_code)
      const tv = vunitOf(targetAccount.currency_code)
      if (!sv || !tv) return null
      return tv / sv
    }

    // Предзаполнить сумму зачисления по курсу ЦБ: amount (в валюте источника)
    // → в валюту получателя. Считаем через рубли как общий знаменатель.
    function prefillByCbr() {
      if (!sourceAccount || !targetAccount || amount <= 0) return
      const sv = vunitOf(sourceAccount.currency_code)
      const tv = vunitOf(targetAccount.currency_code)
      if (!sv || !tv) return
      const credited = (amount * sv) / tv
      // Округляем до копеек — столько же знаков, сколько хранит бэк (Numeric(15,2)).
      form.setFieldValue('target_amount', Math.round(credited * 100) / 100)
    }

    // Авто-предзаполнение один раз: как только стал виден кросс-валютный перевод
    // и курсы загрузились, а поле ещё пустое — подставляем расчёт по ЦБ.
    // Дальше пользователь правит вручную (банковский курс отличается от ЦБ).
    useEffect(() => {
      if (
        isCrossCurrency &&
        ratesData &&
        amount > 0 &&
        (form.values.target_amount === null || form.values.target_amount === 0)
      ) {
        prefillByCbr()
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isCrossCurrency, ratesData, amount])

    // Проверка «не повлияет на баланс»: дата операции раньше opening_date
    // хотя бы одного из затронутых счетов. Та же логика, что на бэке
    // (_apply_signed_delta_to_account) и в бейдже на странице истории.
    // Делает превью «было → стало» нерелевантным — заменяем его Alert'ом.
    const txDate = form.values.occurred_at
      ? new Date(form.values.occurred_at)
      : null
    const sourceUnaffected =
      sourceAccount && txDate && txDate < new Date(sourceAccount.opening_date)
    const targetUnaffected =
      targetAccount && txDate && txDate < new Date(targetAccount.opening_date)
    // Для income/expense смотрим только на источник. Для transfer — на оба.
    const willNotAffectBalance = isTransfer
      ? sourceUnaffected || targetUnaffected
      : sourceUnaffected

    function sourceBalanceAfter(): number | null {
      if (!sourceAccount || amount <= 0) return null
      const current = Number(sourceAccount.balance)
      if (form.values.kind === 'income') return current + amount
      // expense и transfer оба списывают со source.
      return current - amount
    }

    function targetBalanceAfter(): number | null {
      if (!targetAccount || form.values.kind !== 'transfer') return null
      // Для кросс-валютного перевода на получателя приходит target_amount
      // (в его валюте), для одновалютного — тот же amount.
      const credited = isCrossCurrency ? targetAmount : amount
      if (credited <= 0) return null
      return Number(targetAccount.balance) + credited
    }

    const handleClose = () => {
      form.reset()
      onClose()
    }

    // Валидация суммы зачисления — в момент сабмита (zod не видит валют счетов).
    const handleSubmit = (values: TransactionFormValues) => {
      if (isCrossCurrency && (!values.target_amount || values.target_amount <= 0)) {
        form.setFieldError('target_amount', 'Укажите сумму зачисления')
        return
      }
      saveMutation.mutate(values)
    }

    const crossRate = oneTargetInSource()

    return (
      <Modal
        opened={opened}
        onClose={handleClose}
        title={isEditing ? 'Редактирование операции' : 'Новая операция'}
        centered
        size="md"
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            {/* В режиме редактирования объясняем, почему часть полей заблокирована.
                Это критично для UX: иначе пользователь будет думать «почему я не
                могу поменять сумму?» и решит, что приложение сломано. */}
            {isEditing && (
              <Alert color="blue" variant="light">
                Здесь можно поправить категорию, дату и заметку. Сумму, счёт
                и тип менять нельзя — для этого удалите операцию и создайте
                новую. Так гарантируется консистентность балансов.
              </Alert>
            )}

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
                disabled={isEditing}
                {...form.getInputProps('transfer_account_id')}
              />
            )}

            <NumberInput
              label={
                isCrossCurrency
                  ? `Сумма списания${sourceAccount ? ` (${sourceAccount.currency_code})` : ''}`
                  : 'Сумма'
              }
              decimalScale={2}
              fixedDecimalScale
              allowNegative={false}
              min={0.01}
              required
              disabled={isEditing}
              {...form.getInputProps('amount')}
            />

            {/* Кросс-валютный перевод: второе поле — сумма зачисления в валюте
                получателя. Авто-предзаполняется по курсу ЦБ, но редактируемо —
                банк/обменник берёт свой курс с комиссией, поэтому реально
                приходит не «по ЦБ». Кнопка «По курсу ЦБ» пересчитывает заново. */}
            {isCrossCurrency && !isEditing && (
              <Stack gap={4}>
                <NumberInput
                  label={`Сумма зачисления (${targetAccount?.currency_code})`}
                  description="Сколько реально пришло на счёт-получатель"
                  decimalScale={2}
                  fixedDecimalScale
                  allowNegative={false}
                  min={0.01}
                  required
                  {...form.getInputProps('target_amount')}
                />
                <Group justify="space-between" gap="xs">
                  {crossRate !== null && targetAccount && sourceAccount ? (
                    <Text size="xs" c="dimmed">
                      Курс ЦБ
                      {ratesData?.rate_date ? ` на ${ratesData.rate_date}` : ''}:
                      {' '}
                      {/* Показываем направление так, чтобы число было ≥ 1
                          (иначе, напр., «1 RUB ≈ 0.01 $» округлится почти до нуля
                          и читается плохо). */}
                      {crossRate >= 1
                        ? `1 ${targetAccount.currency_code} ≈ ${formatMoney(crossRate, sourceAccount.currency_code)}`
                        : `1 ${sourceAccount.currency_code} ≈ ${formatMoney(1 / crossRate, targetAccount.currency_code)}`}
                    </Text>
                  ) : (
                    <span />
                  )}
                  <Button
                    variant="subtle"
                    size="xs"
                    onClick={prefillByCbr}
                    disabled={amount <= 0 || crossRate === null}
                  >
                    ↻ По курсу ЦБ
                  </Button>
                </Group>
              </Stack>
            )}

            {/* Live-preview балансов. Показывается только в режиме создания
                (PATCH не меняет балансы) и когда счёт выбран + amount > 0.
                Если дата операции раньше opening_date счёта — заменяем
                превью «было → стало» на Alert, потому что в эту операцию
                balance не входит (см. модель «opening_balance + движения»). */}
            {!isEditing && sourceAccount && amount > 0 && (
              willNotAffectBalance ? (
                <Alert color="gray" variant="light">
                  Дата операции раньше «даты остатка» счёта&nbsp;—
                  баланс не изменится. Операция сохранится в истории
                  с пометкой «не в балансе».
                </Alert>
              ) : (
                <BalancePreview
                  source={sourceAccount}
                  sourceAfter={sourceBalanceAfter()}
                  target={targetAccount}
                  targetAfter={targetBalanceAfter()}
                  isTransfer={form.values.kind === 'transfer'}
                />
              )
            )}

            {/* Условное поле: категория — для income/expense, не для transfer.
                Под Select — ссылка для создания новой категории не выходя из формы.
                В режиме редактирования категория ПРАВИТСЯ (это «безопасное» поле). */}
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
              description={
                isEditing
                  ? 'Дата правится — это не влияет на балансы счетов'
                  : 'По умолчанию — текущий момент'
              }
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

            <Button type="submit" loading={saveMutation.isPending}>
              {isEditing ? 'Сохранить' : 'Добавить операцию'}
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
            // Тип операции уже выбран в форме транзакции — фиксируем его
            // в модалке категории, чтобы пользователь не мог создать,
            // например, доходную категорию при выбранной операции «расход».
            // Кнопка «Создать новую» вообще скрыта при kind='transfer',
            // поэтому здесь всегда income или expense — приведение безопасное.
            initialKind={form.values.kind as 'income' | 'expense'}
            lockKind
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
