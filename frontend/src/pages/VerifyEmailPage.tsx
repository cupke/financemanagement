import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [status, setStatus] = useState<Status>('pending')
  // Защита от двойного вызова в React StrictMode (dev): иначе второй вызов
  // получит «токен уже использован» и покажет ошибку поверх успеха.
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (!token) {
      setStatus('error')
      return
    }
    verifyEmailRequest(token)
      .then(() => setStatus('success'))
      .catch(() => setStatus('error'))
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
