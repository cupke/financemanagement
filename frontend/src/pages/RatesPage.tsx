    import {
      Alert,
      Badge,
      Container,
      Group,
      Loader,
      Stack,
      Table,
      Text,
      Title,
    } from '@mantine/core'
    import { useQuery } from '@tanstack/react-query'

    import { listRatesRequest } from '../api/rates'

    // Форматирование курса с 4 знаками после запятой и разделителем тысяч ("74,2963").
    const rateFormatter = new Intl.NumberFormat('ru-RU', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    })

    const dateFormatter = new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    })

    const datetimeFormatter = new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })

    // Страница «Курсы валют ЦБ РФ». Тянет /api/v1/rates через TanStack Query —
    // кеш в памяти браузера + автодедупликация запросов при возврате на страницу.
    // Бэкенд тоже кеширует курсы в БД на день (cache-aside).
    export function RatesPage() {
      const { data, isLoading, isError, error } = useQuery({
        queryKey: ['rates'],
        queryFn: listRatesRequest,
        // Курсы ЦБ меняются раз в сутки — нет смысла перезапрашивать каждые
        // 5 минут (дефолт TanStack Query). 1 час — безопасный компромисс.
        staleTime: 60 * 60 * 1000,
      })

      if (isLoading) {
        return (
          <Container py="xl">
            <Group>
              <Loader />
              <Text c="dimmed">Загружаем курсы ЦБ…</Text>
            </Group>
          </Container>
        )
      }

      if (isError || !data) {
        return (
          <Container py="xl">
            <Alert color="red" title="Не удалось загрузить курсы">
              {error instanceof Error ? error.message : 'Сервер не отвечает'}
            </Alert>
          </Container>
        )
      }

      const rateDate = new Date(data.rate_date)
      const fetchedAt = new Date(data.fetched_at)

      return (
        <Container size="lg" py="xl">
          <Group justify="space-between" align="flex-end" mb="lg">
            <Title order={2}>Курсы валют</Title>
            <Stack gap={2} align="flex-end">
              <Badge size="lg" variant="light">
                ЦБ РФ на {dateFormatter.format(rateDate)}
              </Badge>
              <Text size="xs" c="dimmed">
                Обновлено {datetimeFormatter.format(fetchedAt)}
              </Text>
            </Stack>
          </Group>

          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Код</Table.Th>
                <Table.Th>Валюта</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Номинал</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Курс (₽)</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>
                  Курс за 1 единицу (₽)
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((r) => (
                <Table.Tr key={r.char_code}>
                  <Table.Td>
                    <Text fw={600}>{r.char_code}</Text>
                  </Table.Td>
                  <Table.Td>{r.name}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>{r.nominal}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    {rateFormatter.format(Number(r.value))}
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    {rateFormatter.format(Number(r.vunit_rate))}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Container>
      )
    }