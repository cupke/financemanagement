  import { apiClient } from './client'

  // TypeScript-типы — отражение Pydantic-схем с бэка (UserRead, TokenResponse).
  // Если бэк поменяет контракт API, TypeScript-ошибки укажут точные места
  // несовпадения здесь и в страницах, которые их используют. Это «контракт по типам»,
  // один из главных бонусов TS поверх обычного JS.

  export interface UserRead {
    id: number
    email: string
    // Подтверждён ли email (ссылкой из письма). Влияет на баннер-напоминание.
    email_verified: boolean
    // FastAPI сериализует datetime в ISO-8601, например "2026-05-09T20:14:00".
    created_at: string
  }

  // Ответ-сообщение от операций без полезной нагрузки (MessageResponse на бэке).
  export interface MessageResponse {
    detail: string
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

    // POST /api/v1/auth/change-password — сменить пароль (для залогиненного).
    export async function changePasswordRequest(
      currentPassword: string,
      newPassword: string,
    ): Promise<MessageResponse> {
      const { data } = await apiClient.post<MessageResponse>(
        '/api/v1/auth/change-password',
        { current_password: currentPassword, new_password: newPassword },
      )
      return data
    }

    // POST /api/v1/auth/forgot-password — запросить ссылку для сброса пароля.
    // Ответ всегда одинаковый (anti-enumeration), токена в нём нет.
    export async function forgotPasswordRequest(
      email: string,
    ): Promise<MessageResponse> {
      const { data } = await apiClient.post<MessageResponse>(
        '/api/v1/auth/forgot-password',
        { email },
      )
      return data
    }

    // POST /api/v1/auth/reset-password — задать новый пароль по токену из письма.
    export async function resetPasswordRequest(
      token: string,
      newPassword: string,
    ): Promise<MessageResponse> {
      const { data } = await apiClient.post<MessageResponse>(
        '/api/v1/auth/reset-password',
        { token, new_password: newPassword },
      )
      return data
    }

    // POST /api/v1/auth/verify-email — подтвердить почту по токену из письма.
    export async function verifyEmailRequest(
      token: string,
    ): Promise<MessageResponse> {
      const { data } = await apiClient.post<MessageResponse>(
        '/api/v1/auth/verify-email',
        { token },
      )
      return data
    }

    // POST /api/v1/auth/resend-verification — повторно выслать письмо
    // подтверждения (для залогиненного пользователя).
    export async function resendVerificationRequest(): Promise<MessageResponse> {
      const { data } = await apiClient.post<MessageResponse>(
        '/api/v1/auth/resend-verification',
      )
      return data
    }