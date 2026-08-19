import { ArrowUp, ArrowDown, GripVertical, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import type { SortSpec, ColumnMeta } from '../types'

interface SortPanelProps {
  sorting: SortSpec[]
  onSortingChange: (sorting: SortSpec[]) => void
  columns: ColumnMeta[]
}

export function SortPanel({ sorting, onSortingChange, columns }: SortPanelProps) {
  const [showAddSort, setShowAddSort] = useState(false)

  const handleAddSort = (columnId: string) => {
    const existing = sorting.find((s) => s.field === columnId)
    if (existing) return
    onSortingChange([...sorting, { field: columnId, direction: 'desc' }])
    setShowAddSort(false)
  }

  const handleRemoveSort = (index: number) => {
    onSortingChange(sorting.filter((_, i) => i !== index))
  }

  const handleDirectionChange = (index: number, direction: 'asc' | 'desc') => {
    onSortingChange(
      sorting.map((s, i) => (i === index ? { ...s, direction } : s)),
    )
  }

  const handleReorder = (fromIndex: number, toIndex: number) => {
    const newSorting = [...sorting]
    const [removed] = newSorting.splice(fromIndex, 1)
    newSorting.splice(toIndex, 0, removed)
    onSortingChange(newSorting)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-white flex items-center gap-2">
          <GripVertical className="h-4 w-4" />
          Multi-Column Sort
        </h4>
        {sorting.length > 0 && (
          <button
            onClick={() => onSortingChange([])}
            className="text-[11px] text-slate-500 hover:text-slate-300"
          >
            Clear all
          </button>
        )}
      </div>

      {sorting.length === 0 ? (
        <div className="text-center py-4 text-slate-500">
          <p className="text-sm mb-2">No sort columns. Click headers or add below.</p>
          <button
            onClick={() => setShowAddSort(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-200 ring-1 ring-blue-400/40 hover:bg-blue-500/30 transition"
          >
            Add Sort Column
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {sorting.map((sort, index) => {
            const column = columns.find((c) => c.id === sort.field)
            return (
              <div
                key={sort.field}
                className="flex items-center gap-2 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2"
              >
                <button
                  onMouseDown={() => {}}
                  className="text-slate-500 hover:text-slate-300 cursor-grab active:cursor-grabbing"
                  onDragStart={(e) => {
                    e.dataTransfer.setData('text/plain', index.toString())
                    e.dataTransfer.effectAllowed = 'move'
                  }}
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'move'
                  }}
                  onDrop={(e) => {
                    const fromIndex = Number(e.dataTransfer.getData('text/plain'))
                    handleReorder(fromIndex, index)
                  }}
                >
                  <GripVertical className="h-4 w-4" />
                </button>

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">
                    {column?.label ?? sort.field}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Priority {index + 1} · {sort.direction === 'desc' ? 'Descending' : 'Ascending'}
                  </p>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleDirectionChange(index, 'desc')}
                    className={`rounded px-2 py-1 text-xs transition ${
                      sort.direction === 'desc'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-500 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleDirectionChange(index, 'asc')}
                    className={`rounded px-2 py-1 text-xs transition ${
                      sort.direction === 'asc'
                        ? 'bg-green-500/20 text-green-200'
                        : 'text-slate-500 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleRemoveSort(index)}
                    className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-red-400 transition"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )
          })}

          <button
            onClick={() => setShowAddSort(true)}
            className="w-full rounded-lg border border-white/10 bg-slate-900/40 px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-800/80 hover:text-slate-200"
          >
            + Add another sort column
          </button>
        </div>
      )}

      {showAddSort && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-white">Add Sort Column</h4>
              <button
                onClick={() => setShowAddSort(false)}
                className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white transition"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-60 overflow-y-auto space-y-1">
              {columns
                .filter((c) => !sorting.some((s) => s.field === c.id))
                .map((col) => (
                  <button
                    key={col.id}
                    onClick={() => handleAddSort(col.id)}
                    className="w-full flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm text-left text-slate-200 transition hover:bg-white/5"
                  >
                    <span className="truncate">{col.label}</span>
                    <span className="text-[11px] text-slate-500">{col.category}</span>
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}