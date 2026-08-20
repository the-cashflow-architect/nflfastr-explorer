import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  /** First column renders as a link and stays pinned while the rest scrolls. */
  pinFirstColumn?: boolean
  onRowClick?: (row: Record<string, unknown>) => void
  rowLabel?: (row: Record<string, unknown>) => string | undefined
  maxHeight?: string
}

export function DataTable({
  rows,
  columns,
  columnMeta,
  sorting,
  onSortingChange,
  loading,
  pinFirstColumn,
  onRowClick,
  rowLabel,
  maxHeight = 'calc(100vh - 220px)',
}: DataTableProps) {
  const metaById = useMemo(
    () => new Map(columnMeta.map((c) => [c.id, c])),
    [columnMeta],
  )

  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const update = () => {
      setCanScrollLeft(el.scrollLeft > 4)
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
    }
    update()
    el.addEventListener('scroll', update, { passive: true })
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      observer.disconnect()
    }
  }, [columns, rows])

  const toggleSort = (colId: string) => {
    const existing = sorting.find((s) => s.id === colId)
    if (!existing) onSortingChange([{ id: colId, desc: true }])
    else if (existing.desc) onSortingChange([{ id: colId, desc: false }])
    else onSortingChange([])
  }

  const firstCol = columns[0]
  const restCols = pinFirstColumn ? columns.slice(1) : columns

  const headerCell = (colId: string, pinned: boolean) => {
    const meta = metaById.get(colId)
    const sorted = sorting.find((s) => s.id === colId)
    return (
      <th
        key={colId}
        className={`whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400 ${
          pinned ? 'sticky left-0 z-[2] bg-slate-900/95 backdrop-blur-md' : ''
        }`}
      >
        <button
          type="button"
          onClick={() => toggleSort(colId)}
          className="inline-flex items-center gap-1 transition-colors duration-150 hover:text-blue-300"
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
  }

  const bodyCell = (
    row: Record<string, unknown>,
    colId: string,
    pinned: boolean,
    clickable: boolean,
    striped: boolean,
  ) => {
    const meta = metaById.get(colId)
    const content = formatCell(row[colId], colId, meta?.category)
    // The pinned cell needs its own opaque background (it sits above the
    // scrolling columns behind it), matched to this row's stripe so there's
    // no visible seam between it and the rest of the row.
    const pinnedBg = striped ? 'bg-[#0d1420]' : 'bg-slate-950'
    return (
      <td
        key={colId}
        className={`whitespace-nowrap px-3 py-2.5 text-slate-200 ${
          pinned ? `sticky left-0 z-[1] ${pinnedBg} group-hover:bg-slate-900` : ''
        }`}
      >
        {pinned && clickable ? (
          <span className="font-medium text-blue-300 group-hover:text-blue-200 group-hover:underline underline-offset-2">
            {content}
          </span>
        ) : (
          content
        )}
      </td>
    )
  }

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 backdrop-blur-xl">
      {loading ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/40 backdrop-blur-[1px]">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
        </div>
      ) : null}

      {/* Edge fades signal there are more columns to scroll to — a slim
          scrollbar alone is easy to miss. */}
      <div
        className={`pointer-events-none absolute left-0 top-0 z-[3] h-full w-8 bg-gradient-to-r from-slate-900/80 to-transparent transition-opacity duration-150 ${
          canScrollLeft ? 'opacity-100' : 'opacity-0'
        }`}
      />
      <div
        className={`pointer-events-none absolute right-0 top-0 z-[3] h-full w-8 bg-gradient-to-l from-slate-900/80 to-transparent transition-opacity duration-150 ${
          canScrollRight ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <div ref={scrollRef} className="overflow-auto" style={{ maxHeight }}>
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-[2] bg-slate-900/95 backdrop-blur-md">
            <tr className="border-b border-white/10">
              {pinFirstColumn && firstCol ? headerCell(firstCol, true) : null}
              {restCols.map((colId) => headerCell(colId, false))}
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
              rows.map((row, idx) => {
                const clickable = !!onRowClick
                const striped = idx % 2 !== 0
                return (
                  <tr
                    key={idx}
                    onClick={clickable ? () => onRowClick(row) : undefined}
                    title={clickable ? rowLabel?.(row) : undefined}
                    className={`group border-b border-white/5 transition-colors duration-150 hover:bg-white/[0.04] ${
                      clickable ? 'cursor-pointer' : ''
                    } ${striped ? 'bg-white/[0.015]' : 'bg-transparent'}`}
                  >
                    {pinFirstColumn && firstCol ? bodyCell(row, firstCol, true, clickable, striped) : null}
                    {restCols.map((colId) => bodyCell(row, colId, false, clickable, striped))}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
