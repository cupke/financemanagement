import { useEffect } from 'react'

// Меняет <title> вкладки браузера на «FinTrack — <suffix>».
// При размонтировании компонента возвращает базовый «FinTrack» — иначе
// при переходе на страницу без useDocumentTitle (например, /login)
// в шапке вкладки оставался бы старый текст.
export function useDocumentTitle(suffix: string): void {
  useEffect(() => {
    document.title = `FinTrack — ${suffix}`
    return () => {
      document.title = 'FinTrack'
    }
  }, [suffix])
}
