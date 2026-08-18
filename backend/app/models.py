from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class FilterOperator(str, Enum):
    eq = "eq"
    neq = "neq"
    in_ = "in"
    not_in = "not_in"
    gte = "gte"
    lte = "lte"
    between = "between"
    contains = "contains"
    is_true = "is_true"
    is_false = "is_false"


class FilterCondition(BaseModel):
    field: str
    operator: FilterOperator
    value: Any = None


class SortSpec(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class QueryRequest(BaseModel):
    filters: list[FilterCondition] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    columns: list[str] | None = None


class FilterOptionsRequest(BaseModel):
    field: str
    filters: list[FilterCondition] = Field(default_factory=list)
    search: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)


class ColumnMeta(BaseModel):
    id: str
    label: str
    description: str
    formula: str | None = None
    dtype: str
    category: str


class FilterDef(BaseModel):
    id: str
    field: str
    label: str
    type: Literal["multi_select", "single_select", "range", "boolean", "search"]
    category: str
    depends_on: list[str] = Field(default_factory=list)
    description: str | None = None


class DatasetMeta(BaseModel):
    id: str
    name: str
    description: str
    source: str
    row_count: int
    columns: list[ColumnMeta]
    filters: list[FilterDef]
    default_columns: list[str]
    default_sort: list[SortSpec]


class QueryResponse(BaseModel):
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    columns: list[str]


class FilterOptionsResponse(BaseModel):
    field: str
    options: list[Any]
    total: int
