  import { Button, Modal, NumberInput, Select, Stack, TextInput } from '@mantine/core'
  import { useForm } from '@mantine/form'
  import { zodResolver } from 'mantine-form-zod-resolver'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQueryClient } from '@tanstack/react-query'
  import { z } from 'zod'

  import { createAccountRequest } from '../api/accounts'
  import { COMMON_CURRENCIES } from '../lib/format'

  // Zod-схема для формы создания счёта. Дублирует ограничения Pydantic на бэке —
  // клиент даёт мгновенный фидбэк, бэк гарантирует безопасность.
  const accountSchema = z.object({
    name: z.string().min(1, 'Введите название').max(100, 'Максимум 100 символов'),
    balance: z.number().refine((v) => Number.isFinite(v), 'Введите число'),
    currency_code: z.string().length(3, 'Код валюты — 3 символа'),
  })

  type AccountFormValues = z.infer<typeof accountSchema>

  interface Props {
    opened: boolean
    onClose: () => void
  }

  export function AccountFormModal({ opened, onClose }: Props) {
    const queryClient = useQueryClient()

    const form = useForm<AccountFormValues>({
      initialValues: {
        name: '',
        balance: 0,
        currency_code: 'RUB',
      },
      validate: zodResolver(accountSchema),
    })

    const createMutation = useMutation({
      mutationFn: (values: AccountFormValues) => createAccountRequest(values),
      onSuccess: (data) => {
        notifications.show({
          title: 'Счёт создан',
          message: `«${data.name}» добавлен в список`,
          color: 'green',
        })
        // Инвалидация кеша — TanStack Query перезапросит ['accounts'], и
        // AccountsPage автоматически перерисуется с новым счётом.
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
        form.reset()
        onClose()
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onError: (error: any) => {
        // FastAPI: detail может быть строкой (наша 409) или массивом (Pydantic 422).
        const raw = error.response?.data?.detail
        const message =
          typeof raw === 'string'
            ? raw
            : Array.isArray(raw)
              ? raw.map((e) => e.msg).join('; ')
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
      <Modal opened={opened} onClose={handleClose} title="Новый счёт" centered>
        <form onSubmit={form.onSubmit((values) => createMutation.mutate(values))}>
          <Stack>
            <TextInput
              label="Название"
              placeholder="Например, Сбер карта"
              required
              {...form.getInputProps('name')}
            />
            <NumberInput
              label="Начальный баланс"
              description="Сколько денег уже на счету сейчас"
              decimalScale={2}
              fixedDecimalScale
              allowNegative={false}
              {...form.getInputProps('balance')}
            />
            <Select
              label="Валюта"
              data={COMMON_CURRENCIES}
              searchable
              allowDeselect={false}
              {...form.getInputProps('currency_code')}
            />
            <Button type="submit" loading={createMutation.isPending}>
              Создать
            </Button>
          </Stack>
        </form>
      </Modal>
    )
  }