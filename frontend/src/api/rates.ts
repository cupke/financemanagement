    import { apiClient } from './client'

    // Один курс валюты в ответе API. `value` и `vunit_rate` приходят строками —
    // Decimal в JSON всегда строка, чтобы при передаче по сети не терялась
    // точность копеек. На фронте при отображении парсим в Number.
    export interface RateRead {
      char_code: string
      num_code: string
      name: string
      nominal: number
      value: string
      vunit_rate: string
      rate_date: string  // 'YYYY-MM-DD'
    }

    export interface RatesListResponse {
      rate_date: string
      fetched_at: string  // ISO datetime
      items: RateRead[]
    }

    // GET /api/v1/rates — все курсы ЦБ РФ на актуальную дату.
    export async function listRatesRequest(): Promise<RatesListResponse> {
      const { data } = await apiClient.get<RatesListResponse>('/api/v1/rates')
      return data
    }

    // GET /api/v1/rates/{code} — курс конкретной валюты по коду ISO 4217.
    export async function getRateRequest(charCode: string): Promise<RateRead> {
      const { data } = await apiClient.get<RateRead>(
        `/api/v1/rates/${encodeURIComponent(charCode)}`,
      )
      return data
    }