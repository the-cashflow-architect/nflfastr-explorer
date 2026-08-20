import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { fetchFilterOptions } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import type { ActiveFilter, FilterDef } from '../types'

interface EditorProps {
  datasetId: string
  def: FilterDef
  value: unknown
  siblingFilters: ActiveFilter[]
  onChange: (value: unknown) => void
}

export function MultiSelectEditor({ datasetId, def, value, siblingFilters, onChange }: EditorProps) {
  const selected = (value as unknown[]) ?? []
  const conditions = activeFiltersToConditions(siblingFilters)

  const { data, isLoading } = useQuery({
    queryKey: ['filter-options', datasetId, def.field, conditions],
    queryFn: () => fetchFilterOptions(datasetId, { field: def.field, filters: conditions, limit: 300 }),
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
    <div className="space-y-2">
      <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
        {(data?.options ?? []).map((option) => {
          const active = selected.some((s) => String(s) === String(option))
          return (
            <button
              key={String(option)}
              type="button"
              onClick={() => toggle(option)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-all ${
                active
                  ? 'bg-blue-500/20 text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40'
                  : 'bg-slate-800/80 light:bg-slate-100 text-slate-300 light:text-slate-600 ring-1 ring-white/5 light:ring-slate-200 hover:bg-slate-700/80'
              }`}
            >
              {String(option)}
            </button>
          )
        })}
        {isLoading ? <span className="text-xs text-slate-500">Loading…</span> : null}
        {!isLoading && data?.options.length === 0 ? (
          <span className="text-xs text-slate-500">No options for the current filters.</span>
        ) : null}
      </div>
      {selected.length > 0 ? (
        <button type="button" onClick={() => onChange([])} className="text-[11px] text-slate-500 hover:text-slate-300">
          Clear {selected.length} selected
        </button>
      ) : null}
    </div>
  )
}

export function SearchEditor({ datasetId, def, value, siblingFilters, onChange }: EditorProps) {
  const [search, setSearch] = useState(String(value ?? ''))
  const conditions = activeFiltersToConditions(siblingFilters)

  useEffect(() => {
    const timer = setTimeout(() => onChange(search || null), 300)
    return () => clearTimeout(timer)
  }, [search, onChange])

  const { data } = useQuery({
    queryKey: ['filter-options', datasetId, def.field, conditions, search],
    queryFn: () =>
      fetchFilterOptions(datasetId, { field: def.field, filters: conditions, search: search || undefined, limit: 12 }),
    enabled: search.length >= 2,
  })

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
        <input
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${def.label.toLowerCase()}…`}
          className="w-full rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/70 light:bg-white py-2 pl-9 pr-3 text-sm text-slate-100 light:text-slate-800 outline-none ring-blue-500/0 transition focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
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
              className="rounded-md bg-slate-800/80 light:bg-slate-100 px-2 py-1 text-xs text-slate-300 light:text-slate-600 hover:bg-slate-700"
            >
              {String(option)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function RangeEditor({ value, onChange }: Omit<EditorProps, 'datasetId' | 'siblingFilters' | 'def'>) {
  const range = (value as { min?: number | null; max?: number | null }) ?? {}

  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="space-y-1">
        <span className="text-[11px] text-slate-500">At least</span>
        <input
          type="number"
          autoFocus
          placeholder="Min"
          value={range.min ?? ''}
          onChange={(e) => onChange({ ...range, min: e.target.value === '' ? null : Number(e.target.value) })}
          className="w-full rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/70 light:bg-white px-3 py-2 text-sm outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
        />
      </label>
      <label className="space-y-1">
        <span className="text-[11px] text-slate-500">At most</span>
        <input
          type="number"
          placeholder="Max"
          value={range.max ?? ''}
          onChange={(e) => onChange({ ...range, max: e.target.value === '' ? null : Number(e.target.value) })}
          className="w-full rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/70 light:bg-white px-3 py-2 text-sm outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
        />
      </label>
    </div>
  )
}

export function BooleanEditor({ value, onChange }: Omit<EditorProps, 'datasetId' | 'siblingFilters' | 'def'>) {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onChange(true)}
        className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
          value === true ? 'bg-emerald-500/20 text-emerald-200 light:text-emerald-700 ring-1 ring-emerald-400/40' : 'bg-slate-800/80 light:bg-slate-100 text-slate-300 light:text-slate-600 ring-1 ring-white/5 light:ring-slate-200 hover:bg-slate-700/80'
        }`}
      >
        Yes
      </button>
      <button
        type="button"
        onClick={() => onChange(false)}
        className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
          value === false ? 'bg-red-500/20 text-red-200 ring-1 ring-red-400/40' : 'bg-slate-800/80 light:bg-slate-100 text-slate-300 light:text-slate-600 ring-1 ring-white/5 light:ring-slate-200 hover:bg-slate-700/80'
        }`}
      >
        No
      </button>
    </div>
  )
}

export function FilterValueEditor({ datasetId, def, value, siblingFilters, onChange }: EditorProps) {
  if (def.type === 'multi_select' || def.type === 'single_select') {
    return <MultiSelectEditor datasetId={datasetId} def={def} value={value} siblingFilters={siblingFilters} onChange={onChange} />
  }
  if (def.type === 'search') {
    return <SearchEditor datasetId={datasetId} def={def} value={value} siblingFilters={siblingFilters} onChange={onChange} />
  }
  if (def.type === 'range') {
    return <RangeEditor value={value} onChange={onChange} />
  }
  if (def.type === 'boolean') {
    return <BooleanEditor value={value} onChange={onChange} />
  }
  return null
}
