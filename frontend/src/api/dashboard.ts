import { apiClient } from './client'

export interface CategorySpending {
  category_id: number
  category_name: string
  spent_rub: string
}

export interface DashboardSummary {
  total_capital_rub: string
  accounts_count: number
  spent_this_month_rub: string
  transactions_this_month: number
  top_categories: CategorySpending[]
}

export async function getDashboardSummaryRequest(): Promise<DashboardSummary> {
  const response = await apiClient.get<DashboardSummary>('/api/v1/dashboard/summary')
  return response.data
}
