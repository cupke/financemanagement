    import { useNavigate } from 'react-router-dom'
    import {
      Button,
      Card,
      Container,
      Loader,
      Stack,
      Text,
      Title,
    } from '@mantine/core'
    import { modals } from '@mantine/modals'
    import { notifications } from '@mantine/notifications'
    import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

    import { deleteAccountRequest, getMeRequest } from '../api/auth'
    import { useAuthStore } from '../stores/auth'

    // Защищённая страница профиля. Показывает email + id + дату создания
    // текущего пользователя. Данные берутся через GET /api/v1/users/me.
    //
    // Внизу — «Опасная зона» с двумя необратимыми действиями: выход
    // и удаление аккаунта. Удаление каскадно сносит все счета/категории/
    // транзакции пользователя (FK ON DELETE CASCADE на бэке).
    export function MePage() {
      const navigate = useNavigate()
      const clearToken = useAuthStore((state) => state.clearToken)
      const queryClient = useQueryClient()

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

      const deleteMutation = useMutation({
        mutationFn: deleteAccountRequest,
        onSuccess: () => {
          // Чистим всё локальное состояние: токен и кеш всех запросов.
          // Без clear() кеши счетов/категорий/транзакций «протекут» в следующую
          // сессию (если зайти под другим пользователем), показав чужие данные
          // на долю секунды до их инвалидации.
          clearToken()
          queryClient.clear()
          notifications.show({
            title: 'Аккаунт удалён',
            message: 'Все ваши данные стёрты безвозвратно.',
            color: 'blue',
          })
          navigate('/login')
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onError: (error: any) => {
          notifications.show({
            title: 'Ошибка',
            message:
              error.response?.data?.detail || 'Не удалось удалить аккаунт',
            color: 'red',
          })
        },
      })

      const handleDelete = () => {
        modals.openConfirmModal({
          title: '⚠️  Удалить аккаунт?',
          centered: true,
          children: (
            <Stack gap="xs">
              <Text size="sm">
                Будут <strong>безвозвратно</strong> удалены:
              </Text>
              <Text size="sm">
                • все ваши счета и их балансы;
                <br />
                • все категории и подкатегории;
                <br />
                • вся история операций.
              </Text>
              <Text size="sm" c="red" fw={500}>
                Это действие нельзя отменить.
              </Text>
            </Stack>
          ),
          labels: { confirm: 'Удалить аккаунт', cancel: 'Отмена' },
          confirmProps: { color: 'red' },
          onConfirm: () => deleteMutation.mutate(),
        })
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
            <Button onClick={handleLogout} variant="default" w="fit-content">
              Выйти
            </Button>

            {/* Опасная зона — стиль из GitHub: красная рамка вокруг
                необратимых действий, чтобы пользователь визуально отделил
                их от обычных кнопок. */}
            <Card
              withBorder
              mt="xl"
              p="md"
              style={{ borderColor: 'var(--mantine-color-red-5)' }}
            >
              <Stack gap="sm">
                <Title order={4} c="red">
                  ⚠️  Опасная зона
                </Title>
                <Text size="sm" c="dimmed">
                  Удаление аккаунта необратимо. Все ваши счета, категории и
                  транзакции будут безвозвратно стёрты в соответствии с № 152-ФЗ
                  «О персональных данных» (право на забвение).
                </Text>
                <Button
                  color="red"
                  variant="outline"
                  onClick={handleDelete}
                  loading={deleteMutation.isPending}
                  w="fit-content"
                >
                  🗑️  Удалить аккаунт
                </Button>
              </Stack>
            </Card>
          </Stack>
        </Container>
      )
    }