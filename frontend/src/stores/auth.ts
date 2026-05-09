  import { create } from 'zustand'
  import { persist } from 'zustand/middleware'

  // Zustand-стор для JWT-токена. Простая альтернатива Redux — две функции вместо
  // двух десятков. State хранится в обычном объекте, изменяется через set().
  //
  // persist — middleware, которая автоматически синхронизирует state с localStorage.
  // Это значит: после F5 / перезагрузки вкладки токен восстановится, пользователь
  // останется залогиненным.
  //
  // КОМПРОМИСС БЕЗОПАСНОСТИ: токен в localStorage уязвим к XSS — если на странице
  // исполнится чужой скрипт, он сможет прочитать localStorage. В проде стандарт
  // надёжнее — refresh-токен в httpOnly-cookie, который JS не видит. Для дипломного
  // MVP это сознательный trade-off, упомянем в защите.

  interface AuthState {
    token: string | null
    setToken: (token: string) => void
    clearToken: () => void
  }

  export const useAuthStore = create<AuthState>()(
    persist(
      (set) => ({
        token: null,
        setToken: (token) => set({ token }),
        clearToken: () => set({ token: null }),
      }),
      {
        // Имя ключа в localStorage. Префикс fintrack- — чтобы не конфликтовать
        // с другими приложениями на том же хосте.
        name: 'fintrack-auth',
      },
    ),
  )