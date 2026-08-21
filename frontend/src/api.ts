import type {
  DatasetSchema,
  DatasetSummary,
  FilterCondition,
  FilterOptionsResponse,
  QueryResponse,
  SortSpec,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = API_BASE_URL ? `${API_BASE_URL}${path}` : path
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export interface BlobResult {
  blob: Blob
  /** Rows actually written, once the server cap was applied. */
  rows: number | null
  /** Rows the filters matched, before the cap. */
  matchingRows: number | null
  truncated: boolean
}

async function requestBlob(path: string, init?: RequestInit): Promise<BlobResult> {
  const url = API_BASE_URL ? `${API_BASE_URL}${path}` : path
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  const num = (name: string) => {
    const raw = res.headers.get(name)
    const parsed = raw == null ? NaN : Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return {
    blob: await res.blob(),
    rows: num('X-Export-Rows'),
    matchingRows: num('X-Export-Matching-Rows'),
    truncated: res.headers.get('X-Export-Truncated') === 'true',
  }
}

export function fetchDatasets() {
  return request<DatasetSummary[]>('/api/datasets')
}

export function fetchSchema(datasetId: string) {
  return request<DatasetSchema>(`/api/datasets/${datasetId}/schema`)
}

export function queryDataset(
  datasetId: string,
  body: {
    filters: FilterCondition[]
    sort: SortSpec[]
    page: number
    page_size: number
    columns?: string[]
  },
) {
  return request<QueryResponse>(`/api/datasets/${datasetId}/query`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchFilterOptions(
  datasetId: string,
  body: {
    field: string
    filters: FilterCondition[]
    search?: string
    limit?: number
  },
) {
  return request<FilterOptionsResponse>(`/api/datasets/${datasetId}/filter-options`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export interface RankingsResponse {
  rows: Record<string, unknown>[]
  total: number
  page: number
  page_size: number
  columns: string[]
}

export function fetchRankings(
  datasetId: string,
  body: {
    filters: FilterCondition[]
    columns?: string[]
    sort: SortSpec[]
    page: number
    page_size: number
    rank_fields: string[]
    qualify_field?: string | null
    qualify_min?: number | null
  },
) {
  return request<RankingsResponse>(`/api/datasets/${datasetId}/rankings`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function checkHealth() {
  return request<{ status: string }>('/api/health')
}

export interface WeeklyBreakdownResponse {
  rows: Record<string, unknown>[]
  weeks: number[]
  total: number
  page: number
  page_size: number
}

export function fetchWeeklyBreakdown(
  datasetId: string,
  body: {
    filters: FilterCondition[]
    group_columns: string[]
    weekly_field: string
    agg_columns: string[]
    sort: SortSpec[]
    page: number
    page_size: number
  },
) {
  return request<WeeklyBreakdownResponse>(`/api/datasets/${datasetId}/weekly-breakdown`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function fetchDataQuality(
  datasetId: string,
  body: {
    filters: FilterCondition[]
  },
) {
  return request<{
    total_rows: number
    filtered_rows: number
    columns: { id: string; label: string; null_pct: number; category: string }[]
  }>(`/api/datasets/${datasetId}/data-quality`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function exportDataset(
  datasetId: string,
  body: {
    filters: FilterCondition[]
    sort: SortSpec[]
    columns?: string[]
    format?: 'csv' | 'json'
    max_rows?: number
  },
) {
  return requestBlob(`/api/datasets/${datasetId}/export`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
