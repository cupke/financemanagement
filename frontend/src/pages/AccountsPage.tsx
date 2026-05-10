  import { useState } from 'react'
  import {
    ActionIcon,
    Button,
    Card,
    Container,
    Group,
    Loader,
    Stack,
    Text,
    Title,
  } from '@mantine/core'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
  import { modals } from '@mantine/modals'

  import {
    deleteAccountRequest,
    listAccountsRequest,
    type AccountRead,
  } from '../api/accounts'
  import { AccountFormModal } from '../components/AccountFormModal'
  import { formatMoney, pluralRu } from '../lib/format'

  // Главная страница после логина: список счетов с балансами и кнопка добавления.
  export function AccountsPage() {
    const [modalOpened, setModalOpened] = useState(false)
    const queryClient = useQueryClient()

    const { data: accounts, isLoading, isError } = useQuery({
      queryKey: ['accounts'],
      queryFn: listAccountsRequest,
    })

    const deleteMutation = useMutation({
      mutationFn: (id: number) => deleteAccountRequest(id),
      onSuccess: () => {
        notifications.show({
          title: 'Счёт удалён',
          message: 'Счёт и связанные с ним транзакции удалены',
          color: 'blue',
        })
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onError: (error: any) => {
        notifications.show({
          title: 'Ошибка',
          message: error.response?.data?.detail || 'Не удалось удалить счёт',
          color: 'red',
        })
      },
    })

    const handleDelete = (account: AccountRead) => {
      modals.openConfirmModal({
        title: 'Удалить счёт?',
        centered: true,
        children: (
          <Text size="sm">
            Удалить счёт «<strong>{account.name}</strong>»?
            Все его транзакции тоже будут удалены. Это действие необратимо.
          </Text>
        ),
        labels: { confirm: 'Удалить', cancel: 'Отмена' },
        confirmProps: { color: 'red' },
        onConfirm: () => deleteMutation.mutate(account.id),
      })
    }

    if (isLoading) {
      return (
        <Container py="xl">
          <Loader />
        </Container>
      )
    }

    if (isError || !accounts) {
      return (
        <Container py="xl">
          <Text c="red">Не удалось загрузить список счетов.</Text>
        </Container>
      )
    }

    // Группировка балансов по валютам — суммы в разных валютах нельзя складывать
    // без курсов конвертации. На главном экране «Итого» показывается отдельно
    // для каждой валюты (RUB: ..., USD: ...).
    const totalsByCurrency = accounts.reduce<Record<string, number>>((acc, a) => {
      acc[a.currency_code] = (acc[a.currency_code] ?? 0) + Number(a.balance)
      return acc
    }, {})

    return (
      <Container size="md" py="xl">
        <Group justify="space-between" mb="lg">
          <Title order={2}>Мои счета</Title>
          <Button onClick={() => setModalOpened(true)}>+ Добавить счёт</Button>
        </Group>

        {/* Hero-карточка с общим капиталом — самая важная цифра дашборда.
        Поставлена в самый верх, чтобы пользователю не приходилось скроллить
        до конца списка для ответа «сколько у меня всего». Балансы группируются
        по валютам — складывать разные валюты без курсов нельзя. */}
        {accounts.length > 0 && (
          <Card withBorder p="md" mb="lg" bg="gray.0">
            <Stack gap={4}>
              <Text size="sm" c="dimmed">
                Общий капитал · {accounts.length}{' '}
                {pluralRu(accounts.length, 'счёт', 'счёта', 'счетов')}
              </Text>
              <Group gap="lg" wrap="wrap">
                {Object.entries(totalsByCurrency).map(([code, total]) => (
                  <Text key={code} fw={700} size="xl">
                    {formatMoney(total, code)}
                  </Text>
                ))}
              </Group>
            </Stack>
          </Card>
        )}

        {accounts.length === 0 ? (
          <Card withBorder p="xl">
            <Stack align="center" gap="xs">
              <Text c="dimmed">У вас пока нет счетов.</Text>
              <Button variant="light" onClick={() => setModalOpened(true)}>
                Создать первый счёт
              </Button>
            </Stack>
          </Card>
        ) : (
          <Stack gap="sm">
            {accounts.map((account) => (
              <Card key={account.id} withBorder p="md">
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={600} size="lg">
                    {account.name}
                  </Text>
                  <Group gap="md" wrap="nowrap">
                    <Text fw={700} size="xl">
                      {formatMoney(account.balance, account.currency_code)}
                    </Text>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label="Удалить счёт"
                      onClick={() => handleDelete(account)}
                      loading={
                        deleteMutation.isPending &&
                        deleteMutation.variables === account.id
                      }
                    >
                      🗑️ 
                    </ActionIcon>
                  </Group>
                </Group>
              </Card>
            ))}
          </Stack>
        )}

        <AccountFormModal
          opened={modalOpened}
          onClose={() => setModalOpened(false)}
        />
      </Container>
    )
  }