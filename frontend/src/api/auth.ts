  import { apiClient } from './client'

  // TypeScript-типы — отражение Pydantic-схем с бэка (UserRead, TokenResponse).
  // Если бэк поменяет контракт API, TypeScript-ошибки укажут точные места
  // несовпадения здесь и в страницах, которые их используют. Это «контракт по типам»,
  // один из главных бонусов TS поверх обычного JS.

  export interface UserRead {
    id: number
    email: string
    // FastAPI сериализует datetime в ISO-8601, например "2026-05-09T20:14:00".
    created_at: string
  }

  export interface TokenResponse {
    access_token: string
    // На бэке всегда "bearer" — но честно описываем тип, не захардкоживаем.
    token_type: string
  }

  // POST /api/v1/auth/login → JWT
  export async function loginRequest(
    email: string,
    password: string,
  ): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>(
      '/api/v1/auth/login',
      { email, password },
    )
    return data
  }

  // POST /api/v1/auth/register → созданный пользователь (HTTP 201).
  // Замечание: бэк отдаёт UserRead, а не токен — то есть после регистрации
  // нужно отдельно вызвать loginRequest. Это сделано в RegisterPage.
  export async function registerRequest(
    email: string,
    password: string,
  ): Promise<UserRead> {
    const { data } = await apiClient.post<UserRead>(
      '/api/v1/auth/register',
      { email, password },
    )
    return data
  }

  // GET /api/v1/users/me → текущий пользователь.
  // Authorization-заголовок подкладывает интерсептор apiClient — здесь о нём
  // не думаем.
  export async function getMeRequest(): Promise<UserRead> {
    const { data } = await apiClient.get<UserRead>('/api/v1/users/me')
    return data
  }

      // DELETE /api/v1/users/me → 204 No Content.
    // Каскадно удаляет всё, что принадлежит пользователю (счета, категории,
    // транзакции) через ON DELETE CASCADE в БД. После успешного вызова клиент
    // должен очистить токен и редиректить на /login.
    export async function deleteAccountRequest(): Promise<void> {
      await apiClient.delete('/api/v1/users/me')
    }