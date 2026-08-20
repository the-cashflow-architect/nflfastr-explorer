import { User, Calendar, BarChart3 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { queryDataset } from '../api'
import { formatCell } from '../lib/filters'
import type { DatasetSchema, ColumnMeta } from '../types'
import { FILTER_CATEGORIES, HIDDEN_CATEGORIES } from '../types'
import { StatTrendChart, MultiStatTrend } from './StatTrendChart'
import { ExpandablePanel } from './ExpandablePanel'

interface PlayerDetailProps {
  datasetId: string
  schema: DatasetSchema
  playerName: string
}

// A cockpit page fetches its own broad column set rather than depending on
// whatever the caller's current stat tab happens to show — a QB opened from
// the Advanced tab should still show rushing/receiving history if they have
// any, and vice versa.
//
// player_season has no per-game week or opponent, and names its team column
// "recent_team" rather than "team" — requesting (or sorting by) a column
// that doesn't exist in the target table doesn't get silently dropped like
// an unknown filter does, it 500s, so this has to branch on the dataset.
const DETAIL_STAT_COLUMNS = [
  'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
  'passing_epa', 'passing_cpoe',
  'carries', 'rushing_yards', 'rushing_tds', 'rushing_epa',
  'receptions', 'targets', 'receiving_yards', 'receiving_tds', 'receiving_epa',
  'def_tackles_solo', 'def_sacks', 'def_interceptions', 'def_pass_defended',
  'fg_made', 'fg_att', 'pt_yards', 'pt_net_yards',
  'fantasy_points', 'fantasy_points_ppr',
]

function detailColumnsFor(datasetId: string): string[] {
  const identity =
    datasetId === 'player_season'
      ? ['season', 'position', 'recent_team', 'headshot_url']
      : ['season', 'week', 'position', 'team', 'opponent_team', 'headshot_url']
  return [...identity, ...DETAIL_STAT_COLUMNS]
}

function detailSortFor(datasetId: string): { field: string; direction: 'asc' | 'desc' }[] {
  return datasetId === 'player_season'
    ? [{ field: 'season', direction: 'asc' }]
    : [{ field: 'season', direction: 'asc' }, { field: 'week', direction: 'asc' }]
}

const CANDIDATE_SUMMARY_STATS = [
  'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
  'carries', 'rushing_yards', 'rushing_tds',
  'receptions', 'targets', 'receiving_yards', 'receiving_tds',
  'def_tackles_solo', 'def_sacks', 'def_interceptions',
  'fg_made', 'fg_att', 'pt_yards',
  'fantasy_points_ppr',
]

export function PlayerDetail({ datasetId, schema, playerName }: PlayerDetailProps) {
  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [compareStats, setCompareStats] = useState<string[] | null>(null)

  const { data: playerData, isLoading: playerLoading } = useQuery({
    queryKey: ['player-detail', datasetId, playerName],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: [{ field: 'player_display_name', operator: 'eq' as const, value: playerName }],
        sort: detailSortFor(datasetId),
        page: 1,
        page_size: 500,
        columns: detailColumnsFor(datasetId),
      }),
    enabled: !!datasetId && !!playerName,
  })

  const rows = useMemo(() => playerData?.rows ?? [], [playerData])
  const headshotUrl = rows.find((r) => typeof r.headshot_url === 'string')?.headshot_url as
    | string
    | undefined
  const position = rows[rows.length - 1]?.position as string | undefined
  const lastRow = rows[rows.length - 1]
  const latestTeam = (lastRow?.team ?? lastRow?.recent_team) as string | undefined

  // Which candidate stats this player actually has activity in — adapts the
  // summary table to their position instead of showing a fixed list where
  // half the columns are always blank.
  const relevantStats = useMemo(() => {
    return CANDIDATE_SUMMARY_STATS.filter((id) =>
      rows.some((r) => typeof r[id] === 'number' && (r[id] as number) !== 0),
    ).slice(0, 8)
  }, [rows])

  const seasonAggregates = useMemo(() => {
    if (!rows.length) return []
    const seasons = new Map<string, Record<string, number[]>>()
    for (const row of rows) {
      const season = String(row.season ?? '')
      if (!seasons.has(season)) seasons.set(season, {})
      const stats = seasons.get(season)!
      for (const col of relevantStats) {
        const val = row[col]
        if (typeof val === 'number' && !isNaN(val)) {
          if (!stats[col]) stats[col] = []
          stats[col].push(val)
        }
      }
    }
    return Array.from(seasons.entries())
      .map(([season, stats]) => {
        const agg = Object.fromEntries(
          Object.entries(stats).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0)]),
        )
        const gamesPlayed = rows.filter((r) => String(r.season ?? '') === season).length
        return { season: Number(season), games: gamesPlayed, ...agg } as Record<string, number>
      })
      .sort((a, b) => a.season - b.season)
  }, [rows, relevantStats])

  const numericStats = useMemo(() => {
    return schema.columns
      .filter((c) => ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL'].some((t) => c.dtype.includes(t)))
      .filter((c) => !HIDDEN_CATEGORIES.has(c.category))
      .filter((c) => !['season', 'week'].includes(c.id))
  }, [schema.columns])

  const numericByCategory = useMemo(() => {
    const map = new Map<string, ColumnMeta[]>()
    for (const c of numericStats) {
      if (!map.has(c.category)) map.set(c.category, [])
      map.get(c.category)!.push(c)
    }
    return Array.from(map.entries()).sort(([a], [b]) => (FILTER_CATEGORIES[a] ?? a).localeCompare(FILTER_CATEGORIES[b] ?? b))
  }, [numericStats])

  // Default to a stat this player actually has activity in, picked in a
  // sensible priority order — never the first alphabetical column, which
  // would as often as not be something irrelevant to their position.
  const smartDefault = useMemo(() => {
    for (const id of ['passing_yards', 'rushing_yards', 'receiving_yards', 'def_tackles_solo', 'fg_made', 'pt_yards']) {
      if (rows.some((r) => typeof r[id] === 'number' && (r[id] as number) !== 0)) return id
    }
    return relevantStats[0] ?? 'passing_yards'
  }, [rows, relevantStats])

  const effectiveSelectedStat = selectedStat ?? smartDefault
  const effectiveCompareStats = compareStats ?? relevantStats.slice(0, 3)

  const totalGames = rows.length
  const hasWeek = rows.some((r) => r.week != null)

  if (playerLoading || !playerData) {
    return (
      <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/30 light:bg-slate-100/70">
        <div className="text-center">
          <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
          <p className="text-sm text-slate-400 light:text-slate-500">Loading player data…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/50 light:bg-white p-6">
        <div className="flex items-start gap-4">
          {headshotUrl ? (
            <img
              src={headshotUrl}
              alt=""
              className="h-16 w-16 rounded-xl bg-slate-800 light:bg-slate-100 object-cover shadow-lg"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 shadow-lg shadow-blue-500/20">
              <User className="h-8 w-8 text-white light:text-slate-900" />
            </div>
          )}
          <div>
            <h2 className="text-2xl font-bold text-white light:text-slate-900">{playerName}</h2>
            <div className="mt-1 flex flex-wrap gap-4 text-sm text-slate-400 light:text-slate-500">
              {position ? <span>{position}{latestTeam ? ` · ${latestTeam}` : ''}</span> : null}
              {totalGames ? (
                <span className="inline-flex items-center gap-1.5">
                  <Calendar className="h-4 w-4" />
                  {totalGames} {hasWeek ? 'games' : 'seasons'}
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1.5">
                <BarChart3 className="h-4 w-4" />
                {seasonAggregates.length} {seasonAggregates.length === 1 ? 'season' : 'seasons'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {seasonAggregates.length > 0 && relevantStats.length > 0 && (
        <ExpandablePanel title="Season Summary" className="rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/50 light:bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500">Season Summary</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 light:border-slate-200">
                  <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500">
                    Season
                  </th>
                  <th className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500">
                    Games
                  </th>
                  {relevantStats.map((stat) => {
                    const meta = schema.columns.find((c) => c.id === stat)
                    return (
                      <th
                        key={stat}
                        className="whitespace-nowrap px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500"
                      >
                        {meta?.label ?? stat}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {seasonAggregates.map((season) => (
                  <tr key={String(season.season)} className="border-b border-white/5 light:border-slate-200">
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium text-slate-200 light:text-slate-700">
                      {season.season}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-slate-300 light:text-slate-600">
                      {season.games}
                    </td>
                    {relevantStats.map((stat) => {
                      const meta = schema.columns.find((c) => c.id === stat)
                      return (
                        <td key={stat} className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-slate-300 light:text-slate-600">
                          {season[stat] != null ? formatCell(season[stat], stat, meta?.category) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ExpandablePanel>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <select
            value={effectiveSelectedStat}
            onChange={(e) => setSelectedStat(e.target.value)}
            className="w-full rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/70 light:bg-white px-3 py-2 text-sm text-slate-100 light:text-slate-800 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
          >
            {numericByCategory.map(([category, stats]) => (
              <optgroup key={category} label={FILTER_CATEGORIES[category] ?? category}>
                {stats.map((stat) => (
                  <option key={stat.id} value={stat.id}>
                    {stat.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <ExpandablePanel title={`${effectiveSelectedStat} trend`}>
            <StatTrendChart
              data={rows}
              xField={hasWeek ? 'week' : 'season'}
              yField={effectiveSelectedStat}
              columnMeta={
                (schema.columns.find((c) => c.id === effectiveSelectedStat) ?? {
                  id: effectiveSelectedStat,
                  label: effectiveSelectedStat,
                  description: '',
                  dtype: 'unknown',
                  category: 'other',
                }) as ColumnMeta
              }
              playerName={playerName}
            />
          </ExpandablePanel>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {numericStats.slice(0, 16).map((stat) => (
              <button
                key={stat.id}
                onClick={() => {
                  const current = effectiveCompareStats
                  if (current.includes(stat.id)) {
                    setCompareStats(current.filter((s) => s !== stat.id))
                  } else if (current.length < 5) {
                    setCompareStats([...current, stat.id])
                  }
                }}
                className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                  effectiveCompareStats.includes(stat.id)
                    ? 'bg-blue-500/20 text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40'
                    : 'border-white/10 light:border-slate-200 text-slate-400 light:text-slate-500 hover:bg-white/5 hover:text-white'
                }`}
              >
                {stat.label}
              </button>
            ))}
          </div>
          {effectiveCompareStats.length > 0 && (
            <ExpandablePanel title="Stat Trends">
              <MultiStatTrend
                data={rows}
                xField={hasWeek ? 'week' : 'season'}
                yFields={effectiveCompareStats}
                columnsMeta={schema.columns}
                playerName={playerName}
              />
            </ExpandablePanel>
          )}
        </div>
      </div>
    </div>
  )
}
