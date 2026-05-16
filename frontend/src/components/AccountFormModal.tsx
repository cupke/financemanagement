    import { useEffect } from 'react'
    import {
      Alert,
      Button,
      Modal,
      NumberInput,
      Select,
      Stack,
      Textarea,
      TextInput,
    } from '@mantine/core'
    import { DateTimePicker } from '@mantine/dates'
    import { useForm } from '@mantine/form'
    import { zodResolver } from 'mantine-form-zod-resolver'
    import { notifications } from '@mantine/notifications'
    import { useMutation, useQueryClient } from '@tanstack/react-query'
    import { z } from 'zod'

    import {
      createAccountRequest,
      updateAccountRequest,
      type AccountRead,
    } from '../api/accounts'
    import { localToUtcIso, utcToLocalIso } from '../lib/datetime'
    import { ACCOUNT_KIND_OPTIONS, COMMON_CURRENCIES } from '../lib/format'

    // Zod-схема. Одна и та же для create и edit — поля идентичны.
    // Поле balance в форме называется opening_balance — оно отправляется
    // на бэк как opening_balance, а current balance вычисляется бэком.
    const accountSchema = z.object({
      name: z.string().min(1, 'Введите название').max(100, 'Максимум 100 символов'),
      kind: z.enum(['card', 'cash', 'savings', 'credit', 'e_wallet', 'other']),
      note: z.string().max(500, 'Максимум 500 символов').nullable(),
      opening_balance: z
        .number()
        .refine((v) => Number.isFinite(v), 'Введите число'),
      opening_date: z.string().min(1, 'Выберите дату'),
      currency_code: z.string().length(3, 'Код валюты — 3 символа'),
    })

    type AccountFormValues = z.infer<typeof accountSchema>

    interface Props {
      opened: boolean
      onClose: () => void
      // Если передан — режим редактирования: форма заполняется текущими
      // значениями, при сабмите вызывается PATCH вместо POST. Если null —
      // режим создания нового счёта.
      account?: AccountRead | null
    }

    // Начальные значения формы. Выносим из компонента, чтобы переиспользовать
    // в useEffect для синхронизации при смене editingAccount.
    function getInitialValues(account: AccountRead | null | undefined): AccountFormValues {
      if (account) {
        // В режиме edit показываем текущее opening_balance (то, что юзер
        // ввёл при создании), НЕ current balance. Иначе пользователь
        // подумал бы, что меняет «то, что сейчас», но фактически менял бы
        // отправную точку — и после пересчёта balance уехал бы.
        return {
          name: account.name,
          kind: account.kind,
          note: account.note ?? '',
          opening_balance: Number(account.opening_balance),
          // Бэк хранит UTC, picker'у нужен local — иначе юзер видел бы
          // сдвинутое на таймзону время «даты остатка».
          opening_date: utcToLocalIso(account.opening_date),
          currency_code: account.currency_code,
        }
      }
      return {
        name: '',
        kind: 'card',
        note: '',
        opening_balance: 0,
        // Текущий момент в local-формате. При сабмите конвертируется
        // в UTC через localToUtcIso.
        opening_date: utcToLocalIso(new Date().toISOString()),
        currency_code: 'RUB',
      }
    }

    export function AccountFormModal({ opened, onClose, account }: Props) {
      const queryClient = useQueryClient()
      const isEditing = !!account

      const form = useForm<AccountFormValues>({
        initialValues: getInitialValues(account),
        validate: zodResolver(accountSchema),
      })

      // При открытии модалки с другим счётом (или переход create → edit)
      // подтягиваем актуальные значения. Зависим только от account?.id и opened,
      // чтобы не перезаписывать форму на каждом ререндере родителя.
      useEffect(() => {
        if (opened) {
          form.setValues(getInitialValues(account))
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [opened, account?.id])

      const saveMutation = useMutation({
        mutationFn: (values: AccountFormValues) => {
          const payload = {
            name: values.name,
            kind: values.kind,
            // Пустая строка → null (не хранить пустые заметки в БД).
            note: values.note?.trim() ? values.note.trim() : null,
            opening_balance: values.opening_balance,
            // Picker отдаёт naive local ISO — конвертируем в UTC ISO с Z,
            // чтобы бэк правильно понял момент времени независимо от таймзоны.
            opening_date: localToUtcIso(values.opening_date),
            currency_code: values.currency_code,
          }
          return account
            ? updateAccountRequest(account.id, payload)
            : createAccountRequest(payload)
        },
        onSuccess: (data) => {
          notifications.show({
            title: isEditing ? 'Счёт обновлён' : 'Счёт создан',
            message: `«${data.name}» ${isEditing ? 'сохранён' : 'добавлен в список'}`,
            color: 'green',
          })
          queryClient.invalidateQueries({ queryKey: ['accounts'] })
          // При создании транзакций список тоже мог измениться (формат отображения
          // валюты, например) — инвалидируем для надёжности.
          queryClient.invalidateQueries({ queryKey: ['transactions'] })
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
                  ? 'Не удалось сохранить счёт'
                  : 'Не удалось создать счёт'
          notifications.show({
            title: 'Ошибка',
            message,
            color: 'red',
          })
        },
      })

      const handleClose = () => {
        form.reset()
        onClose()
      }

      return (
        <Modal
          opened={opened}
          onClose={handleClose}
          title={isEditing ? 'Редактирование счёта' : 'Новый счёт'}
          centered
        >
          <form onSubmit={form.onSubmit((values) => saveMutation.mutate(values))}>
            <Stack>
              {/* Объясняем суть полей «снимок + дата», иначе пользователь
                  не поймёт, почему вводит «сейчас» а не «начальный» и зачем дата.
                  В режиме edit предупреждаем про пересчёт. */}
              {isEditing ? (
                <Alert color="orange" variant="light">
                  Изменение остатка или его даты пересчитает текущий баланс
                  по всем операциям счёта. Это безопасно, но проверь, что
                  значения соответствуют реальности.
                </Alert>
              ) : (
                <Alert color="blue" variant="light">
                  Введи сумму, которая на счету <strong>прямо сейчас</strong>
                  {' '}(посмотри в банк-приложении). Дальше любая операция
                  с датой после &laquo;даты остатка&raquo; будет менять текущий
                  баланс. Операции «задним числом» с датой раньше — останутся
                  в истории, но баланс не тронут (они уже учтены в твоём остатке).
                </Alert>
              )}

              <TextInput
                label="Название"
                placeholder="Например, Сбер карта"
                required
                {...form.getInputProps('name')}
              />
              <Select
                label="Тип счёта"
                description="Влияет на иконку в списке"
                data={ACCOUNT_KIND_OPTIONS}
                searchable
                allowDeselect={false}
                {...form.getInputProps('kind')}
              />
              <Textarea
                label="Заметка"
                description="Необязательно. Например: «зарплатная» или «копилка на отпуск»"
                autosize
                minRows={1}
                maxRows={3}
                maxLength={500}
                {...form.getInputProps('note')}
              />
              <NumberInput
                label={isEditing ? 'Остаток на дату ниже' : 'Сколько на счету сейчас'}
                description={
                  isEditing
                    ? 'Снимок состояния. От него + транзакций считается текущий баланс.'
                    : 'Открой банк-приложение и введи ту сумму'
                }
                decimalScale={2}
                fixedDecimalScale
                allowNegative={false}
                {...form.getInputProps('opening_balance')}
              />
              <DateTimePicker
                label="Дата остатка"
                description={
                  isEditing
                    ? 'Дата, на которую указан остаток выше'
                    : 'Обычно — сегодня. Операции после этой даты будут менять баланс.'
                }
                valueFormat="DD.MM.YYYY HH:mm"
                required
                {...form.getInputProps('opening_date')}
              />
              <Select
                label="Валюта"
                description={
                  isEditing
                    ? 'Смена валюты не пересчитывает уже созданные транзакции'
                    : undefined
                }
                data={COMMON_CURRENCIES}
                searchable
                allowDeselect={false}
                // Запрещаем менять валюту при редактировании — это разрушило бы
                // консистентность с уже привязанными транзакциями (snapshot их
                // currency_code остался бы старым). Хочешь сменить валюту —
                // удали счёт и создай заново.
                disabled={isEditing}
                {...form.getInputProps('currency_code')}
              />
              <Button type="submit" loading={saveMutation.isPending}>
                {isEditing ? 'Сохранить' : 'Создать'}
              </Button>
            </Stack>
          </form>
        </Modal>
      )
    }