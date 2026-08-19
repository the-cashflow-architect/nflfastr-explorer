from __future__ import annotations

import re
from typing import Any

from .models import FilterCondition, FilterOperator, SortSpec

IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_identifier(name: str) -> str:
    if not IDENTIFIER.match(name):
        raise ValueError(f"Invalid column name: {name}")
    return f'"{name}"'


def build_where(filters: list[FilterCondition]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    for f in filters:
        col = _quote_identifier(f.field)
        op = f.operator

        if op == FilterOperator.eq:
            clauses.append(f"{col} = ?")
            params.append(f.value)
        elif op == FilterOperator.neq:
            clauses.append(f"{col} <> ?")
            params.append(f.value)
        elif op == FilterOperator.in_:
            values = list(f.value or [])
            if not values:
                clauses.append("1 = 0")
                continue
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(values)
        elif op == FilterOperator.not_in:
            values = list(f.value or [])
            if not values:
                continue
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{col} NOT IN ({placeholders})")
            params.extend(values)
        elif op == FilterOperator.gte:
            clauses.append(f"{col} >= ?")
            params.append(f.value)
        elif op == FilterOperator.lte:
            clauses.append(f"{col} <= ?")
            params.append(f.value)
        elif op == FilterOperator.between:
            low, high = f.value
            clauses.append(f"{col} BETWEEN ? AND ?")
            params.extend([low, high])
        elif op == FilterOperator.contains:
            clauses.append(f"CAST({col} AS VARCHAR) ILIKE ?")
            params.append(f"%{f.value}%")
        elif op == FilterOperator.is_true:
            clauses.append(f"{col} = TRUE")
        elif op == FilterOperator.is_false:
            clauses.append(f"({col} = FALSE OR {col} IS NULL)")

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def build_order(sort: list[SortSpec]) -> str:
    if not sort:
        return ""
    parts = []
    for s in sort:
        col = _quote_identifier(s.field)
        direction = "ASC" if s.direction == "asc" else "DESC"
        parts.append(f"{col} {direction}")
    return " ORDER BY " + ", ".join(parts)


def build_select_columns(columns: list[str] | None, available: list[str]) -> str:
    if not columns:
        return "*"
    safe = [_quote_identifier(c) for c in columns if c in available]
    if not safe:
        return "*"
    return ", ".join(safe)


def build_null_count_sql(table: str, columns: list[str], where_sql: str) -> str:
    """One scan that yields the row count plus a non-null count per column.

    COUNT(col) skips NULLs, so nulls are COUNT(*) - COUNT(col). Results are
    read positionally, which sidesteps alias-quoting entirely. The previous
    implementation issued a separate `WHERE col IS NULL` count per column —
    100+ full scans for a single request on the player tables.
    """
    projections = ", ".join(f"COUNT({_quote_identifier(c)})" for c in columns)
    head = "SELECT COUNT(*)" + (f", {projections}" if projections else "")
    return f"{head} FROM {table}{where_sql}"
