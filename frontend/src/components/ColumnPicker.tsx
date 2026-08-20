import { Columns3, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { ColumnMeta } from '../types'
import { FILTER_CATEGORIES, HIDDEN_CATEGORIES } from '../types'

interface ColumnPickerProps {
  allColumns: ColumnMeta[]
  selected: string[]
  onChange: (columns: string[]) => void
  /** When set, the picker opens/closes in lockstep with this instead of managing its own state. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export function ColumnPicker({ allColumns, selected, onChange, open: openProp, onOpenChange }: ColumnPickerProps) {
  const [openState, setOpenState] = useState(false)
  const open = openProp ?? openState
  const setOpen = (next: boolean) => {
    setOpenState(next)
    onOpenChange?.(next)
  }
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!open) setSearch('')
  }, [open])

  const pickable = useMemo(
    () => allColumns.filter((c) => !HIDDEN_CATEGORIES.has(c.category)),
    [allColumns],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return pickable
    return pickable.filter(
      (c) => c.label.toLowerCase().includes(q) || c.description.toLowerCase().includes(q),
    )
  }, [pickable, search])

  const grouped = useMemo(() => {
    const map = new Map<string, ColumnMeta[]>()
    for (const col of filtered) {
      if (!map.has(col.category)) map.set(col.category, [])
      map.get(col.category)!.push(col)
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      (FILTER_CATEGORIES[a] ?? a).localeCompare(FILTER_CATEGORIES[b] ?? b),
    )
  }, [filtered])

  const toggle = (id: string) => {
    if (selected.includes(id)) {
      if (selected.length <= 3) return
      onChange(selected.filter((c) => c !== id))
    } else {
      onChange([...selected, id])
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/80"
      >
        <Columns3 className="h-4 w-4" />
        Columns ({selected.length})
      </button>
      {open ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40"
            aria-label="Close column picker"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 z-50 mt-2 w-96 max-h-[28rem] overflow-y-auto rounded-2xl border border-white/10 bg-slate-900/95 p-3 shadow-2xl backdrop-blur-xl">
            <div className="relative mb-3">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
              <input
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search stats…"
                className="w-full rounded-lg border border-white/10 bg-slate-950/60 py-2 pl-9 pr-3 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
            {grouped.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-slate-500">No stats match "{search}"</p>
            ) : (
              <div className="space-y-3">
                {grouped.map(([category, cols]) => (
                  <div key={category}>
                    <p className="mb-1 text-[11px] font-medium uppercase text-slate-500">
                      {FILTER_CATEGORIES[category] ?? category}
                    </p>
                    <div className="space-y-1">
                      {cols.map((col) => (
                        <label
                          key={col.id}
                          className="flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5"
                        >
                          <input
                            type="checkbox"
                            checked={selected.includes(col.id)}
                            onChange={() => toggle(col.id)}
                            className="mt-0.5"
                          />
                          <span>
                            <span className="block text-sm text-slate-200">{col.label}</span>
                            <span className="block text-[11px] text-slate-500 line-clamp-1">
                              {col.description}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}
