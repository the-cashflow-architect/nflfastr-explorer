import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from 'lucide-react'
import { useMemo } from 'react'
import { formatCell } from '../lib/filters'
import type { ColumnMeta } from '../types'
import { StatTooltip } from './StatTooltip'

export interface SortState {
  id: string
  desc: boolean
}

interface DataTableProps {
  rows: Record<string, unknown>[]
  columns: string[]
  columnMeta: ColumnMeta[]
  sorting: SortState[]
  onSortingChange: (sorting: SortState[]) => void
  loading?: boolean
}

export function DataTable({
  rows,
  columns,
  columnMeta,
  sorting,
  onSortingChange,
  loading,
}: DataTableProps) {
  const metaById = useMemo(
    () => new Map(columnMeta.map((c) => [c.id, c])),
    [columnMeta],
  )

  const toggleSort = (colId: string) => {
    const existing = sorting.find((s) => s.id === colId)
    if (!existing) onSortingChange([{ id: colId, desc: true }])
    else if (existing.desc) onSortingChange([{ id: colId, desc: false }])
    else onSortingChange([])
  }

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 backdrop-blur-xl">
      {loading ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/40 backdrop-blur-[1px]">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
        </div>
      ) : null}
      <div className="overflow-auto max-h-[calc(100vh-220px)]">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-[1] bg-slate-900/95 backdrop-blur-md">
            <tr className="border-b border-white/10">
              {columns.map((colId) => {
                const meta = metaById.get(colId)
                const sorted = sorting.find((s) => s.id === colId)
                return (
                  <th
                    key={colId}
                    className="whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400"
                  >
                     <button
                       type="button"
                       onClick={() => toggleSort(colId)}
                       className="inline-flex items-center gap-1 transition-all duration-200 hover:text-blue-300"
                     >
                      <span>{meta?.label ?? colId}</span>
                      {meta ? <StatTooltip column={meta} /> : null}
                      {sorted ? (
                        sorted.desc ? (
                          <ArrowDown className="h-3.5 w-3.5 text-blue-400" />
                        ) : (
                          <ArrowUp className="h-3.5 w-3.5 text-blue-400" />
                        )
                      ) : (
                        <ArrowUpDown className="h-3.5 w-3.5 opacity-40" />
                      )}
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-16 text-center text-slate-500">
                    <div className="flex flex-col items-center gap-2">
                      <Filter className="h-8 w-8 text-slate-600/50" />
                      <span className="text-sm">No rows match your filters.</span>
                      <span className="text-xs">Try broadening filters or selecting different columns.</span>
                    </div>
                  </td>
                </tr>
              ) : (
              rows.map((row, idx) => (
                 <tr
                  key={idx}
                  className={`group border-b border-white/5 transition-all duration-150 hover:bg-white/[0.04] ${
                    idx % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.015]'
                  }`}
                >
                  {columns.map((colId) => (
                    <td key={colId} className="whitespace-nowrap px-3 py-2.5 text-slate-200">
                      {formatCell(row[colId])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
