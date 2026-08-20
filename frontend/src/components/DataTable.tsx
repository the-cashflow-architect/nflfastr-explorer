import { ArrowDown, ArrowUp, ArrowUpDown, Filter, Gauge } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { formatCell } from '../lib/filters'
import type { ColumnMeta } from '../types'
import { StatTooltip } from './StatTooltip'

export interface SortState {
  id: string
  desc: boolean
}

// Categories where a bigger number is unambiguously better, so grading every
// row on it means something. Deliberately excludes games/season/week (not a
// stat), identity/team/time (not a number worth ranking), and
// fumbles/penalties (more is worse, not better).
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
// interceptions thrown never gets dressed up as a good tier.
const NEGATIVE_STAT_IDS = new Set([
  'passing_interceptions',
  'sacks_suffered',
  'sack_yards_lost',
  'sack_fumbles',
  'sack_fumbles_lost',
])

// 5-tier read of where a value falls among the rows on screen: 5 = best 20%,
// 1 = worst 20%. Small colored dot, not a number — meant to be glanced at,
// not read.
const TIER_DOT: Record<number, string> = {
  5: 'bg-emerald-400',
  4: 'bg-lime-400',
  3: 'bg-amber-300',
  2: 'bg-orange-400',
  1: 'bg-rose-500',
}

const TIER_LABEL: Record<number, string> = {
  5: 'Top 20% among rows shown',
  4: 'Above average among rows shown',
  3: 'Average among rows shown',
  2: 'Below average among rows shown',
  1: 'Bottom 20% among rows shown',
}

interface ColumnGroup {
  /** Header shown above the group, spanning every column in it. */
  label: string
  /** Column ids in this group, contiguous within `columns`. */
  columnIds: string[]
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
  /** Groups of columns (e.g. one stat broken out per week) under a shared header. */
  columnGroups?: ColumnGroup[]
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
  columnGroups,
}: DataTableProps) {
  const metaById = useMemo(
    () => new Map(columnMeta.map((c) => [c.id, c])),
    [columnMeta],
  )

  const showRankColumn = pinFirstColumn && rankOffset != null
  const [showTiers, setShowTiers] = useState(true)

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

  const hasGroups = !!(columnGroups && columnGroups.length > 0)
  const groupedColIds = useMemo(
    () => new Set((columnGroups ?? []).flatMap((g) => g.columnIds)),
    [columnGroups],
  )
  const groupStartIds = useMemo(
    () => new Map((columnGroups ?? []).map((g) => [g.columnIds[0], g])),
    [columnGroups],
  )

  // Every row gets a tier (1-5) on every eligible stat column, based on
  // where its value falls among the rows currently on screen — not a true
  // league-wide percentile (that would need a dedicated backend query), but
  // enough to see who's leading and who's trailing at a glance.
  const statTiers = useMemo(() => {
    if (!showTiers) return new Map<string, Map<number, number>>()
    const result = new Map<string, Map<number, number>>()
    for (const colId of columns) {
      const meta = metaById.get(colId)
      if (!meta || !RANKABLE_CATEGORIES.has(meta.category) || NEGATIVE_STAT_IDS.has(colId)) continue
      const values = rows
        .map((row, idx) => [idx, row[colId]] as const)
        .filter((v): v is [number, number] => typeof v[1] === 'number' && Number.isFinite(v[1]))
      if (values.length < 2) continue
      // Nobody in view actually did anything in this stat — grading everyone
      // "poor" at it would be meaningless, not informative (common when a
      // stat table mixes positions, e.g. a QB with 0 receiving yards).
      const distinct = new Set(values.map((v) => v[1]))
      if (distinct.size < 2) continue
      const sorted = [...values].sort((a, b) => b[1] - a[1])
      const n = sorted.length
      const tiers = new Map<number, number>()
      // Rows tied on the same value must land in the same tier — grouping by
      // value (rather than tiering each sorted position independently) keeps
      // a long run of identical values (very common: many players with 0 in
      // a stat that isn't their position's specialty) from being split
      // arbitrarily across tiers depending on where they fell in the sort.
      // The tier comes from the tied group's *midpoint* rank (fractional
      // ranking), not its best-case start — otherwise a block of 50 tied
      // zeros starting at position 3 would score as "top 20%".
      let i = 0
      while (i < n) {
        let j = i
        while (j < n && sorted[j][1] === sorted[i][1]) j++
        const midpoint = (i + j - 1) / 2
        const frac = midpoint / (n - 1) // 0 = best, 1 = worst
        const tier = frac < 0.2 ? 5 : frac < 0.4 ? 4 : frac < 0.6 ? 3 : frac < 0.8 ? 2 : 1
        for (let k = i; k < j; k++) tiers.set(sorted[k][0], tier)
        i = j
      }
      result.set(colId, tiers)
    }
    return result
  }, [showTiers, columns, rows, metaById])

  const headerCell = (colId: string, pinLeft: string | undefined, rowSpan?: number) => {
    const meta = metaById.get(colId)
    const sorted = sorting.find((s) => s.id === colId)
    const compact = meta && COMPACT_CATEGORIES.has(meta.category)
    return (
      <th
        key={colId}
        rowSpan={rowSpan}
        style={pinLeft != null ? { left: pinLeft } : undefined}
        className={`whitespace-nowrap text-left text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500 ${
          compact ? 'px-2 py-3' : 'px-3 py-3'
        } ${pinLeft != null ? 'sticky z-[2] bg-slate-900/95 light:bg-white/95 backdrop-blur-md' : ''}`}
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
    const tier = statTiers.get(colId)?.get(rowIdx)
    const compact = meta && COMPACT_CATEGORIES.has(meta.category)
    // The pinned cell needs its own opaque background (it sits above the
    // scrolling columns behind it), matched to this row's stripe so there's
    // no visible seam between it and the rest of the row.
    const pinnedBg = striped ? 'bg-[#0d1420] light:bg-slate-100' : 'bg-slate-950 light:bg-slate-50'
    return (
      <td
        key={colId}
        style={pinLeft != null ? { left: pinLeft } : undefined}
        className={`whitespace-nowrap text-slate-200 light:text-slate-700 ${compact ? 'px-2 py-2.5 text-[13px]' : 'px-3 py-2.5'} ${
          pinLeft != null ? `sticky z-[1] ${pinnedBg} group-hover:bg-slate-900 light:group-hover:bg-slate-100` : ''
        }`}
      >
        <span className="inline-flex items-center gap-1.5">
          {pinLeft != null && clickable ? (
            <span className="font-medium text-blue-300 light:text-blue-600 group-hover:text-blue-200 group-hover:underline underline-offset-2">
              {content}
            </span>
          ) : (
            content
          )}
          {tier ? (
            <span
              title={TIER_LABEL[tier]}
              className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${TIER_DOT[tier]}`}
            />
          ) : null}
        </span>
      </td>
    )
  }

  const colSpan = columns.length + (showRankColumn ? 1 : 0)

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white backdrop-blur-xl">
      {loading ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/40 light:bg-white/60 backdrop-blur-[1px]">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
        </div>
      ) : null}

      <div className="flex items-center justify-end border-b border-white/5 light:border-slate-200 py-1.5 pl-2 pr-10">
        <button
          type="button"
          onClick={() => setShowTiers((v) => !v)}
          title={showTiers ? 'Hide stat performance tiers' : 'Show stat performance tiers'}
          className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors duration-150 ${
            showTiers
              ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200 light:text-emerald-700'
              : 'border-white/10 light:border-slate-200 bg-slate-900/70 light:bg-white text-slate-400 light:text-slate-500 hover:text-white light:hover:text-slate-900'
          }`}
        >
          <Gauge className="h-3 w-3" />
          Tiers
        </button>
      </div>

      {/* Edge fades signal there are more columns to scroll to — a slim
          scrollbar alone is easy to miss. */}
      <div
        className={`pointer-events-none absolute left-0 top-0 z-[3] h-full w-8 bg-gradient-to-r from-slate-900/80 light:from-white/90 to-transparent transition-opacity duration-150 ${
          canScrollLeft ? 'opacity-100' : 'opacity-0'
        }`}
      />
      <div
        className={`pointer-events-none absolute right-0 top-0 z-[3] h-full w-8 bg-gradient-to-l from-slate-900/80 light:from-white/90 to-transparent transition-opacity duration-150 ${
          canScrollRight ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <div ref={scrollRef} className="overflow-auto" style={{ maxHeight }}>
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-[2] bg-slate-900/95 light:bg-white/95 backdrop-blur-md">
            {hasGroups ? (
              <tr className="border-b border-white/5 light:border-slate-200">
                {showRankColumn ? (
                  <th
                    rowSpan={2}
                    className="sticky left-0 z-[2] w-12 whitespace-nowrap bg-slate-900/95 light:bg-white/95 px-2 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500 backdrop-blur-md"
                  >
                    Rank
                  </th>
                ) : null}
                {pinFirstColumn && firstCol ? headerCell(firstCol, secondPinLeft ?? '0px', 2) : null}
                {restCols.map((colId) => {
                  const group = groupStartIds.get(colId)
                  if (group) {
                    return (
                      <th
                        key={`group-${group.label}`}
                        colSpan={group.columnIds.length}
                        className="whitespace-nowrap border-l border-white/5 light:border-slate-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-blue-300 light:text-blue-600"
                      >
                        {group.label}
                      </th>
                    )
                  }
                  if (groupedColIds.has(colId)) return null
                  return headerCell(colId, undefined, 2)
                })}
              </tr>
            ) : null}
            <tr className="border-b border-white/10 light:border-slate-200">
              {!hasGroups && showRankColumn ? (
                <th className="sticky left-0 z-[2] w-12 whitespace-nowrap bg-slate-900/95 light:bg-white/95 px-2 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500 backdrop-blur-md">
                  Rank
                </th>
              ) : null}
              {!hasGroups && pinFirstColumn && firstCol ? headerCell(firstCol, secondPinLeft ?? '0px') : null}
              {restCols
                .filter((colId) => !hasGroups || groupedColIds.has(colId))
                .map((colId) => headerCell(colId, undefined))}
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
                const pinnedBg = striped ? 'bg-[#0d1420] light:bg-slate-100' : 'bg-slate-950 light:bg-slate-50'
                return (
                  <tr
                    key={idx}
                    onClick={clickable ? () => onRowClick(row) : undefined}
                    title={clickable ? rowLabel?.(row) : undefined}
                    className={`group border-b border-white/5 light:border-slate-200 transition-colors duration-150 hover:bg-white/[0.04] light:hover:bg-slate-50 ${
                      clickable ? 'cursor-pointer' : ''
                    } ${striped ? 'bg-white/[0.015] light:bg-slate-50/60' : 'bg-transparent'}`}
                  >
                    {showRankColumn ? (
                      <td
                        className={`sticky left-0 z-[1] w-12 whitespace-nowrap px-2 py-2.5 text-slate-400 light:text-slate-500 ${pinnedBg} group-hover:bg-slate-900 light:group-hover:bg-slate-100`}
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
