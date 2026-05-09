import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'

// Стили Mantine — без них компоненты выглядят как голый HTML без оформления.
// Подключаются один раз на всё приложение, в самой верхней точке.
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'

import App from './App'
import './index.css'

// QueryClient — это «мозг» TanStack Query: общий кеш HTTP-запросов и состояний loading/error.
// Создаём один экземпляр на всё приложение и пробрасываем через Provider — так все компоненты
// будут пользоваться одним и тем же кешем (например, после login следующий запрос /users/me
// либо ходит на сервер, либо отдаёт уже закешированный ответ).
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,           // если запрос упал — повторить 1 раз, потом отдать ошибку
      staleTime: 30_000,  // 30 секунд считаем данные «свежими» — не дёргаем сервер заново
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* MantineProvider — единая тема и стили для всех Mantine-компонентов. */}
    <MantineProvider>
      {/* Notifications — всплывающие тосты «успех/ошибка», нужны для UX при auth-операциях. */}
      <Notifications position="top-right" />
      {/* QueryClientProvider делает queryClient доступным для всех useQuery/useMutation. */}
      <QueryClientProvider client={queryClient}>
        {/* BrowserRouter включает обычные URL-маршруты (/login вместо /#/login). */}
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
