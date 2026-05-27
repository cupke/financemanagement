  import { StrictMode } from 'react'
  import { createRoot } from 'react-dom/client'
  import { BrowserRouter } from 'react-router-dom'
  import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
  import { MantineProvider, createTheme } from '@mantine/core'
  import { ModalsProvider } from '@mantine/modals'
  import { Notifications } from '@mantine/notifications'

  // Стили Mantine. @mantine/modals использует базовый Modal из @mantine/core
  // и собственного styles.css не имеет — отдельный импорт не нужен.
  import '@mantine/core/styles.css'
  import '@mantine/dates/styles.css'
  import '@mantine/notifications/styles.css'

  import App from './App'
  import './index.css'

    // Тема Mantine: глобальные дефолты для компонентов. Сейчас одно правило —
  // ограничение высоты выпадающего списка Select (280px ≈ 6-7 элементов, дальше
  // скролл). Без него при большом числе счетов/категорий dropdown растягивался
  // на пол-экрана. Через тему — один раз настроили для всех Select в приложении.
  const theme = createTheme({
    components: {
      Select: {
        defaultProps: {
          maxDropdownHeight: 280,
        },
      },
    },
  })

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
      <MantineProvider theme={theme} defaultColorScheme="auto">
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