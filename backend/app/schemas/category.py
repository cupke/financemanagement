"""Pydantic-схемы категории для запросов и ответов API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
      """Тело запроса POST /categories."""
      name: str = Field(..., min_length=1, max_length=100)
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
      """
      name: str | None = Field(default=None, min_length=1, max_length=100)
      parent_id: int | None = None


class CategoryRead(BaseModel):
      """Что отдаём в ответе API. parent_id отдаём как есть — фронт по нему
      строит дерево из плоского списка."""
      id: int
      owner_id: int
      name: str
      parent_id: int | None
      created_at: datetime
      updated_at: datetime

      model_config = ConfigDict(from_attributes=True)