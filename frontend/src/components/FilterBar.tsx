import { ChevronLeft, ListFilter, Plus, RotateCcw, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { clearFilterCascade, formatFilterValue, hasValue } from '../lib/filters'
import type { ActiveFilter, FilterDef } from '../types'
import { FILTER_CATEGORIES } from '../types'
import { FilterValueEditor } from './FilterEditor'
import { HelpHint } from './HelpHint'

export interface QuickSuggestion {
  label: string
  filters: { defId: string; value: unknown }[]
}

interface FilterBarProps {
  datasetId: string
  allDefs: FilterDef[]
  activeFilters: ActiveFilter[]
  onChange: (next: ActiveFilter[]) => void
  quickSuggestions?: QuickSuggestion[]
}

/**
 * Every active filter is a chip, always visible above the table — not
 * hidden inside a panel you have to open to see what's currently applied.
 * "+ Add filter" searches every filterable field on the dataset (not just a
 * hand-picked few); clicking a chip re-opens the same editor to adjust it.
 */
export function FilterBar({ datasetId, allDefs, activeFilters, onChange, quickSuggestions }: FilterBarProps) {
  const [addOpen, setAddOpen] = useState(false)
  const [editingDefId, setEditingDefId] = useState<string | null>(null)

  const setValue = (def: FilterDef, value: unknown) => {
    const without = activeFilters.filter((f) => f.def.id !== def.id)
    if (!hasValue(def, value)) {
      onChange(clearFilterCascade(without, def.id, allDefs))
      return
    }
    onChange([...without, { def, value }])
  }

  const removeFilter = (def: FilterDef) => {
    onChange(clearFilterCascade(activeFilters.filter((f) => f.def.id !== def.id), def.id, allDefs))
  }

  const applySuggestion = (s: QuickSuggestion) => {
    let next = activeFilters
    for (const { defId, value } of s.filters) {
      const def = allDefs.find((d) => d.id === defId)
      if (!def) continue
      next = next.filter((f) => f.def.id !== def.id)
      if (hasValue(def, value)) next = [...next, { def, value }]
    }
    onChange(next)
  }

  const activeIds = new Set(activeFilters.map((f) => f.def.id))
  const availableSuggestions = (quickSuggestions ?? []).filter(
    (s) => !s.filters.every((f) => activeIds.has(f.defId)),
  )

  // Some active filters (season/week) are managed by a dedicated control
  // elsewhere on the page rather than this bar — allDefs is the source of
  // truth for what this bar owns, so only show a chip for those.
  const managedIds = new Set(allDefs.map((d) => d.id))
  const chipFilters = activeFilters.filter((f) => managedIds.has(f.def.id))

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chipFilters.map((f) => (
        <FilterChip
          key={f.def.id}
          datasetId={datasetId}
          activeFilter={f}
          activeFilters={activeFilters}
          open={editingDefId === f.def.id}
          onOpen={() => setEditingDefId(f.def.id)}
          onClose={() => setEditingDefId(null)}
          onApply={(value) => {
            setValue(f.def, value)
            setEditingDefId(null)
          }}
          onRemove={() => removeFilter(f.def)}
        />
      ))}

      <AddFilterControl
        datasetId={datasetId}
        allDefs={allDefs}
        activeFilters={activeFilters}
        open={addOpen}
        onOpenChange={setAddOpen}
        onAdd={(def, value) => {
          setValue(def, value)
          setAddOpen(false)
        }}
      />

      {availableSuggestions.length > 0 ? (
        <>
          <div className="mx-1 h-4 w-px bg-white/10" />
          {availableSuggestions.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => applySuggestion(s)}
              className="rounded-full border border-dashed border-white/15 px-3 py-1.5 text-xs font-medium text-slate-400 light:text-slate-500 transition hover:border-blue-400/40 hover:text-blue-200"
            >
              + {s.label}
            </button>
          ))}
        </>
      ) : null}

      {chipFilters.length > 0 ? (
        <button
          type="button"
          onClick={() => onChange(activeFilters.filter((f) => !managedIds.has(f.def.id)))}
          className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-slate-500 transition hover:text-white"
        >
          <RotateCcw className="h-3 w-3" />
          Clear all
        </button>
      ) : null}
    </div>
  )
}

function FilterChip({
  datasetId,
  activeFilter,
  activeFilters,
  open,
  onOpen,
  onClose,
  onApply,
  onRemove,
}: {
  datasetId: string
  activeFilter: ActiveFilter
  activeFilters: ActiveFilter[]
  open: boolean
  onOpen: () => void
  onClose: () => void
  onApply: (value: unknown) => void
  onRemove: () => void
}) {
  const { def, value } = activeFilter
  const [draft, setDraft] = useState(value)

  return (
    <div className="relative">
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/15 py-1 pl-3 pr-1.5 text-xs font-medium text-blue-100 light:text-blue-700 ring-1 ring-blue-400/30">
        <button
          type="button"
          onClick={() => {
            setDraft(value)
            if (open) onClose()
            else onOpen()
          }}
          className="hover:text-white"
        >
          {def.label}: {formatFilterValue(def, value)}
        </button>
        <button
          type="button"
          onClick={onRemove}
          className="rounded-full p-0.5 text-blue-300 light:text-blue-600 hover:bg-white/10 hover:text-white"
          aria-label={`Remove ${def.label} filter`}
        >
          <X className="h-3 w-3" />
        </button>
      </span>

      {open ? (
        <>
          <button type="button" className="fixed inset-0 z-40" aria-label="Close" onClick={onClose} />
          <div className="absolute left-0 z-50 mt-2 w-72 rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/95 light:bg-white/95 p-3 shadow-2xl backdrop-blur-xl">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium text-slate-200 light:text-slate-700">{def.label}</p>
              {def.description ? <HelpHint text={def.description} /> : null}
            </div>
            <FilterValueEditor
              datasetId={datasetId}
              def={def}
              value={draft}
              siblingFilters={activeFilters.filter((f) => f.def.id !== def.id)}
              onChange={setDraft}
            />
            <button
              type="button"
              onClick={() => onApply(draft)}
              className="mt-3 w-full rounded-lg bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40 hover:bg-blue-500/30"
            >
              Apply
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}

function AddFilterControl({
  datasetId,
  allDefs,
  activeFilters,
  open,
  onOpenChange,
  onAdd,
}: {
  datasetId: string
  allDefs: FilterDef[]
  activeFilters: ActiveFilter[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onAdd: (def: FilterDef, value: unknown) => void
}) {
  const [search, setSearch] = useState('')
  const [pickedDef, setPickedDef] = useState<FilterDef | null>(null)
  const [draft, setDraft] = useState<unknown>(null)

  const activeIds = new Set(activeFilters.map((f) => f.def.id))
  const pickable = allDefs.filter((d) => !activeIds.has(d.id))

  const grouped = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = q ? pickable.filter((d) => d.label.toLowerCase().includes(q)) : pickable
    const map = new Map<string, FilterDef[]>()
    for (const d of filtered) {
      if (!map.has(d.category)) map.set(d.category, [])
      map.get(d.category)!.push(d)
    }
    return Array.from(map.entries()).sort(([a], [b]) => (FILTER_CATEGORIES[a] ?? a).localeCompare(FILTER_CATEGORIES[b] ?? b))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickable, search])

  const close = () => {
    onOpenChange(false)
    setSearch('')
    setPickedDef(null)
    setDraft(null)
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => (open ? close() : onOpenChange(true))}
        className="inline-flex items-center gap-1 rounded-full border border-dashed border-white/20 light:border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-300 light:text-slate-600 transition hover:border-blue-400/40 hover:text-blue-200"
      >
        <Plus className="h-3.5 w-3.5" />
        Add filter
      </button>

      {open ? (
        <>
          <button type="button" className="fixed inset-0 z-40" aria-label="Close" onClick={close} />
          <div className="absolute left-0 z-50 mt-2 w-80 max-h-[26rem] overflow-y-auto rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/95 light:bg-white/95 p-3 shadow-2xl backdrop-blur-xl">
            {!pickedDef ? (
              <>
                <div className="relative mb-3">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                  <input
                    autoFocus
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search filters…"
                    className="w-full rounded-lg border border-white/10 light:border-slate-200 bg-slate-950/60 light:bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-100 light:text-slate-800 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                {grouped.length === 0 ? (
                  <p className="flex items-center gap-2 px-1 py-6 text-center text-sm text-slate-500">
                    <ListFilter className="h-4 w-4" />
                    No matching filters
                  </p>
                ) : (
                  <div className="space-y-3">
                    {grouped.map(([category, defs]) => (
                      <div key={category}>
                        <p className="mb-1 text-[11px] font-medium uppercase text-slate-500">
                          {FILTER_CATEGORIES[category] ?? category}
                        </p>
                        <div className="space-y-0.5">
                          {defs.map((d) => (
                            <button
                              key={d.id}
                              type="button"
                              onClick={() => {
                                setPickedDef(d)
                                setDraft(d.type === 'multi_select' || d.type === 'single_select' ? [] : null)
                              }}
                              className="block w-full rounded-lg px-2 py-1.5 text-left text-sm text-slate-200 light:text-slate-700 hover:bg-white/5"
                            >
                              {d.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="mb-3 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setPickedDef(null)}
                    className="rounded p-1 text-slate-400 light:text-slate-500 hover:bg-white/5 hover:text-white"
                    aria-label="Back"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <p className="text-sm font-medium text-slate-200 light:text-slate-700">{pickedDef.label}</p>
                </div>
                {pickedDef.description ? (
                  <p className="mb-2 text-[11px] leading-snug text-slate-500">{pickedDef.description}</p>
                ) : null}
                <FilterValueEditor
                  datasetId={datasetId}
                  def={pickedDef}
                  value={draft}
                  siblingFilters={activeFilters}
                  onChange={setDraft}
                />
                <button
                  type="button"
                  disabled={!hasValue(pickedDef, draft)}
                  onClick={() => {
                    onAdd(pickedDef, draft)
                    close()
                  }}
                  className="mt-3 w-full rounded-lg bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40 hover:bg-blue-500/30 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Add filter
                </button>
              </>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}
