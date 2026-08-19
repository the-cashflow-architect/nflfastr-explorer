import { User, Calendar, BarChart3 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { queryDataset } from '../api'
import { formatCell } from '../lib/filters'
import type { DatasetSchema, ColumnMeta } from '../types'
import { StatTrendChart, MultiStatTrend } from './StatTrendChart'

interface PlayerDetailProps {
  datasetId: string
  schema: DatasetSchema
  playerName: string
}

export function PlayerDetail({ datasetId, schema, playerName }: PlayerDetailProps) {
  const [selectedStat, setSelectedStat] = useState<string>('epa')
  const [compareStats, setCompareStats] = useState<string[]>(['epa', 'fantasy_points_ppr'])

  // Get all data for this player
  const { data: playerData, isLoading: playerLoading } = useQuery({
    queryKey: ['player-detail', datasetId, playerName],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: [
          { field: 'player_display_name', operator: 'eq' as const, value: playerName }
        ],
        sort: [{ field: 'season', direction: 'asc' }, { field: 'week', direction: 'asc' }],
        page: 1,
        page_size: 500,
        columns: schema.default_columns,
      }),
    enabled: !!schema && !!playerName,
  })

  const rows = useMemo(() => playerData?.rows ?? [], [playerData])

  // Aggregate data by season
  const seasonAggregates = useMemo(() => {
    if (!rows.length) return []

    const seasons = new Map<string, Record<string, number[]>>()
    for (const row of rows) {
      const season = String(row.season ?? '')
      if (!seasons.has(season)) seasons.set(season, {})

      const stats = seasons.get(season)!
      for (const col of schema.default_columns) {
        const val = row[col]
        if (typeof val === 'number' && !isNaN(val)) {
          if (!stats[col]) stats[col] = []
          stats[col].push(val)
        }
      }
    }

    return Array.from(seasons.entries()).map(([season, stats]) => {
      const agg = Object.fromEntries(
        Object.entries(stats).map(([k, v]) => [
          k,
          (v as number[]).reduce((a: number, b: number) => a + b, 0),
        ]),
      )
      return { season: Number(season), ...agg } as Record<string, number | string>
    }).sort((a, b) => Number(a.season) - Number(b.season))
  }, [rows, schema.default_columns])

  // Get available numeric stats
  const numericStats = useMemo(() => {
    return schema.columns
      .filter((c) => c.dtype.includes('INT') || c.dtype.includes('FLOAT') || c.dtype.includes('DOUBLE') || c.dtype.includes('DECIMAL'))
      .filter((c) => !['season', 'week', 'player_id'].includes(c.id))
  }, [schema.columns])

  // Get latest season stats
  const latestSeasonData = seasonAggregates[seasonAggregates.length - 1]
  const latestPlayerRows = rows.filter(
    (r) => !latestSeasonData || r.season === latestSeasonData.season,
  )

  // Compute summary stats
  const summaryStats = useMemo(() => {
    if (!latestSeasonData) return {}

    const result: Record<string, number> = {}
    const statKeys = ['passing_yards', 'rushing_yards', 'receiving_yards', 'passing_tds', 'rushing_tds', 'receiving_tds', 'fantasy_points_ppr', 'epa', 'cpoe', 'wpa', 'targets', 'receptions', 'attempts', 'carries']

    for (const key of statKeys) {
      const val = latestSeasonData[key]
      if (val != null && typeof val === 'number') {
        result[key] = val
      }
    }

    if (latestPlayerRows.length > 0) {
      result.games = latestPlayerRows.length
    }

    return result
  }, [latestSeasonData, latestPlayerRows.length])

  if (playerLoading || !playerData) {
    return (
      <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/30">
        <div className="text-center">
          <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
          <p className="text-sm text-slate-400">Loading player data…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Player Header */}
      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 shadow-lg shadow-blue-500/20">
            <User className="h-8 w-8 text-white" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">{playerName}</h2>
            <div className="mt-1 flex flex-wrap gap-4 text-sm text-slate-400">
              {summaryStats.games ? (
                <span className="inline-flex items-center gap-1.5">
                  <Calendar className="h-4 w-4" />
                  {summaryStats.games} games
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1.5">
                <BarChart3 className="h-4 w-4" />
                {seasonAggregates.length} seasons
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Season Summary */}
      {seasonAggregates.length > 0 && (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Season Summary
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Season
                  </th>
                  {['games', 'passing_yards', 'rushing_yards', 'receiving_yards', 'fantasy_points_ppr', 'epa', 'cpoe', 'wpa'].map(
                    (stat) => (
                      <th
                        key={stat}
                        className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400"
                      >
                        {stat.replace(/_/g, ' ')}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {seasonAggregates.map((season) => (
                  <tr key={String(season.season)} className="border-b border-white/5">
                    <td className="whitespace-nowrap px-3 py-2.5 text-slate-200 font-medium">
                      {season.season}
                    </td>
                    {['games', 'passing_yards', 'rushing_yards', 'receiving_yards', 'fantasy_points_ppr', 'epa', 'cpoe', 'wpa'].map(
                      (stat) => (
                        <td
                          key={stat}
                          className="whitespace-nowrap px-3 py-2.5 text-right text-slate-300 font-mono"
                        >
                          {season[stat] != null ? formatCell(season[stat]) : '—'}
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trend Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Single Stat Trend */}
        <div className="space-y-3">
          <select
            value={selectedStat}
            onChange={(e) => setSelectedStat(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
          >
            {numericStats
              .filter((c) => c.id !== 'season' && c.id !== 'week')
              .map((stat) => (
                <option key={stat.id} value={stat.id}>
                  {stat.label}
                </option>
              ))}
          </select>
          {selectedStat && (
            <StatTrendChart
              data={rows}
              xField={rows.some((r) => r.week) ? 'week' : 'season'}
              yField={selectedStat}
              columnMeta={(schema.columns.find((c) => c.id === selectedStat) ?? {
                id: selectedStat,
                label: selectedStat,
                description: '',
                dtype: 'unknown',
                category: 'other',
              }) as ColumnMeta}
              playerName={playerName}
            />
          )}
        </div>

        {/* Multi-Stat Comparison */}
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {numericStats
              .filter((c) => !['season', 'week', 'player_id'].includes(c.id))
              .slice(0, 12)
              .map((stat) => (
                <button
                  key={stat.id}
                  onClick={() => {
                    if (compareStats.includes(stat.id)) {
                      setCompareStats(compareStats.filter((s) => s !== stat.id))
                    } else if (compareStats.length < 5) {
                      setCompareStats([...compareStats, stat.id])
                    }
                  }}
                  className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                    compareStats.includes(stat.id)
                      ? 'bg-blue-500/20 text-blue-200 ring-1 ring-blue-400/40'
                      : 'border-white/10 text-slate-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {stat.label}
                </button>
              ))}
          </div>
          {compareStats.length > 0 && (
            <MultiStatTrend
              data={rows}
              xField={rows.some((r) => r.week) ? 'week' : 'season'}
              yFields={compareStats}
              columnsMeta={schema.columns}
              playerName={playerName}
            />
          )}
        </div>
      </div>
    </div>
  )
}