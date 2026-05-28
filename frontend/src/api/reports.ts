import { apiClient } from './client'

export interface BucketPoint {
  label: string
  income: string
  expense: string
  net: string
  balance: string
}

export interface CategorySlice {
  category_id: number
  category_name: string
  amount: string
}

export interface AccountCapital {
  account_id: number
  account_name: string
  balance: string
}

export interface ReportsSummary {
  total_income: string
  total_expense: string
  net: string
  avg_expense_per_bucket: string
}

export interface ReportsOverview {
  from_date: string
  to_date: string
  account_id: number | null
  currency: string
  granularity: 'day' | 'week' | 'month'
  summary: ReportsSummary
  points: BucketPoint[]
  expense_by_category: CategorySlice[]
  income_by_category: CategorySlice[]
  capital_by_account: AccountCapital[]
}

export async function getReportsOverviewRequest(
  fromDate: string,
  toDate: string,
  accountId: number | null,
): Promise<ReportsOverview> {
  const response = await apiClient.get<ReportsOverview>('/api/v1/reports/overview', {
    params: {
      from_date: fromDate,
      to_date: toDate,
      // account_id отправляем только когда выбран конкретный счёт.
      ...(accountId != null ? { account_id: accountId } : {}),
    },
  })
  return response.data
}
