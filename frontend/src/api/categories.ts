    import { apiClient } from './client'
  
    // Тип категории. Аналог Pydantic Literal на бэке. Income — доходная,
    // expense — расходная. Transfer-категорий не бывает: переводы между своими
    // счетами не относятся к доходам или расходам.
    export type CategoryKind = 'income' | 'expense'

    export interface CategoryRead {
      id: number
      owner_id: number
      name: string
      kind: CategoryKind
      // parent_id === null → корневая категория (без родителя).
      parent_id: number | null
      created_at: string
      updated_at: string
    }

    export interface CategoryCreate {
      name: string
      kind: CategoryKind
      parent_id?: number | null
    }

    // Тело PATCH /api/v1/categories/{id}. kind менять нельзя (бэк это запрещает —
    // сменился бы тип у уже привязанных операций). parent_id: number — перенести
    // под другого родителя, null — сделать корневой, поле опущено — не трогать.
    export interface CategoryUpdate {
      name?: string
      parent_id?: number | null
    }

    // GET /api/v1/categories → плоский список всех категорий юзера.
    // Иерархию (дерево) клиент строит сам из parent_id — это экономит запросы
    // (не нужно делать N запросов «дай детей категории X» рекурсивно).
    // Без параметра — все категории; параметр kind фильтрует на сервере.
    // На практике мы запрашиваем все и фильтруем локально через buildCategoryOptions,
    // чтобы переиспользовать один кеш TanStack Query.
    export async function listCategoriesRequest(
      kind?: CategoryKind,
    ): Promise<CategoryRead[]> {
      const url = kind ? `/api/v1/categories?kind=${kind}` : '/api/v1/categories'
      const { data } = await apiClient.get<CategoryRead[]>(url)
      return data
    }
  
    // POST /api/v1/categories → созданная категория (HTTP 201)
    export async function createCategoryRequest(
      payload: CategoryCreate,
    ): Promise<CategoryRead> {
      const { data } = await apiClient.post<CategoryRead>(
        '/api/v1/categories',
        payload,
      )
      return data
    }
  
    // PATCH /api/v1/categories/{id} → обновлённая категория. Переименование
    // (name) и/или перенос под другого родителя (parent_id). Бэк проверяет
    // принадлежность, совпадение kind с новым родителем и отвергает циклы.
    export async function updateCategoryRequest(
      id: number,
      payload: CategoryUpdate,
    ): Promise<CategoryRead> {
      const { data } = await apiClient.patch<CategoryRead>(
        `/api/v1/categories/${id}`,
        payload,
      )
      return data
    }

    // DELETE /api/v1/categories/{id} → 204. На бэке стоит ON DELETE CASCADE —
    // все вложенные категории (потомки любой глубины) удалятся каскадно.
    export async function deleteCategoryRequest(id: number): Promise<void> {
      await apiClient.delete(`/api/v1/categories/${id}`)
    }