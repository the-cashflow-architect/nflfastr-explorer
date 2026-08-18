import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, RotateCcw, Search, X } from 'lucide-react'
import { fetchFilterOptions } from '../api'
import { activeFiltersToConditions, clearFilterCascade, isFilterEnabled } from '../lib/filters'
import type { ActiveFilter, FilterDef } from '../types'
import { FILTER_CATEGORIES } from '../types'

interface FilterPanelProps {
  datasetId: string
  filterDefs: FilterDef[]
  activeFilters: ActiveFilter[]
  onChange: (filters: ActiveFilter[]) => void
}

function getActiveValue(activeFilters: ActiveFilter[], id: string): unknown {
  return activeFilters.find((f) => f.def.id === id)?.value
}

function setActiveValue(
  activeFilters: ActiveFilter[],
  def: FilterDef,
  value: unknown,
  allDefs: FilterDef[],
): ActiveFilter[] {
  const without = activeFilters.filter((f) => f.def.id !== def.id)
  if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
    return clearFilterCascade(without, def.id, allDefs)
  }
  return [...without, { def, value }]
}

function MultiSelectFilter({
  datasetId,
  def,
  value,
  siblingFilters,
  disabled,
  onChange,
}: {
  datasetId: string
  def: FilterDef
  value: unknown
  siblingFilters: ActiveFilter[]
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  const selected = (value as unknown[]) ?? []
  const conditions = activeFiltersToConditions(siblingFilters)

  const { data, isLoading } = useQuery({
    queryKey: ['filter-options', datasetId, def.field, conditions],
    queryFn: () => fetchFilterOptions(datasetId, { field: def.field, filters: conditions, limit: 300 }),
    enabled: !disabled,
  })

  const toggle = (option: unknown) => {
    const set = new Set(selected.map(String))
    const key = String(option)
    if (set.has(key)) set.delete(key)
    else set.add(key)
    const next = (data?.options ?? []).filter((o) => set.has(String(o)))
    onChange(next)
  }

  return (
    <div className={`space-y-2 ${disabled ? 'opacity-40 pointer-events-none' : ''}`}>
      <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
        {(data?.options ?? []).map((option) => {
          const active = selected.some((s) => String(s) === String(option))
          return (
            <button
              key={String(option)}
              type="button"
              onClick={() => toggle(option)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-all ${
                active
                  ? 'bg-blue-500/20 text-blue-200 ring-1 ring-blue-400/40'
                  : 'bg-slate-800/80 text-slate-300 ring-1 ring-white/5 hover:bg-slate-700/80'
              }`}
            >
              {String(option)}
            </button>
          )
        })}
        {isLoading ? <span className="text-xs text-slate-500">Loading…</span> : null}
      </div>
      {selected.length > 0 ? (
        <button
          type="button"
          onClick={() => onChange([])}
          className="text-[11px] text-slate-500 hover:text-slate-300"
        >
          Clear {selected.length} selected
        </button>
      ) : null}
    </div>
  )
}

function SearchFilter({
  datasetId,
  def,
  value,
  siblingFilters,
  disabled,
  onChange,
}: {
  datasetId: string
  def: FilterDef
  value: unknown
  siblingFilters: ActiveFilter[]
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  const [search, setSearch] = useState(String(value ?? ''))
  const conditions = activeFiltersToConditions(siblingFilters)

  useEffect(() => {
    const timer = setTimeout(() => onChange(search || null), 300)
    return () => clearTimeout(timer)
  }, [search, onChange])

  const { data } = useQuery({
    queryKey: ['filter-options', datasetId, def.field, conditions, search],
    queryFn: () =>
      fetchFilterOptions(datasetId, {
        field: def.field,
        filters: conditions,
        search: search || undefined,
        limit: 12,
      }),
    enabled: !disabled && search.length >= 2,
  })

  return (
    <div className={`space-y-2 ${disabled ? 'opacity-40 pointer-events-none' : ''}`}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${def.label.toLowerCase()}…`}
          className="w-full rounded-lg border border-white/10 bg-slate-900/70 py-2 pl-9 pr-3 text-sm text-slate-100 outline-none ring-blue-500/0 transition focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
        />
      </div>
      {data?.options?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {data.options.slice(0, 8).map((option) => (
            <button
              key={String(option)}
              type="button"
              onClick={() => {
                setSearch(String(option))
                onChange(String(option))
              }}
              className="rounded-md bg-slate-800/80 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
            >
              {String(option)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function RangeFilter({
  value,
  disabled,
  onChange,
}: {
  value: unknown
  disabled: boolean
  onChange: (value: unknown) => void
}) {
  const range = (value as { min?: number | null; max?: number | null }) ?? {}

  return (
    <div className={`grid grid-cols-2 gap-2 ${disabled ? 'opacity-40 pointer-events-none' : ''}`}>
      <input
        type="number"
        placeholder="Min"
        value={range.min ?? ''}
        onChange={(e) =>
          onChange({ ...range, min: e.target.value === '' ? null : Number(e.target.value) })
        }
        className="rounded-lg border border-white/10 bg-slate-900/70 px-3 py-2 text-sm outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
      />
      <input
        type="number"
        placeholder="Max"
        value={range.max ?? ''}
        onChange={(e) =>
          onChange({ ...range, max: e.target.value === '' ? null : Number(e.target.value) })
        }
        className="rounded-lg border border-white/10 bg-slate-900/70 px-3 py-2 text-sm outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
      />
    </div>
  )
}

export function FilterPanel({ datasetId, filterDefs, activeFilters, onChange }: FilterPanelProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const grouped = useMemo(() => {
    const map = new Map<string, FilterDef[]>()
    for (const def of filterDefs) {
      const cat = def.category
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(def)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [filterDefs])

  const clearAll = () => onChange([])

  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Filters</h2>
          <p className="text-xs text-slate-400">Options update based on your selections</p>
        </div>
        <button
          type="button"
          onClick={clearAll}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 transition hover:bg-white/5 hover:text-white"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Reset
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {grouped.map(([category, defs]) => {
          const isCollapsed = collapsed[category]
          return (
            <section key={category} className="rounded-xl border border-white/5 bg-slate-950/40">
              <button
                type="button"
                onClick={() => setCollapsed((c) => ({ ...c, [category]: !c[category] }))}
                className="flex w-full items-center justify-between px-3 py-2 text-left"
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {FILTER_CATEGORIES[category] ?? category}
                </span>
                <ChevronDown
                  className={`h-4 w-4 text-slate-500 transition ${isCollapsed ? '-rotate-90' : ''}`}
                />
              </button>
              {!isCollapsed ? (
                <div className="space-y-4 border-t border-white/5 px-3 py-3">
                  {defs.map((def) => {
                    const enabled = isFilterEnabled(def, activeFilters)
                    const siblings = activeFilters.filter((f) => f.def.id !== def.id)
                    const value = getActiveValue(activeFilters, def.id)

                    return (
                      <div key={def.id} className="space-y-1.5">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-medium text-slate-200">{def.label}</p>
                            {def.description ? (
                              <p className="text-[11px] leading-snug text-slate-500">{def.description}</p>
                            ) : null}
                            {!enabled && def.depends_on.length > 0 ? (
                              <p className="text-[10px] text-amber-400/80">
                                Set {def.depends_on.join(', ')} first
                              </p>
                            ) : null}
                          </div>
                          {value != null &&
                          value !== '' &&
                          !(Array.isArray(value) && value.length === 0) ? (
                            <button
                              type="button"
                              onClick={() => onChange(setActiveValue(activeFilters, def, null, filterDefs))}
                              className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          ) : null}
                        </div>

                        {def.type === 'multi_select' || def.type === 'single_select' ? (
                          <MultiSelectFilter
                            datasetId={datasetId}
                            def={def}
                            value={value}
                            siblingFilters={siblings}
                            disabled={!enabled}
                            onChange={(next) => onChange(setActiveValue(activeFilters, def, next, filterDefs))}
                          />
                        ) : null}

                        {def.type === 'search' ? (
                          <SearchFilter
                            datasetId={datasetId}
                            def={def}
                            value={value}
                            siblingFilters={siblings}
                            disabled={!enabled}
                            onChange={(next) => onChange(setActiveValue(activeFilters, def, next, filterDefs))}
                          />
                        ) : null}

                        {def.type === 'range' ? (
                          <RangeFilter
                            value={value}
                            disabled={!enabled}
                            onChange={(next) => onChange(setActiveValue(activeFilters, def, next, filterDefs))}
                          />
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </section>
          )
        })}
      </div>
    </aside>
  )
}
