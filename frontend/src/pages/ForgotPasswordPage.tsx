import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Alert,
  Anchor,
  Button,
  Container,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { zodResolver } from 'mantine-form-zod-resolver'
import { useMutation } from '@tanstack/react-query'
import { z } from 'zod'

import { forgotPasswordRequest } from '../api/auth'
import { useDocumentTitle } from '../lib/useDocumentTitle'

const schema = z.object({
  email: z.string().email('Неверный формат email'),
})

type FormValues = z.infer<typeof schema>

export function ForgotPasswordPage() {
  useDocumentTitle('Восстановление пароля')
  // Показываем подтверждение после отправки. Текст намеренно нейтральный
  // (не раскрываем, есть такой email или нет) — это сделано и на бэке.
  const [submitted, setSubmitted] = useState(false)

  const form = useForm<FormValues>({
    initialValues: { email: '' },
    validate: zodResolver(schema),
  })

  const mutation = useMutation({
    mutationFn: (values: FormValues) => forgotPasswordRequest(values.email),
    onSuccess: () => setSubmitted(true),
    // Даже при ошибке сети показываем то же сообщение — не раскрываем детали.
    onError: () => setSubmitted(true),
  })

  return (
    <Container size="xs" py="xl">
      <Title order={2} mb="lg">
        Восстановление пароля
      </Title>

      {submitted ? (
        <Stack>
          <Alert color="blue" variant="light">
            Если такой email зарегистрирован, мы отправили на него ссылку для
            сброса пароля. Проверьте почту (ссылка действует ограниченное время).
          </Alert>
          <Text size="sm" ta="center">
            <Anchor component={Link} to="/login">
              Вернуться ко входу
            </Anchor>
          </Text>
        </Stack>
      ) : (
        <form onSubmit={form.onSubmit((values) => mutation.mutate(values))}>
          <Stack>
            <Text size="sm" c="dimmed">
              Введите email от аккаунта — пришлём ссылку для сброса пароля.
            </Text>
            <TextInput
              label="Email"
              type="email"
              placeholder="user@example.com"
              required
              {...form.getInputProps('email')}
            />
            <Button type="submit" loading={mutation.isPending}>
              Отправить ссылку
            </Button>
            <Text size="sm" ta="center">
              <Anchor component={Link} to="/login">
                Вспомнили пароль? Войти
              </Anchor>
            </Text>
          </Stack>
        </form>
      )}
    </Container>
  )
}
