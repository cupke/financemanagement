  import { apiClient } from './client'

  // TypeScript-типы — отражение Pydantic-схем с бэка (AccountRead, AccountCreate, AccountUpdate).
  // Если бэк поменяет контракт API, TS-ошибки укажут точные места несовпадения.

  export interface AccountRead {
    id: number
    owner_id: number
    name: string
    // Numeric(15,2) на бэке сериализуется в строку через json — это норма для
    // финансовых сумм (избежать потерь точности float). Парсим в Number при отображении.
    balance: string
    currency_code: string
    created_at: string
    updated_at: string
  }

  export interface AccountCreate {
    name: string
    balance?: number
    currency_code?: string
  }

  export interface AccountUpdate {
    name?: string
    balance?: number
    currency_code?: string
  }

  // GET /api/v1/accounts → список счетов текущего юзера
  export async function listAccountsRequest(): Promise<AccountRead[]> {
    const { data } = await apiClient.get<AccountRead[]>('/api/v1/accounts')
    return data
  }

  // POST /api/v1/accounts → созданный счёт (HTTP 201)
  export async function createAccountRequest(
    payload: AccountCreate,
  ): Promise<AccountRead> {
    const { data } = await apiClient.post<AccountRead>('/api/v1/accounts', payload)
    return data
  }

  // PATCH /api/v1/accounts/{id} → обновлённый счёт. На MVP не используется в UI,
  // но оставлен в API-слое для удобства будущих этапов.
  export async function updateAccountRequest(
    id: number,
    payload: AccountUpdate,
  ): Promise<AccountRead> {
    const { data } = await apiClient.patch<AccountRead>(
      `/api/v1/accounts/${id}`,
      payload,
    )
    return data
  }

  // DELETE /api/v1/accounts/{id} → 204 No Content
  export async function deleteAccountRequest(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/accounts/${id}`)
  }