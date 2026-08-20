import { ArrowDown, ArrowUp, ArrowUpDown, Filter, Trophy } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { formatCell } from '../lib/filters'
import type { ColumnMeta } from '../types'
import { StatTooltip } from './StatTooltip'

export interface SortState {
  id: string
  desc: boolean
}

// Categories where a bigger number is unambiguously better, so a "this
// player leads the league" badge means something. Deliberately excludes
// games/season/week (not a stat), identity/team/time (not a number worth
// ranking), and fumbles/penalties (more is worse, not better).
const RANKABLE_CATEGORIES = new Set([
  'passing',
  'rushing',
  'receiving',
  'defense',
  'kicking',
  'punting',
  'returns',
  'fantasy',
  'advanced',
])

// Columns that identify the row rather than measure it — condensed tighter
// than stat columns so more of the table's width goes to actual numbers.
const COMPACT_CATEGORIES = new Set(['identity', 'team', 'time'])

// A handful of "passing"-category columns record something bad for the QB
// (a pick, a sack) rather than production — categorized alongside real
// passing stats for filtering purposes, but excluded here so the most
// interceptions thrown never gets dressed up as a "leader" badge.
const NEGATIVE_STAT_IDS = new Set([
  'passing_interceptions',
  'sacks_suffered',
  'sack_yards_lost',
  'sack_fumbles',
  'sack_fumbles_lost',
])

const RANK_BADGE_STYLE: Record<number, string> = {
  1: 'bg-amber-400/90 text-slate-900',
  2: 'bg-slate-300/80 text-slate-900',
  3: 'bg-amber-700/70 text-amber-50',
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
  /** Row number of the first row, e.g. (page - 1) * pageSize — pinned alongside the first column when set. */
  rankOffset?: number
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
  rankOffset,
  onRowClick,
  rowLabel,
  maxHeight = 'calc(100vh - 220px)',
}: DataTableProps) {
  const metaById = useMemo(
    () => new Map(columnMeta.map((c) => [c.id, c])),
    [columnMeta],
  )

  const showRankColumn = pinFirstColumn && rankOffset != null
  const [showLeaders, setShowLeaders] = useState(true)

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
  const secondPinLeft = showRankColumn ? '3rem' : undefined

  // Rank (1st/2nd/3rd) within the rows currently on screen, per eligible
  // stat column — a lightweight "who's leading in this?" visual, not a
  // true league-wide rank (that would need a dedicated backend query).
  const leaderRanks = useMemo(() => {
    if (!showLeaders) return new Map<string, Map<number, number>>()
    const result = new Map<string, Map<number, number>>()
    for (const colId of columns) {
      const meta = metaById.get(colId)
      if (!meta || !RANKABLE_CATEGORIES.has(meta.category) || NEGATIVE_STAT_IDS.has(colId)) continue
      // A "leader" badge on 0 is meaningless — skip columns where nobody in
      // the visible rows actually did anything (common when a stat table
      // mixes positions, e.g. a QB with 0 receiving yards).
      const values = rows
        .map((row, idx) => [idx, row[colId]] as const)
        .filter((v): v is [number, number] => typeof v[1] === 'number' && Number.isFinite(v[1]) && v[1] > 0)
      if (values.length === 0) continue
      const sorted = [...values].sort((a, b) => b[1] - a[1])
      const ranks = new Map<number, number>()
      let rank = 0
      let lastValue: number | null = null
      sorted.forEach(([idx, value], i) => {
        if (value !== lastValue) {
          rank = i + 1
          lastValue = value
        }
        if (rank <= 3) ranks.set(idx, rank)
      })
      if (ranks.size > 0) result.set(colId, ranks)
    }
    return result
  }, [showLeaders, columns, rows, metaById])

  const headerCell = (colId: string, pinLeft: string | undefined) => {
    const meta = metaById.get(colId)
    const sorted = sorting.find((s) => s.id === colId)
    const compact = meta && COMPACT_CATEGORIES.has(meta.category)
    return (
      <th
        key={colId}
        style={pinLeft != null ? { left: pinLeft } : undefined}
        className={`whitespace-nowrap text-left text-xs font-semibold uppercase tracking-wide text-slate-400 ${
          compact ? 'px-2 py-3' : 'px-3 py-3'
        } ${pinLeft != null ? 'sticky z-[2] bg-slate-900/95 backdrop-blur-md' : ''}`}
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
    rowIdx: number,
    colId: string,
    pinLeft: string | undefined,
    clickable: boolean,
    striped: boolean,
  ) => {
    const meta = metaById.get(colId)
    const content = formatCell(row[colId], colId, meta?.category)
    const rank = leaderRanks.get(colId)?.get(rowIdx)
    const compact = meta && COMPACT_CATEGORIES.has(meta.category)
    // The pinned cell needs its own opaque background (it sits above the
    // scrolling columns behind it), matched to this row's stripe so there's
    // no visible seam between it and the rest of the row.
    const pinnedBg = striped ? 'bg-[#0d1420]' : 'bg-slate-950'
    return (
      <td
        key={colId}
        style={pinLeft != null ? { left: pinLeft } : undefined}
        className={`whitespace-nowrap text-slate-200 ${compact ? 'px-2 py-2.5 text-[13px]' : 'px-3 py-2.5'} ${
          pinLeft != null ? `sticky z-[1] ${pinnedBg} group-hover:bg-slate-900` : ''
        }`}
      >
        <span className="inline-flex items-center gap-1">
          {pinLeft != null && clickable ? (
            <span className="font-medium text-blue-300 group-hover:text-blue-200 group-hover:underline underline-offset-2">
              {content}
            </span>
          ) : (
            content
          )}
          {rank ? (
            <span
              title={`#${rank} among rows shown`}
              className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${RANK_BADGE_STYLE[rank]}`}
            >
              {rank}
            </span>
          ) : null}
        </span>
      </td>
    )
  }

  const colSpan = columns.length + (showRankColumn ? 1 : 0)

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-slate-900/40 backdrop-blur-xl">
      {loading ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/40 backdrop-blur-[1px]">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
        </div>
      ) : null}

      <div className="flex items-center justify-end border-b border-white/5 py-1.5 pl-2 pr-10">
        <button
          type="button"
          onClick={() => setShowLeaders((v) => !v)}
          title={showLeaders ? 'Hide stat-leader badges' : 'Show stat-leader badges'}
          className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors duration-150 ${
            showLeaders
              ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
              : 'border-white/10 bg-slate-900/70 text-slate-400 hover:text-white'
          }`}
        >
          <Trophy className="h-3 w-3" />
          Leaders
        </button>
      </div>

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
              {showRankColumn ? (
                <th className="sticky left-0 z-[2] w-12 whitespace-nowrap bg-slate-900/95 px-2 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400 backdrop-blur-md">
                  Rank
                </th>
              ) : null}
              {pinFirstColumn && firstCol ? headerCell(firstCol, secondPinLeft ?? '0px') : null}
              {restCols.map((colId) => headerCell(colId, undefined))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="px-4 py-16 text-center text-slate-500">
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
                const pinnedBg = striped ? 'bg-[#0d1420]' : 'bg-slate-950'
                return (
                  <tr
                    key={idx}
                    onClick={clickable ? () => onRowClick(row) : undefined}
                    title={clickable ? rowLabel?.(row) : undefined}
                    className={`group border-b border-white/5 transition-colors duration-150 hover:bg-white/[0.04] ${
                      clickable ? 'cursor-pointer' : ''
                    } ${striped ? 'bg-white/[0.015]' : 'bg-transparent'}`}
                  >
                    {showRankColumn ? (
                      <td
                        className={`sticky left-0 z-[1] w-12 whitespace-nowrap px-2 py-2.5 text-slate-400 ${pinnedBg} group-hover:bg-slate-900`}
                      >
                        {(rankOffset ?? 0) + idx + 1}
                      </td>
                    ) : null}
                    {pinFirstColumn && firstCol ? bodyCell(row, idx, firstCol, secondPinLeft ?? '0px', clickable, striped) : null}
                    {restCols.map((colId) => bodyCell(row, idx, colId, undefined, clickable, striped))}
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
