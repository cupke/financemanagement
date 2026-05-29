import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Anchor,
  Button,
  Container,
  PasswordInput,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { zodResolver } from 'mantine-form-zod-resolver'
import { notifications } from '@mantine/notifications'
import { useMutation } from '@tanstack/react-query'
import { z } from 'zod'

import { resetPasswordRequest } from '../api/auth'
import { useDocumentTitle } from '../lib/useDocumentTitle'

const schema = z
  .object({
    password: z.string().min(8, 'Минимум 8 символов'),
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    message: 'Пароли не совпадают',
    path: ['confirm'],
  })

type FormValues = z.infer<typeof schema>

export function ResetPasswordPage() {
  useDocumentTitle('Новый пароль')
  const navigate = useNavigate()
  // Токен приходит в ссылке из письма: /reset-password?token=...
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const form = useForm<FormValues>({
    initialValues: { password: '', confirm: '' },
    validate: zodResolver(schema),
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      resetPasswordRequest(token ?? '', values.password),
    onSuccess: () => {
      notifications.show({
        title: 'Пароль изменён',
        message: 'Теперь войдите с новым паролем',
        color: 'green',
      })
      navigate('/login')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message:
          error.response?.data?.detail ||
          'Ссылка недействительна или устарела. Запросите новую.',
        color: 'red',
      })
    },
  })

  // Без токена страница бессмысленна — открыли не по ссылке из письма.
  if (!token) {
    return (
      <Container size="xs" py="xl">
        <Title order={2} mb="lg">
          Новый пароль
        </Title>
        <Stack>
          <Alert color="red" variant="light">
            Ссылка неполная или повреждена. Откройте её из письма целиком или
            запросите сброс заново.
          </Alert>
          <Text size="sm" ta="center">
            <Anchor component={Link} to="/forgot-password">
              Запросить ссылку заново
            </Anchor>
          </Text>
        </Stack>
      </Container>
    )
  }

  return (
    <Container size="xs" py="xl">
      <Title order={2} mb="lg">
        Новый пароль
      </Title>
      <form onSubmit={form.onSubmit((values) => mutation.mutate(values))}>
        <Stack>
          <PasswordInput
            label="Новый пароль"
            placeholder="Минимум 8 символов"
            required
            {...form.getInputProps('password')}
          />
          <PasswordInput
            label="Повторите пароль"
            required
            {...form.getInputProps('confirm')}
          />
          <Button type="submit" loading={mutation.isPending}>
            Сохранить пароль
          </Button>
          <Text size="sm" ta="center">
            <Anchor component={Link} to="/login">
              Вернуться ко входу
            </Anchor>
          </Text>
        </Stack>
      </form>
    </Container>
  )
}
