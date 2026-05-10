  import { apiClient } from './client'

  // Типы — отражение Pydantic-схем с бэка (TransactionRead, TransactionCreate).

  export type TransactionKind = 'income' | 'expense' | 'transfer'

  export interface TransactionRead {
    id: number
    owner_id: number
    account_id: number
    kind: TransactionKind
    // Numeric(15,2) сериализуется в строку, как и balance — точность float-а
    // не подходит для денег. Парсим в Number при отображении.
    amount: string
    currency_code: string
    category_id: number | null
    transfer_account_id: number | null
    occurred_at: string
    note: string | null
    created_at: string
    updated_at: string
  }

  export interface TransactionCreate {
    kind: TransactionKind
    account_id: number
    amount: number
    currency_code?: string
    category_id?: number | null
    transfer_account_id?: number | null
    occurred_at: string
    note?: string | null
  }

  export interface TransactionListFilters {
    account_id?: number
    category_id?: number
    kind?: TransactionKind
    from_date?: string
    to_date?: string
    limit?: number
    offset?: number
  }

  // GET /api/v1/transactions с query-параметрами фильтров.
  export async function listTransactionsRequest(
    filters: TransactionListFilters = {},
  ): Promise<TransactionRead[]> {
    // Удаляем undefined/null/'' из query — иначе axios отправит "?account_id=undefined"
    // (буквально строку), и бэк не сможет валидировать.
    const params = Object.fromEntries(
      Object.entries(filters).filter(
        ([, v]) => v !== undefined && v !== null && v !== '',
      ),
    )
    const { data } = await apiClient.get<TransactionRead[]>(
      '/api/v1/transactions',
      { params },
    )
    return data
  }

  // POST /api/v1/transactions → 201. На бэке атомарно меняет balance счёта
  // (для перевода — двух счетов) в одной БД-транзакции.
  export async function createTransactionRequest(
    payload: TransactionCreate,
  ): Promise<TransactionRead> {
    const { data } = await apiClient.post<TransactionRead>(
      '/api/v1/transactions',
      payload,
    )
    return data
  }

  export async function getTransactionRequest(
    id: number,
  ): Promise<TransactionRead> {
    const { data } = await apiClient.get<TransactionRead>(
      `/api/v1/transactions/${id}`,
    )
    return data
  }

  // DELETE /api/v1/transactions/{id} → 204. На бэке зеркально откатывает
  // эффект транзакции на балансах (для перевода — на обоих счетах).
  export async function deleteTransactionRequest(id: number): Promise<void> {
    await apiClient.delete(`/api/v1/transactions/${id}`)
  }