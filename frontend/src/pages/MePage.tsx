  import { useNavigate } from 'react-router-dom'
  import { Button, Container, Loader, Stack, Text, Title } from '@mantine/core'
  import { notifications } from '@mantine/notifications'
  import { useQuery } from '@tanstack/react-query'

  import { getMeRequest } from '../api/auth'
  import { useAuthStore } from '../stores/auth'

  // Защищённая страница профиля. Показывает email + id + дату создания
  // текущего пользователя. Данные берутся через GET /api/v1/users/me.
  //
  // useQuery — обёртка TanStack Query для GET-запросов. Сама управляет состояниями
  // loading/error/data; кеширует результат под ключом ['me'] на staleTime (30 сек,
  // настроено в main.tsx). Это значит: если уйти со страницы и вернуться через
  // 10 секунд — данные возьмутся из кеша мгновенно, без сетевого запроса.
  export function MePage() {
    const navigate = useNavigate()
    const clearToken = useAuthStore((state) => state.clearToken)

    const { data, isLoading, isError } = useQuery({
      queryKey: ['me'],
      queryFn: getMeRequest,
    })

    const handleLogout = () => {
      clearToken()
      notifications.show({
        title: 'Выход',
        message: 'Вы вышли из аккаунта',
        color: 'blue',
      })
      navigate('/login')
    }

    if (isLoading) {
      return (
        <Container size="sm" py="xl">
          <Loader />
        </Container>
      )
    }

    if (isError || !data) {
      // На 401 наш axios-интерсептор уже почистил токен, ProtectedRoute сделает
      // редирект на /login и до этой ветки мы не дойдём. Сюда попадаем при
      // других проблемах (5xx, сетевая ошибка, таймаут) — показываем сообщение,
      // не выкидывая пользователя.
      return (
        <Container size="sm" py="xl">
          <Text c="red">Не удалось загрузить данные пользователя.</Text>
        </Container>
      )
    }

    return (
      <Container size="sm" py="xl">
        <Stack>
          <Title order={2}>Профиль</Title>
          <Text>
            <strong>Email:</strong> {data.email}
          </Text>
          <Text>
            <strong>ID:</strong> {data.id}
          </Text>
          <Text>
            <strong>Создан:</strong>{' '}
            {new Date(data.created_at).toLocaleString('ru-RU')}
          </Text>
          <Button onClick={handleLogout} color="red" w="fit-content">
            Выйти
          </Button>
        </Stack>
      </Container>
    )
  }