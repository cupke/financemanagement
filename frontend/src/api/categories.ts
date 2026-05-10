  import { apiClient } from './client'

  // TypeScript-типы — отражение Pydantic-схем с бэка (CategoryRead, CategoryCreate).

  export interface CategoryRead {
    id: number
    owner_id: number
    name: string
    // parent_id === null → корневая категория (без родителя).
    parent_id: number | null
    created_at: string
    updated_at: string
  }

  export interface CategoryCreate {
    name: string
    parent_id?: number | null
  }

  export interface CategoryUpdate {
    name?: string
    parent_id?: number | null
  }

  // GET /api/v1/categories → плоский список всех категорий юзера.
  // Иерархию (дерево) клиент строит сам из parent_id — это экономит запросы
  // (не нужно делать N запросов «дай детей категории X» рекурсивно).
  export async function listCategoriesRequest(): Promise<CategoryRead[]> {
    const { data } = await apiClient.get<CategoryRead[]>('/api/v1/categories')
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