import {
  Button,
  Modal,
  PasswordInput,
  Stack,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { zodResolver } from 'mantine-form-zod-resolver'
import { notifications } from '@mantine/notifications'
import { useMutation } from '@tanstack/react-query'
import { z } from 'zod'

import { changePasswordRequest } from '../api/auth'

const schema = z
  .object({
    current: z.string().min(1, 'Введите текущий пароль'),
    password: z.string().min(8, 'Минимум 8 символов'),
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    message: 'Пароли не совпадают',
    path: ['confirm'],
  })

type FormValues = z.infer<typeof schema>

interface Props {
  opened: boolean
  onClose: () => void
}

export function ChangePasswordModal({ opened, onClose }: Props) {
  const form = useForm<FormValues>({
    initialValues: { current: '', password: '', confirm: '' },
    validate: zodResolver(schema),
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      changePasswordRequest(values.current, values.password),
    onSuccess: () => {
      notifications.show({
        title: 'Пароль изменён',
        message: 'В следующий раз входите с новым паролем',
        color: 'green',
      })
      form.reset()
      onClose()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось сменить пароль',
        color: 'red',
      })
    },
  })

  const handleClose = () => {
    form.reset()
    onClose()
  }

  return (
    <Modal opened={opened} onClose={handleClose} title="Смена пароля" centered>
      <form onSubmit={form.onSubmit((values) => mutation.mutate(values))}>
        <Stack>
          <PasswordInput
            label="Текущий пароль"
            required
            {...form.getInputProps('current')}
          />
          <PasswordInput
            label="Новый пароль"
            placeholder="Минимум 8 символов"
            required
            {...form.getInputProps('password')}
          />
          <PasswordInput
            label="Повторите новый пароль"
            required
            {...form.getInputProps('confirm')}
          />
          <Button type="submit" loading={mutation.isPending}>
            Сменить пароль
          </Button>
        </Stack>
      </form>
    </Modal>
  )
}
