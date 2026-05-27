    import { useNavigate } from 'react-router-dom'
    import {
      Avatar,
      Button,
      Card,
      Container,
      Group,
      Loader,
      Stack,
      Text,
      Title,
    } from '@mantine/core'
    import { modals } from '@mantine/modals'
    import { notifications } from '@mantine/notifications'
    import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

    import { listAccountsRequest } from '../api/accounts'
    import { deleteAccountRequest, getMeRequest } from '../api/auth'
    import { listCategoriesRequest } from '../api/categories'
    import { listTransactionsRequest } from '../api/transactions'
    import { formatMoney, pluralRu } from '../lib/format'
    import { useAuthStore } from '../stores/auth'
    import { useDocumentTitle } from '../lib/useDocumentTitle'

    // Расширенная страница профиля. Состоит из трёх секций:
    // 1. Hero — аватар с инициалом + email + точная дата регистрации + Выйти.
    // 2. Статистика — счета / категории / транзакции + общий капитал по валютам.
    // 3. Опасная зона — удаление аккаунта (152-ФЗ ст. 19).
    //
    // Статистика берётся из тех же queryKey, что используют AccountsPage,
    // CategoriesPage, TransactionsPage — благодаря TanStack Query это переиспользует
    // кеш без дополнительных сетевых запросов.
    export function MePage() {
      useDocumentTitle('Профиль')
      const navigate = useNavigate()
      const clearToken = useAuthStore((state) => state.clearToken)
      const queryClient = useQueryClient()

      const { data, isLoading, isError } = useQuery({
        queryKey: ['me'],
        queryFn: getMeRequest,
      })

      // Запросы для статистики. Если пользователь уже посещал /accounts, /categories
      // или /transactions — данные возьмутся из кеша TanStack Query мгновенно.
      const { data: accounts = [] } = useQuery({
        queryKey: ['accounts'],
        queryFn: listAccountsRequest,
      })
      const { data: categories = [] } = useQuery({
        queryKey: ['categories'],
        queryFn: () => listCategoriesRequest(),
      })
      // Отдельный queryKey для статистики, чтобы не конфликтовать с TransactionsPage
      // (там фильтры в queryKey). Limit 500 — достаточно для подсчёта у любого
      // адекватного пользователя.
      const { data: transactions = [] } = useQuery({
        queryKey: ['transactions-stats'],
        queryFn: () => listTransactionsRequest({ limit: 500 }),
      })

      const deleteMutation = useMutation({
        mutationFn: deleteAccountRequest,
        onSuccess: () => {
          // Чистим всё локальное состояние: токен и кеш всех запросов.
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
          title: '⚠️   Удалить аккаунт?',
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
        return (
          <Container size="sm" py="xl">
            <Text c="red">Не удалось загрузить данные пользователя.</Text>
          </Container>
        )
      }

      // Общий капитал по валютам — то же вычисление, что на AccountsPage.
      const totalsByCurrency = accounts.reduce<Record<string, number>>(
        (acc, a) => {
          acc[a.currency_code] = (acc[a.currency_code] ?? 0) + Number(a.balance)
          return acc
        },
        {},
      )

      // new Date(string).toLocaleString — pure (зависит только от строки и
      // локали браузера), безопасно вычислять прямо в render. Date.now() ниже
      // нигде не используется — отсюда и упрощение кода без useMemo/useEffect.
      const createdAtFull = new Date(data.created_at).toLocaleString('ru-RU')

      return (
        <Container size="sm" py="xl">
          <Stack gap="lg">
            <Title order={2}>Профиль</Title>

            {/* Hero-карточка: аватар с инициалом + email + точная дата
                регистрации. Внизу карточки — кнопка «Выйти». Логично, что
                управление сеансом (выход) живёт рядом с заголовком профиля. */}
            <Card withBorder p="lg">
              <Group gap="md" wrap="nowrap">
                  <Avatar color="blue" size="xl" radius="xl">
                    {data.email[0].toUpperCase()}
                  </Avatar>
                  <Stack gap={2} style={{ minWidth: 0, flex: 1 }}>
                    <Text fw={600} size="lg" truncate>
                      {data.email}
                    </Text>
                    <Text size="sm" c="dimmed">
                      Зарегистрирован: {createdAtFull}
                    </Text>
                  </Stack>
                </Group>
            </Card>

            {/* Статистика по аккаунту. Три цифры на одной строке + общий капитал
                снизу. На мобильных карточки складываются вертикально (Group grow). */}
            <Card withBorder p="lg">
              <Stack gap="md">
                <Title order={4}>Статистика</Title>

                <Group gap="md" grow>
                  <StatCard
                    emoji="🏦"
                    count={accounts.length}
                    label={pluralRu(accounts.length, 'счёт', 'счёта', 'счетов')}
                  />
                  <StatCard
                    emoji="📂"
                    count={categories.length}
                    label={pluralRu(
                      categories.length,
                      'категория',
                      'категории',
                      'категорий',
                    )}
                  />
                  <StatCard
                    emoji="📝"
                    count={transactions.length}
                    label={pluralRu(
                      transactions.length,
                      'операция',
                      'операции',
                      'операций',
                    )}
                  />
                </Group>

                {Object.keys(totalsByCurrency).length > 0 && (
                  <Stack gap={4}>
                    <Text size="sm" c="dimmed">
                      Общий капитал
                    </Text>
                    <Group gap="md" wrap="wrap">
                      {Object.entries(totalsByCurrency).map(([code, total]) => (
                        <Text key={code} fw={700} size="lg">
                          {formatMoney(total, code)}
                        </Text>
                      ))}
                    </Group>
                  </Stack>
                )}
              </Stack>
            </Card>

            {/* Опасная зона — удаление аккаунта (152-ФЗ ст. 19). */}
            <Card
              withBorder
              p="lg"
              style={{ borderColor: 'var(--mantine-color-red-5)' }}
            >
              <Stack gap="sm">
                <Title order={4} c="red">
                  ⚠️   Опасная зона
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
                  🗑️   Удалить аккаунт
                </Button>
              </Stack>
            </Card>
          </Stack>
        </Container>
      )
    }

    // ─── Карточка одной метрики ─────────────────────────────────────────────

    interface StatCardProps {
      emoji: string
      count: number
      label: string
    }

    // Маленький компонент для одной статистики (счета / категории / транзакции).
    // Вынесен, чтобы не дублировать одинаковую вёрстку три раза.
    function StatCard({ emoji, count, label }: StatCardProps) {
      return (
        <Card withBorder p="sm" ta="center">
          <Stack gap={2} align="center">
            <Text size="28px" style={{ lineHeight: 1 }}>
              {emoji}
            </Text>
            <Text fw={700} size="xl">
              {count}
            </Text>
            <Text size="xs" c="dimmed">
              {label}
            </Text>
          </Stack>
        </Card>
      )
    }