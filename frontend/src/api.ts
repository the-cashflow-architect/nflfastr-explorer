import type {
  DatasetSchema,
  DatasetSummary,
  FilterCondition,
  FilterOptionsResponse,
  QueryResponse,
  SortSpec,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  return res.blob()
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

export function checkHealth() {
  return request<{ status: string }>('/api/health')
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
  },
) {
  return requestBlob(`/api/datasets/${datasetId}/export`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
