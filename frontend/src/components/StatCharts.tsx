import { useMemo } from 'react'
import type { ColumnMeta, SortSpec } from '../types'
import { StatTrendChart, MultiStatTrend } from './StatTrendChart'

interface StatChartsProps {
  schema: {
    columns: ColumnMeta[]
    default_columns: string[]
    default_sort: SortSpec[]
  }
  queryData: { rows: Record<string, unknown>[]; total: number } | undefined
  visibleColumns: string[]
}

// Preference order among whichever numeric columns are currently visible —
// player_weekly/season never has a bare "epa"/"cpoe"/"wpa" column (only
// play-by-play does), so both forms are listed and whichever exists wins.
const PREFERRED_STATS = [
  'epa', 'passing_epa', 'rushing_epa', 'receiving_epa',
  'fantasy_points_ppr', 'passing_yards', 'rushing_yards', 'receiving_yards',
  'cpoe', 'wpa',
]

export function StatCharts({ schema, queryData, visibleColumns }: StatChartsProps) {
  // Memoised so the aggregation below has stable dependencies — `rows` would
  // otherwise be a fresh array on every render and defeat the useMemo.
  const rows = useMemo(() => queryData?.rows ?? [], [queryData])

  const hasWeek = visibleColumns.includes('week')
  const xField = hasWeek ? 'week' : 'season'

  const finalStats = useMemo(() => {
    const numericColumns = visibleColumns.filter((colId) => {
      const meta = schema.columns.find((c) => c.id === colId)
      return meta && ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL'].some((t) => meta.dtype.includes(t))
    })
    const preferred = numericColumns.filter((c) => PREFERRED_STATS.includes(c)).slice(0, 4)
    return preferred.length > 0 ? preferred : numericColumns.slice(0, 4)
  }, [visibleColumns, schema])

  const aggregated = useMemo(() => {
    const groups = new Map<string, Record<string, number[]>>()
    for (const row of rows) {
      const xVal = String(row[xField] ?? '')
      if (!xVal) continue
      if (!groups.has(xVal)) groups.set(xVal, {})
      for (const stat of finalStats) {
        const val = row[stat]
        if (typeof val === 'number' && !isNaN(val)) {
          if (!groups.get(xVal)![stat]) groups.get(xVal)![stat] = []
          groups.get(xVal)![stat].push(val)
        }
      }
    }
    return Array.from(groups.entries())
      .map(([x, stats]) => ({
        x,
        ...Object.fromEntries(
          Object.entries(stats).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length]),
        ),
      }))
      .sort((a, b) => Number(a.x) - Number(b.x))
  }, [rows, xField, finalStats])

  // Both bail-outs sit below every hook call — returning earlier would
  // change the hook count between renders and crash React.
  if (rows.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        No data to chart. Adjust your filters.
      </div>
    )
  }

  if (aggregated.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        No numeric data available for the selected stat view.
      </div>
    )
  }

  const statMetas = finalStats.map((s) => schema.columns.find((c) => c.id === s)).filter(Boolean) as ColumnMeta[]

  return (
    <div className="space-y-4">
      {statMetas.length === 1 ? (
        <StatTrendChart data={aggregated} xField="x" yField={statMetas[0].id} columnMeta={statMetas[0]} />
      ) : (
        <MultiStatTrend data={aggregated} xField="x" yFields={finalStats} columnsMeta={statMetas} />
      )}
    </div>
  )
}
