  import { StrictMode } from 'react'
  import { createRoot } from 'react-dom/client'
  import { BrowserRouter } from 'react-router-dom'
  import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
  import { MantineProvider } from '@mantine/core'
  import { ModalsProvider } from '@mantine/modals'
  import { Notifications } from '@mantine/notifications'

  // Стили Mantine. @mantine/modals использует базовый Modal из @mantine/core
  // и собственного styles.css не имеет — отдельный импорт не нужен.
  import '@mantine/core/styles.css'
  import '@mantine/notifications/styles.css'

  import App from './App'
  import './index.css'

  // QueryClient — это «мозг» TanStack Query: общий кеш HTTP-запросов и состояний loading/error.
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 30_000,
      },
    },
  })

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <MantineProvider>
        {/* ModalsProvider — глобальная очередь модалок. После этого в любом
            месте кода можно вызвать modals.openConfirmModal({...}) — не нужно
            создавать свой компонент-обёртку для каждого подтверждения. */}
        <ModalsProvider>
          <Notifications position="top-right" />
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </QueryClientProvider>
        </ModalsProvider>
      </MantineProvider>
    </StrictMode>,
  )