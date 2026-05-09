import axios from 'axios'
  import { useAuthStore } from '../stores/auth'

  // Axios-instance — единая точка для всех запросов к нашему backend.
  // baseURL берётся из env-переменной VITE_API_BASE_URL (если задана в .env),
  // иначе используется дев-дефолт. В Vite все переменные с префиксом VITE_*
  // прокидываются в browser bundle через import.meta.env.
  export const apiClient = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:60000',
    timeout: 10_000,
  })

  // === Интерсепторы — это middleware для axios. ===
  // Срабатывают на КАЖДЫЙ запрос/ответ. Помогают не дублировать одну и ту же
  // логику (заголовки, обработка ошибок) во всех местах кода.

  // Перед каждым запросом: если в сторе есть токен — подкладываем Authorization.
  // Это значит, что в коде страниц мы просто вызываем apiClient.get('/users/me')
  // и не думаем о токене вручную.
  apiClient.interceptors.request.use((config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // На каждый ответ: если сервер вернул 401 — токен невалиден или истёк,
  // чистим его в сторе. Сам редирект на /login делает ProtectedRoute, когда
  // увидит null token. Так мы разделяем «политику хранения» (стор) и
  // «политику навигации» (роуты) — каждый делает только свою работу.
  apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        useAuthStore.getState().clearToken()
      }
      return Promise.reject(error)
    },
  )