import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Anchor,
  Center,
  Container,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core'

import { verifyEmailRequest } from '../api/auth'
import { useDocumentTitle } from '../lib/useDocumentTitle'

type Status = 'pending' | 'success' | 'error'

export function VerifyEmailPage() {
  useDocumentTitle('Подтверждение почты')
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  // Начальный статус выводим из наличия токена: нет токена → сразу 'error'
  // (без синхронного setState в эффекте — этого требует react-hooks).
  const [status, setStatus] = useState<Status>(token ? 'pending' : 'error')
  // Защита от двойного вызова в React StrictMode (dev): иначе второй вызов
  // получит «токен уже использован» и покажет ошибку поверх успеха.
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (!token) return  // статус уже 'error' из начального значения
    verifyEmailRequest(token)
      .then(() => {
        setStatus('success')
        // Если пользователь уже залогинен — обновляем профиль, чтобы бейдж
        // «почта не подтверждена» и баннер сразу исчезли.
        queryClient.invalidateQueries({ queryKey: ['me'] })
      })
      .catch(() => setStatus('error'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return (
    <Container size="xs" py="xl">
      <Title order={2} mb="lg">
        Подтверждение почты
      </Title>

      {status === 'pending' && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {status === 'success' && (
        <Stack>
          <Alert color="green" variant="light">
            Почта подтверждена. Спасибо!
          </Alert>
          <Text size="sm" ta="center">
            <Anchor component={Link} to="/">
              Перейти на главную
            </Anchor>
          </Text>
        </Stack>
      )}

      {status === 'error' && (
        <Stack>
          <Alert color="red" variant="light">
            Ссылка недействительна или устарела. Войдите в аккаунт и запросите
            письмо для подтверждения заново.
          </Alert>
          <Text size="sm" ta="center">
            <Anchor component={Link} to="/login">
              Вернуться ко входу
            </Anchor>
          </Text>
        </Stack>
      )}
    </Container>
  )
}
