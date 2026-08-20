import type { ActiveFilter, FilterCondition, FilterDef } from '../types'

export function activeFiltersToConditions(active: ActiveFilter[]): FilterCondition[] {
  const conditions: FilterCondition[] = []

  for (const { def, value } of active) {
    if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
      continue
    }

    switch (def.type) {
      case 'multi_select':
        conditions.push({ field: def.field, operator: 'in', value })
        break
      case 'single_select':
        conditions.push({ field: def.field, operator: 'eq', value })
        break
      case 'search':
        conditions.push({ field: def.field, operator: 'contains', value })
        break
      case 'boolean':
        conditions.push({
          field: def.field,
          operator: value ? 'is_true' : 'is_false',
        })
        break
      case 'range': {
        const range = value as { min?: number | null; max?: number | null }
        if (range.min != null) {
          conditions.push({ field: def.field, operator: 'gte', value: Number(range.min) })
        }
        if (range.max != null) {
          conditions.push({ field: def.field, operator: 'lte', value: Number(range.max) })
        }
        break
      }
    }
  }

  return conditions
}

export function getDependentFilters(filters: FilterDef[], active: ActiveFilter[]): FilterDef[] {
  const activeIds = new Set(active.map((a) => a.def.id))
  return filters.filter((f) => f.depends_on.every((dep) => activeIds.has(dep) || dep === f.id))
}

export function isFilterEnabled(filter: FilterDef, active: ActiveFilter[]): boolean {
  if (filter.depends_on.length === 0) return true
  return filter.depends_on.every((depId) => {
    const parent = active.find((a) => a.def.id === depId)
    if (!parent) return false
    const v = parent.value
    return v != null && v !== '' && !(Array.isArray(v) && v.length === 0)
  })
}

function collectDependents(filterId: string, all: FilterDef[]): string[] {
  const direct = all.filter((f) => f.depends_on.includes(filterId)).map((f) => f.id)
  return [...direct, ...direct.flatMap((id) => collectDependents(id, all))]
}

export function clearFilterCascade(
  active: ActiveFilter[],
  filterId: string,
  allDefs: FilterDef[],
): ActiveFilter[] {
  const remove = new Set([filterId, ...collectDependents(filterId, allDefs)])
  return active.filter((f) => !remove.has(f.def.id))
}

// Columns that are codes or identifiers, not quantities — a season or a
// down should never render with a thousands separator ("2,025").
const NO_GROUPING_CATEGORIES = new Set(['identity', 'time', 'meta'])
const NO_GROUPING_COLUMNS = new Set(['down', 'qtr', 'game_seconds_remaining'])

export function formatCell(value: unknown, columnId?: string, category?: string): string {
  if (value == null) return '—'
  if (typeof value === 'number') {
    const plain = (category && NO_GROUPING_CATEGORIES.has(category)) || (columnId && NO_GROUPING_COLUMNS.has(columnId))
    if (Number.isInteger(value)) return plain ? String(value) : value.toLocaleString()
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

/** True once a value is meaningful enough to keep as an active filter. */
export function hasValue(def: FilterDef, value: unknown): boolean {
  if (value == null || value === '') return false
  if (Array.isArray(value)) return value.length > 0
  if (def.type === 'range') {
    const r = value as { min?: number | null; max?: number | null }
    return r.min != null || r.max != null
  }
  return true
}

/** Compact "Label: value" text for a chip. */
export function formatFilterValue(def: FilterDef, value: unknown): string {
  if (def.type === 'range') {
    const r = value as { min?: number | null; max?: number | null }
    if (r.min != null && r.max != null) return `${r.min}–${r.max}`
    if (r.min != null) return `≥ ${r.min}`
    if (r.max != null) return `≤ ${r.max}`
    return ''
  }
  if (def.type === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) {
    if (value.length <= 3) return value.map(String).join(', ')
    return `${value.slice(0, 2).map(String).join(', ')} +${value.length - 2}`
  }
  return String(value)
}
