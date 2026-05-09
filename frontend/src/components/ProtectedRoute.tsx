  import type { ReactNode } from 'react'
  import { Navigate } from 'react-router-dom'
  import { useAuthStore } from '../stores/auth'

  // Обёртка для защищённых маршрутов: если в сторе нет токена — редирект на /login.
  // Если токен есть — рендерим children (например, MePage).
  //
  // Это «слой авторизации» уровня роутера. Бэкенд тоже проверяет токен на каждом
  // защищённом эндпоинте — это «слой авторизации» уровня API. Дублирование намеренное:
  // фронт защищает только UX (не показывать пустую страницу пока токена нет), реальную
  // безопасность гарантирует бэк. Если кто-то отключит ProtectedRoute в DevTools и
  // зайдёт на /me — запрос к /users/me всё равно вернёт 401, данные не утекут.
  export function ProtectedRoute({ children }: { children: ReactNode }) {
    const token = useAuthStore((state) => state.token)

    if (!token) {
      // replace=true — заменяет текущую запись в истории браузера, чтобы кнопка
      // «назад» не возвращала пользователя на защищённую страницу.
      return <Navigate to="/login" replace />
    }

    return <>{children}</>
  }