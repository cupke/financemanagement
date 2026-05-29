  import { Link, useNavigate } from 'react-router-dom'
  import {
    Anchor,
    Button,
    Container,
    PasswordInput,
    Stack,
    Text,
    TextInput,
    Title,
  } from '@mantine/core'
  import { useForm } from '@mantine/form'
  import { zodResolver } from 'mantine-form-zod-resolver'
  import { notifications } from '@mantine/notifications'
  import { useMutation } from '@tanstack/react-query'
  import { z } from 'zod'

  import { loginRequest, registerRequest } from '../api/auth'
  import { useAuthStore } from '../stores/auth'
  import { useDocumentTitle } from '../lib/useDocumentTitle'

  // Та же логика «двойной валидации», что и в LoginPage. Минимум 8 символов
  // пароля повторяет ограничение из Pydantic-схемы UserCreate на бэке.
  const registerSchema = z.object({
    email: z.string().email('Неверный формат email'),
    password: z
      .string()
      .min(8, 'Минимум 8 символов')
      .max(128, 'Максимум 128 символов'),
  })

  type RegisterFormValues = z.infer<typeof registerSchema>

  export function RegisterPage() {
    useDocumentTitle('Регистрация')
    const navigate = useNavigate()
    const setToken = useAuthStore((state) => state.setToken)

    const form = useForm<RegisterFormValues>({
      initialValues: { email: '', password: '' },
      validate: zodResolver(registerSchema),
    })

    // После успешной регистрации сразу делаем login — чтобы пользователь не
    // вводил креды второй раз. mutationFn возвращает результат login (токен),
    // который в onSuccess кладём в стор. Бэк register отдаёт UserRead без
    // токена, поэтому отдельный шаг login обязателен.
    const registerMutation = useMutation({
      mutationFn: async (values: RegisterFormValues) => {
        await registerRequest(values.email, values.password)
        return loginRequest(values.email, values.password)
      },
      onSuccess: (data) => {
        setToken(data.access_token)
        notifications.show({
          title: 'Успех',
          message: 'Аккаунт создан',
          color: 'green',
        })
        // После регистрации — на главную (дашборд).
        navigate('/')
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onError: (error: any) => {
        const message =
          error.response?.data?.detail || 'Не удалось зарегистрироваться'
        notifications.show({
          title: 'Ошибка',
          message,
          color: 'red',
        })
      },
    })

    return (
      <Container size="xs" py="xl">
        <Title order={2} mb="lg">
          Регистрация в FinTrack
        </Title>
        <form
          onSubmit={form.onSubmit((values) => registerMutation.mutate(values))}
        >
          <Stack>
            <TextInput
              label="Email"
              type="email"
              placeholder="user@example.com"
              required
              {...form.getInputProps('email')}
            />
            <PasswordInput
              label="Пароль"
              placeholder="Минимум 8 символов"
              required
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={registerMutation.isPending}>
              Зарегистрироваться
            </Button>
            <Text size="sm" ta="center">
              Уже есть аккаунт?{' '}
              <Anchor component={Link} to="/login">
                Войти
              </Anchor>
            </Text>
          </Stack>
        </form>
      </Container>
    )
  }