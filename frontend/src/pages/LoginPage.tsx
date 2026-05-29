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

  import { loginRequest } from '../api/auth'
  import { useAuthStore } from '../stores/auth'
  import { useDocumentTitle } from '../lib/useDocumentTitle'

  // Zod-схема валидации формы. На бэке Pydantic делает то же самое строже —
  // принцип «валидируем дважды»: клиент для UX (мгновенная реакция),
  // сервер для безопасности (клиенту нельзя доверять).
  const loginSchema = z.object({
    email: z.string().email('Неверный формат email'),
    password: z.string().min(1, 'Введите пароль'),
  })

  type LoginFormValues = z.infer<typeof loginSchema>

  export function LoginPage() {
    useDocumentTitle('Вход')
    const navigate = useNavigate()
    // Берём из стора только нужное действие — Zustand перерисовывает компонент
    // только при изменении того, что мы запрашиваем. Подписка на весь стор
    // привела бы к лишним перерисовкам.
    const setToken = useAuthStore((state) => state.setToken)

    // Mantine-форма: ведёт values, ошибки, touched-флаги. Мы ей просто говорим
    // схему валидации (Zod через resolver) — она сама проверит на blur/submit.
    const form = useForm<LoginFormValues>({
      initialValues: { email: '', password: '' },
      validate: zodResolver(loginSchema),
    })

    // useMutation — обёртка TanStack Query для запросов, меняющих серверное
    // состояние (POST/PUT/DELETE). Удобнее ручного useState — даёт isPending,
    // error, и колбэки onSuccess/onError из коробки.
    const loginMutation = useMutation({
      mutationFn: ({ email, password }: LoginFormValues) =>
        loginRequest(email, password),
      onSuccess: (data) => {
        setToken(data.access_token)
        notifications.show({
          title: 'Успех',
          message: 'Вход выполнен',
          color: 'green',
        })
        // После входа — на главную (дашборд), а не на список счетов.
        navigate('/')
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onError: (error: any) => {
        // FastAPI кладёт человекочитаемую причину в response.data.detail.
        // Если запрос вообще не дошёл (CORS / сеть) — фолбэк на общий текст.
        const message =
          error.response?.data?.detail || 'Не удалось выполнить вход'
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
          Вход в FinTrack
        </Title>
        <form
          onSubmit={form.onSubmit((values) => loginMutation.mutate(values))}
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
              placeholder="Ваш пароль"
              required
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={loginMutation.isPending}>
              Войти
            </Button>
            <Text size="sm" ta="center">
              Нет аккаунта?{' '}
              <Anchor component={Link} to="/register">
                Регистрация
              </Anchor>
            </Text>
          </Stack>
        </form>
      </Container>
    )
  }