import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { fetchFilterOptions } from '../../api/datasets'
import { activeFiltersToConditions } from '../../lib/filters'
import type { ActiveFilter, FilterDef } from '../../types'

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
    const next = (data?.options ?? []).filter((o: unknown) => set.has(String(o)))
    onChange(next)
  }

  return (
    <div className="space-y-2">
      <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
        {(data?.options ?? []).map((option: unknown) => {
          const active = selected.some((s) => String(s) === String(option))
          return (
            <button
              key={String(option)}
              type="button"
              onClick={() => toggle(option)}
              className={`motion-state rounded border px-2 py-0.5 text-[12px] ${
                active ? 'border-line-strong text-ink' : 'border-line text-ink-3 hover:text-ink'
              }`}
            >
              {String(option)}
            </button>
          )
        })}
        {isLoading ? <span className="text-[12px] text-ink-3">Loading…</span> : null}
        {!isLoading && data?.options.length === 0 ? (
          <span className="text-[12px] text-ink-3">No values are left once the other conditions apply.</span>
        ) : null}
      </div>
      {selected.length > 0 ? (
        <button type="button" onClick={() => onChange([])} className="motion-state text-[11px] text-ink-3 hover:text-ink">
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
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-3" />
        <input
          autoFocus
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Search ${def.label.toLowerCase()}…`}
          className="w-full rounded-md border border-line bg-page py-1.5 pl-9 pr-3 text-[13px] outline-none focus:border-line-strong"
        />
      </div>
      {data?.options?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {data.options.slice(0, 8).map((option: unknown) => (
            <button
              key={String(option)}
              type="button"
              onClick={() => {
                setSearch(String(option))
                onChange(String(option))
              }}
              className="motion-state rounded border border-line px-2 py-0.5 text-[12px] text-ink-3 hover:text-ink"
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
        <span className="text-[11px] text-ink-3">At least</span>
        <input
          type="number"
          autoFocus
          placeholder="Min"
          value={range.min ?? ''}
          onChange={(e) => onChange({ ...range, min: e.target.value === '' ? null : Number(e.target.value) })}
          className="w-full rounded-md border border-line bg-page px-2 py-1.5 text-[13px] outline-none focus:border-line-strong"
        />
      </label>
      <label className="space-y-1">
        <span className="text-[11px] text-ink-3">At most</span>
        <input
          type="number"
          placeholder="Max"
          value={range.max ?? ''}
          onChange={(e) => onChange({ ...range, max: e.target.value === '' ? null : Number(e.target.value) })}
          className="w-full rounded-md border border-line bg-page px-2 py-1.5 text-[13px] outline-none focus:border-line-strong"
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
        className={`motion-state flex-1 rounded-md border px-3 py-1.5 text-[13px] ${
          value === true ? 'border-line-strong text-ink' : 'border-line text-ink-3 hover:text-ink'
        }`}
      >
        Yes
      </button>
      <button
        type="button"
        onClick={() => onChange(false)}
        className={`motion-state flex-1 rounded-md border px-3 py-1.5 text-[13px] ${
          value === false ? 'border-line-strong text-ink' : 'border-line text-ink-3 hover:text-ink'
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
