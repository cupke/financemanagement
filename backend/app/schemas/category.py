"""Pydantic-схемы категории для запросов и ответов API."""
from datetime import datetime
from typing import Literal
  
from pydantic import BaseModel, ConfigDict, Field
  

  # Тип, который попадает в Pydantic-валидацию ровно как в БД. Literal
  # гарантирует на уровне OpenAPI-схемы, что клиент пришлёт одну из двух строк.
CategoryKind = Literal["income", "expense"]
  

class CategoryCreate(BaseModel):
      """Тело запроса POST /categories."""
      name: str = Field(..., min_length=1, max_length=100)
      kind: CategoryKind = Field(
          ...,
          description="Тип категории: 'income' (доход) или 'expense' (расход).",
      )
      parent_id: int | None = Field(
          default=None,
          description="ID родительской категории. None — категория корневая.",
      )

  
class CategoryUpdate(BaseModel):
      """Тело запроса PATCH /categories/{id}.

      Различение «не прислано» vs «прислано null» делаем через
      `model_dump(exclude_unset=True)` в роутере. Это позволяет:
      - не передавать parent_id вообще → сохраняется текущий;
      - передать `"parent_id": null` → категория станет корневой.

      kind в PATCH намеренно не разрешён — менять тип у категории с уже
      привязанными транзакциями привело бы к несогласованности (например,
      у «расходных» транзакций оказалась бы «доходная» категория). Чтобы
      «переклассифицировать» — удали и создай заново.
      """
      name: str | None = Field(default=None, min_length=1, max_length=100)
      parent_id: int | None = None

  
class CategoryRead(BaseModel):
      """Что отдаём в ответе API. parent_id отдаём как есть — фронт по нему
      строит дерево из плоского списка."""
      id: int
      owner_id: int
      name: str
      kind: CategoryKind
      parent_id: int | None
      created_at: datetime
      updated_at: datetime
  
      model_config = ConfigDict(from_attributes=True)