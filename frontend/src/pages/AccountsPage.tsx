    import { useMemo, useState } from 'react'
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
    import { listRatesRequest } from '../api/rates'
    import { AccountFormModal } from '../components/AccountFormModal'
    import { ACCOUNT_KIND_META, formatMoney, pluralRu } from '../lib/format'
    import { useDocumentTitle } from '../lib/useDocumentTitle'

    // Главная страница после логина: список счетов с балансами и кнопка добавления.
    export function AccountsPage() {
      useDocumentTitle('Счета')
      const [modalOpened, setModalOpened] = useState(false)
      // Если null — режим создания. Если AccountRead — редактирование того счёта.
      const [editingAccount, setEditingAccount] = useState<AccountRead | null>(null)
      const queryClient = useQueryClient()

      const { data: accounts, isLoading, isError } = useQuery({
        queryKey: ['accounts'],
        queryFn: listAccountsRequest,
      })

      // Курсы ЦБ — нужны для сводки «общий капитал в рублях».
      // Грузим параллельно со счетами; если не загрузились — просто не
      // покажем эквивалент в RUB (graceful degradation, остальное работает).
      const { data: ratesData } = useQuery({
        queryKey: ['rates'],
        queryFn: listRatesRequest,
      })

      // Map char_code → курс к рублю (за 1 единицу). RUB = 1 захардкожен:
      // CBR не публикует «курс RUB к RUB», но он по определению единичный.
      // useMemo здесь обязателен ДО любых early-return (rules of hooks).
      const rateByCode = useMemo(() => {
        const map = new Map<string, number>()
        map.set('RUB', 1)
        if (ratesData) {
          for (const r of ratesData.items) {
            map.set(r.char_code, Number(r.vunit_rate))
          }
        }
        return map
      }, [ratesData])

      const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteAccountRequest(id),
        onSuccess: () => {
          notifications.show({
            title: 'Счёт удалён',
            message: 'Счёт и связанные с ним транзакции удалены',
            color: 'blue',
          })
          queryClient.invalidateQueries({ queryKey: ['accounts'] })
          // Удаление счёта каскадом сносит его операции → обновляем всё
          // производное: история, дашборд, отчёты, бюджеты.
          queryClient.invalidateQueries({ queryKey: ['transactions'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
          queryClient.invalidateQueries({ queryKey: ['reports-overview'] })
          queryClient.invalidateQueries({ queryKey: ['budgets'] })
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

      const handleEdit = (account: AccountRead) => {
        setEditingAccount(account)
        setModalOpened(true)
      }

      const handleCreate = () => {
        setEditingAccount(null)
        setModalOpened(true)
      }

      // Сброс editingAccount при закрытии — иначе при следующем «+ Добавить»
      // форма откроется со значениями последнего редактируемого счёта.
      const handleModalClose = () => {
        setModalOpened(false)
        setEditingAccount(null)
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

      const totalsByCurrency = accounts.reduce<Record<string, number>>((acc, a) => {
        acc[a.currency_code] = (acc[a.currency_code] ?? 0) + Number(a.balance)
        return acc
      }, {})

      // Эквивалент в RUB считаем только если есть НЕ-RUB счёт (иначе строка
      // дублирует RUB-сумму выше) и для всех валют известен курс. Если у юзера
      // есть какая-то экзотическая валюта без курса от ЦБ — честнее не показать,
      // чем показать заниженную сумму.
      const nonRubCurrencies = Object.keys(totalsByCurrency).filter(
        (c) => c !== 'RUB',
      )
      let totalInRub: number | null = null
      if (nonRubCurrencies.length > 0 && ratesData) {
        let sum = 0
        let allKnown = true
        for (const [code, total] of Object.entries(totalsByCurrency)) {
          const rate = rateByCode.get(code)
          if (rate === undefined) {
            allKnown = false
            break
          }
          sum += total * rate
        }
        if (allKnown) totalInRub = sum
      }

      // «DD.MM.YYYY» из «YYYY-MM-DD» — самый компактный формат для подписи.
      const rateDateLabel = ratesData
        ? ratesData.rate_date.split('-').reverse().join('.')
        : null

      return (
        <Container size="md" py="xl">
          <Group justify="space-between" mb="lg">
            <Title order={2}>Мои счета</Title>
            <Button onClick={handleCreate}>+ Добавить счёт</Button>
          </Group>

          {accounts.length > 0 && (
            <Card withBorder p="md" mb="lg" bg="light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))">
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
                {/* Эквивалент в RUB — только при наличии валютных счетов
                    и загруженных курсов. См. логику totalInRub выше. */}
                {totalInRub !== null && rateDateLabel && (
                  <Text size="sm" c="dimmed">
                    ≈ {formatMoney(totalInRub, 'RUB')} по курсу ЦБ на {rateDateLabel}
                  </Text>
                )}
              </Stack>
            </Card>
          )}

          {accounts.length === 0 ? (
            <Card withBorder p="xl">
              <Stack align="center" gap="xs">
                <Text c="dimmed">У вас пока нет счетов.</Text>
                <Button variant="light" onClick={handleCreate}>
                  Создать первый счёт
                </Button>
              </Stack>
            </Card>
          ) : (
            <Stack gap="sm">
              {accounts.map((account) => {
                const meta = ACCOUNT_KIND_META[account.kind]
                return (
                  <Card key={account.id} withBorder p="md">
                    <Group justify="space-between" wrap="nowrap" align="center">
                      <Group gap="md" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                        <Text size="28px" style={{ lineHeight: 1 }}>
                          {meta.emoji}
                        </Text>
                        <Stack gap={2} style={{ minWidth: 0, flex: 1 }}>
                          <Text fw={600} size="lg" truncate>
                            {account.name}
                          </Text>
                          <Group gap="xs" wrap="nowrap">
                            <Text size="xs" c="dimmed">
                              {meta.label}
                            </Text>
                            {account.note && (
                              <>
                                <Text size="xs" c="dimmed">·</Text>
                                <Text size="xs" c="dimmed" truncate>
                                  {account.note}
                                </Text>
                              </>
                            )}
                          </Group>
                        </Stack>
                      </Group>
                      <Group gap="md" wrap="nowrap">
                        <Text fw={700} size="xl">
                          {formatMoney(account.balance, account.currency_code)}
                        </Text>
                        <ActionIcon
                          variant="subtle"
                          aria-label="Редактировать счёт"
                          onClick={() => handleEdit(account)}
                        >
                          ✏️ 
                        </ActionIcon>
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
                )
              })}
            </Stack>
          )}

          <AccountFormModal
            opened={modalOpened}
            onClose={handleModalClose}
            account={editingAccount}
          />
        </Container>
      )
    }