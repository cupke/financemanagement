import { apiClient } from './client'

// Базовая форма бюджета (без вычисляемых полей spent/percent/status —
// они появляются только в листинге GET /budgets).
export interface BudgetRead {
  id: number
  owner_id: number
  category_id: number
  amount: string // Decimal приходит как строка, парсим в Number при отображении
  // Период, на который действует бюджет. Один бюджет = один месяц.
  period_year: number
  period_month: number
  created_at: string
  updated_at: string
}

// Статус расходования — определяет цвет прогресс-бара.
// Границы синхронизированы с бэком (см. budgets.py:list_budgets).
export type BudgetStatus = 'ok' | 'warning' | 'exceeded'

// Бюджет + прогресс за свой месяц. То, что отдаёт GET /budgets.
export interface BudgetWithProgress extends BudgetRead {
  spent: string // Decimal как строка
  percent: number
  status: BudgetStatus
  category_name: string
}

export interface BudgetCreate {
  category_id: number
  amount: number
  period_year: number
  period_month: number
}

export interface BudgetUpdate {
  amount?: number
}

// GET /api/v1/budgets?year=&month= → бюджеты только на этот месяц.
// Без параметров — за текущий месяц по UTC.
export async function listBudgetsRequest(
  year?: number,
  month?: number,
): Promise<BudgetWithProgress[]> {
  const params = new URLSearchParams()
  if (year !== undefined) params.set('year', String(year))
  if (month !== undefined) params.set('month', String(month))
  const qs = params.toString()
  const url = qs ? `/api/v1/budgets?${qs}` : '/api/v1/budgets'
  const { data } = await apiClient.get<BudgetWithProgress[]>(url)
  return data
}

export async function createBudgetRequest(
  payload: BudgetCreate,
): Promise<BudgetRead> {
  const { data } = await apiClient.post<BudgetRead>('/api/v1/budgets', payload)
  return data
}

export async function updateBudgetRequest(
  id: number,
  payload: BudgetUpdate,
): Promise<BudgetRead> {
  const { data } = await apiClient.patch<BudgetRead>(
    `/api/v1/budgets/${id}`,
    payload,
  )
  return data
}

export async function deleteBudgetRequest(id: number): Promise<void> {
  await apiClient.delete(`/api/v1/budgets/${id}`)
}
