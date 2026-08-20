export type FilterOperator =
  | 'eq'
  | 'neq'
  | 'in'
  | 'not_in'
  | 'gte'
  | 'lte'
  | 'between'
  | 'contains'
  | 'is_true'
  | 'is_false'

export interface FilterCondition {
  field: string
  operator: FilterOperator
  value?: unknown
}

export interface SortSpec {
  field: string
  direction: 'asc' | 'desc'
}

export interface ColumnMeta {
  id: string
  label: string
  description: string
  formula?: string | null
  dtype: string
  category: string
}

export interface FilterDef {
  id: string
  field: string
  label: string
  type: 'multi_select' | 'single_select' | 'range' | 'boolean' | 'search'
  category: string
  depends_on: string[]
  description?: string | null
}

export interface DatasetSummary {
  id: string
  name: string
  description: string
  source: string
  // Null until the backend has finished loading that dataset.
  row_count: number | null
  loaded?: boolean
}

export interface DatasetSchema extends DatasetSummary {
  columns: ColumnMeta[]
  filters: FilterDef[]
  default_columns: string[]
  default_sort: SortSpec[]
}

export interface QueryResponse {
  rows: Record<string, unknown>[]
  total: number
  page: number
  page_size: number
  columns: string[]
}

export interface FilterOptionsResponse {
  field: string
  options: unknown[]
  total: number
}

export interface ActiveFilter {
  def: FilterDef
  value: unknown
}

export const FILTER_CATEGORIES: Record<string, string> = {
  time: 'Time',
  team: 'Team',
  identity: 'Player',
  situation: 'Situation',
  play: 'Play Result',
  passing: 'Passing',
  rushing: 'Rushing',
  receiving: 'Receiving',
  defense: 'Defense',
  kicking: 'Kicking',
  punting: 'Punting',
  returns: 'Returns',
  penalties: 'Penalties',
  ball_security: 'Fumbles',
  advanced: 'Advanced',
  fantasy: 'Fantasy',
  other: 'Other',
  // Not a stat — excluded from every column/filter picker. Kept here only
  // so an unexpected value never renders as a raw category key.
  meta: 'Meta',
}

/** Columns in these categories are never offered in a picker — they're
 * identity metadata (a portrait URL) or encoded in a shape a flat table
 * can't render (delimited lists), not stats to browse or chart. */
export const HIDDEN_CATEGORIES = new Set(['meta'])
