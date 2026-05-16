    import { apiClient } from './client'

    // Тип счёта. Literal на бэке (Pydantic) ↔ union на фронте (TypeScript) —
    // одинаковый строгий контракт по обе стороны API.
    export type AccountKind =
      | 'card'
      | 'cash'
      | 'savings'
      | 'credit'
      | 'e_wallet'
      | 'other'

    // TypeScript-типы — отражение Pydantic-схем с бэка.
    // Если бэк поменяет контракт API, TS-ошибки укажут точные места несовпадения.

    export interface AccountRead {
      id: number
      owner_id: number
      name: string
      kind: AccountKind
      // null — у счёта нет заметки. На фронте показываем заметку,
      // только если она не null и не пустая строка.
      note: string | null
      // opening_balance — снимок состояния на opening_date (то, что юзер
      // ввёл при создании счёта или поправил позже). balance — производный
      // current: opening_balance + Σ(транзакции с occurred_at >= opening_date).
      // Подробнее — в vkr/02_design.md, раздел про модель «opening + движения».
      // Numeric(15,2) на бэке сериализуется в строку через json — это норма для
      // финансовых сумм (избежать потерь точности float). Парсим в Number при отображении.
      opening_balance: string
      opening_date: string
      balance: string
      currency_code: string
      created_at: string
      updated_at: string
    }

    export interface AccountCreate {
      name: string
      kind?: AccountKind
      note?: string | null
      // «Сколько на счету на opening_date» — обычно равно «сколько прямо сейчас
      // в банке». Все будущие транзакции с occurred_at >= opening_date будут
      // наращивать balance поверх этого значения.
      opening_balance?: number
      // ISO 8601. Если не передано — бэк подставит datetime.now(timezone.utc).
      opening_date?: string
      currency_code?: string
    }

    export interface AccountUpdate {
      name?: string
      kind?: AccountKind
      note?: string | null
      // Изменение opening_balance или opening_date вызывает на бэке
      // полный пересчёт current balance по всем транзакциям счёта.
      opening_balance?: number
      opening_date?: string
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
    // но оставлен в API-слое для удобства будущих этапов (редактирование счёта).
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