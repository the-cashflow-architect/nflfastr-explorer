import { Columns3 } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ColumnMeta } from '../types'

interface ColumnPickerProps {
  allColumns: ColumnMeta[]
  selected: string[]
  onChange: (columns: string[]) => void
}

export function ColumnPicker({ allColumns, selected, onChange }: ColumnPickerProps) {
  const [open, setOpen] = useState(false)

  const grouped = useMemo(() => {
    const map = new Map<string, ColumnMeta[]>()
    for (const col of allColumns) {
      if (!map.has(col.category)) map.set(col.category, [])
      map.get(col.category)!.push(col)
    }
    return Array.from(map.entries())
  }, [allColumns])

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
        onClick={() => setOpen((o) => !o)}
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
          <div className="absolute right-0 z-50 mt-2 w-80 max-h-96 overflow-y-auto rounded-2xl border border-white/10 bg-slate-900/95 p-3 shadow-2xl backdrop-blur-xl">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Visible columns
            </p>
            <div className="space-y-3">
              {grouped.map(([category, cols]) => (
                <div key={category}>
                   <p className="mb-1 text-[11px] font-medium uppercase text-slate-500">
                      {category.charAt(0).toUpperCase() + category.slice(1)}
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
          </div>
        </>
      ) : null}
    </div>
  )
}
