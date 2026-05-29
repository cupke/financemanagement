import { apiClient } from './client'

// Типы — отражение Pydantic-схем с бэка (recurring_transaction.py).

export type RecurringKind = 'income' | 'expense' | 'transfer'
export type RecurrenceFrequency = 'daily' | 'weekly' | 'monthly' | 'yearly'

export interface RecurringTransactionRead {
  id: number
  owner_id: number
  name: string
  kind: RecurringKind
  account_id: number
  // Numeric(15,2) приходит строкой — точность float не годится для денег.
  amount: string
  currency_code: string
  category_id: number | null
  transfer_account_id: number | null
  note: string | null
  frequency: RecurrenceFrequency
  interval: number
  start_at: string
  end_at: string | null
  // Курсор движка — момент следующей назревшей операции.
  next_run_at: string
  last_run_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RecurringTransactionCreate {
  name: string
  kind: RecurringKind
  account_id: number
  amount: number
  currency_code?: string
  category_id?: number | null
  transfer_account_id?: number | null
  note?: string | null
  frequency: RecurrenceFrequency
  interval: number
  start_at: string
  end_at?: string | null
}

// PATCH правит только «безопасные» поля (тип/счета/категория неизменны).
export interface RecurringTransactionUpdate {
  name?: string
  amount?: number
  note?: string | null
  frequency?: RecurrenceFrequency
  interval?: number
  end_at?: string | null
  is_active?: boolean
}

// Итог прогона до-генерации.
export interface RunResult {
  created: number
  rules_processed: number
  deactivated: number
}

export async function listRecurringRequest(): Promise<
  RecurringTransactionRead[]
> {
  const { data } = await apiClient.get<RecurringTransactionRead[]>(
    '/api/v1/recurring-transactions',
  )
  return data
}

export async function createRecurringRequest(
  payload: RecurringTransactionCreate,
): Promise<RecurringTransactionRead> {
  const { data } = await apiClient.post<RecurringTransactionRead>(
    '/api/v1/recurring-transactions',
    payload,
  )
  return data
}

export async function updateRecurringRequest(
  id: number,
  payload: RecurringTransactionUpdate,
): Promise<RecurringTransactionRead> {
  const { data } = await apiClient.patch<RecurringTransactionRead>(
    `/api/v1/recurring-transactions/${id}`,
    payload,
  )
  return data
}

export async function deleteRecurringRequest(id: number): Promise<void> {
  await apiClient.delete(`/api/v1/recurring-transactions/${id}`)
}

// POST /run — догенерировать все назревшие операции. Идемпотентен по смыслу:
// повторный вызов сразу ничего не создаст. Вызывается автоматически при
// заходе в приложение (AppLayout) и вручную кнопкой на странице.
export async function runRecurringRequest(): Promise<RunResult> {
  const { data } = await apiClient.post<RunResult>(
    '/api/v1/recurring-transactions/run',
  )
  return data
}
