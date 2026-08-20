import { useQuery } from '@tanstack/react-query'
import { Shield, Target } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchFilterOptions, fetchSchema, queryDataset } from '../api'
import type { ColumnMeta } from '../types'
import { DataTable, type SortState } from './DataTable'
import { ExpandablePanel } from './ExpandablePanel'
import { ErrorBanner } from './ErrorBanner'
import { HelpHint } from './HelpHint'
import type { NavOptions } from './HomeView'
import { TEAM_NAMES } from '../lib/teams'

interface TeamsExplorerProps {
  navOpts: NavOptions | null
  onDrillToTeam: (team: string) => void
}

// Additive counting stats — legitimate to sum across every player on a
// team into a team total. Efficiency metrics (EPA, CPOE, ...) are excluded
// on purpose: summing or averaging them across players doesn't produce a
// meaningful team number.
const OFFENSE_COLUMNS = [
  'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
  'sacks_suffered', 'carries', 'rushing_yards', 'rushing_tds',
  'receptions', 'targets', 'receiving_yards', 'receiving_tds',
  'rushing_fumbles_lost', 'receiving_fumbles_lost', 'sack_fumbles_lost',
]

const DEFENSE_COLUMNS = [
  'def_tackles_solo', 'def_tackles_with_assist', 'def_tackles_for_loss',
  'def_sacks', 'def_qb_hits', 'def_interceptions', 'def_pass_defended',
  'def_fumbles_forced', 'def_fumbles', 'def_tds',
]

const SYNTHETIC_META: Record<string, ColumnMeta> = {
  recent_team: { id: 'recent_team', label: 'Team', description: 'Team abbreviation.', dtype: 'VARCHAR', category: 'team' },
  total_yards: {
    id: 'total_yards', label: 'Total Yards', dtype: 'DOUBLE', category: 'passing',
    description: 'Passing yards plus rushing yards, summed across every player on the team.',
  },
  turnovers: {
    id: 'turnovers', label: 'Turnovers', dtype: 'DOUBLE', category: 'ball_security',
    description: 'Interceptions thrown plus fumbles lost, summed across every player on the team.',
  },
  touchdowns: {
    id: 'touchdowns', label: 'Total TDs', dtype: 'DOUBLE', category: 'passing',
    description: 'Passing, rushing, and receiving touchdowns, summed across every player on the team.',
  },
}

function aggregateByTeam(rows: Record<string, unknown>[], columns: string[]): Record<string, unknown>[] {
  const totals = new Map<string, Record<string, number>>()
  for (const row of rows) {
    const team = String(row.recent_team ?? '')
    if (!team) continue
    if (!totals.has(team)) totals.set(team, {})
    const acc = totals.get(team)!
    for (const col of columns) {
      const val = row[col]
      if (typeof val === 'number' && !isNaN(val)) {
        acc[col] = (acc[col] ?? 0) + val
      }
    }
  }
  return Array.from(totals.entries()).map(([team, stats]) => ({ recent_team: team, ...stats }))
}

export function TeamsExplorer({ navOpts, onDrillToTeam }: TeamsExplorerProps) {
  const [mode, setMode] = useState<'offense' | 'defense'>(navOpts?.teamMode ?? 'offense')
  const [season, setSeason] = useState<number | null>(null)
  const [sorting, setSorting] = useState<SortState[]>([])

  const { data: schema } = useQuery({ queryKey: ['schema', 'player_season'], queryFn: () => fetchSchema('player_season') })

  const { data: seasonOptions } = useQuery({
    queryKey: ['team-seasons'],
    queryFn: () => fetchFilterOptions('player_season', { field: 'season', filters: [], limit: 20 }),
  })

  const seasons = useMemo(
    () => (seasonOptions?.options as number[] | undefined)?.slice().sort((a, b) => b - a) ?? [],
    [seasonOptions],
  )

  useEffect(() => {
    if (season == null && seasons.length > 0) setSeason(seasons[0])
  }, [season, seasons])

  const columns = mode === 'offense' ? OFFENSE_COLUMNS : DEFENSE_COLUMNS

  const { data: rawRows, isFetching, error: rawError } = useQuery({
    queryKey: ['teams-raw', season, mode],
    // A season has ~2,000 player rows, well over the API's 500-row page
    // cap, so this has to page through — a single oversized request 422s.
    queryFn: async () => {
      const filters = season != null ? [{ field: 'season', operator: 'eq' as const, value: season }] : []
      const pageSize = 500
      let page = 1
      let rows: Record<string, unknown>[] = []
      while (true) {
        const res = await queryDataset('player_season', {
          filters,
          sort: [],
          page,
          page_size: pageSize,
          columns: ['recent_team', ...columns],
        })
        rows = rows.concat(res.rows)
        if (rows.length >= res.total || res.rows.length === 0) break
        page += 1
      }
      return rows
    },
    enabled: season != null,
  })

  const teamRows: Record<string, unknown>[] = useMemo(() => {
    if (!rawRows) return []
    const aggregated = aggregateByTeam(rawRows, columns)
    if (mode === 'offense') {
      return aggregated.map((row) => ({
        ...row,
        total_yards: (Number(row.passing_yards) || 0) + (Number(row.rushing_yards) || 0),
        touchdowns: (Number(row.passing_tds) || 0) + (Number(row.rushing_tds) || 0) + (Number(row.receiving_tds) || 0),
        turnovers:
          (Number(row.passing_interceptions) || 0) +
          (Number(row.rushing_fumbles_lost) || 0) +
          (Number(row.receiving_fumbles_lost) || 0) +
          (Number(row.sack_fumbles_lost) || 0),
      }))
    }
    return aggregated
  }, [rawRows, columns, mode])

  const displayColumns = mode === 'offense'
    ? ['recent_team', 'total_yards', 'passing_yards', 'passing_tds', 'rushing_yards', 'rushing_tds', 'receiving_yards', 'touchdowns', 'turnovers']
    : ['recent_team', ...DEFENSE_COLUMNS]

  const columnMeta = useMemo(() => {
    const fromSchema = schema?.columns ?? []
    const merged = new Map<string, ColumnMeta>()
    for (const c of fromSchema) merged.set(c.id, c)
    for (const [id, meta] of Object.entries(SYNTHETIC_META)) merged.set(id, meta)
    return Array.from(merged.values())
  }, [schema])

  const sortedRows = useMemo(() => {
    if (sorting.length === 0) {
      const defaultKey = mode === 'offense' ? 'total_yards' : 'def_tackles_solo'
      return [...teamRows].sort((a, b) => (Number(b[defaultKey]) || 0) - (Number(a[defaultKey]) || 0))
    }
    const { id, desc } = sorting[0]
    return [...teamRows].sort((a, b) => {
      const av = a[id]
      const bv = b[id]
      if (typeof av === 'number' && typeof bv === 'number') return desc ? bv - av : av - bv
      return desc ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv))
    })
  }, [teamRows, sorting, mode])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
          <button
            type="button"
            onClick={() => setMode('offense')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${mode === 'offense' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-300 hover:text-white hover:bg-white/5'}`}
          >
            <Target className="h-4 w-4" />
            Offense
          </button>
          <button
            type="button"
            onClick={() => setMode('defense')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${mode === 'defense' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-300 hover:text-white hover:bg-white/5'}`}
          >
            <Shield className="h-4 w-4" />
            Defense
          </button>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={season ?? ''}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="rounded-lg border border-white/10 bg-slate-900/70 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20"
          >
            {seasons.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <HelpHint
            title={mode === 'offense' ? 'Team Offense' : 'Team Defense'}
            text={
              mode === 'offense'
                ? "Each team's total is the sum of every player's recorded stats for that season — real, additive numbers, not modeled or estimated."
                : "These are individual defenders' recorded stats (tackles, sacks, takeaways) summed by team — not opponent yards or points allowed, which this dataset doesn't include."
            }
          />
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Click a team to see its full roster.{' '}
        {mode === 'defense' ? "Defensive totals are individual-stat sums, not points or yards allowed." : ''}
      </p>

      {rawError && <ErrorBanner error={rawError} />}

      <ExpandablePanel title={mode === 'offense' ? 'Team Offense' : 'Team Defense'} className="flex-1 min-h-0">
        {season == null || !schema ? (
          <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/30">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
          </div>
        ) : (
          <DataTable
            rows={sortedRows}
            columns={displayColumns}
            columnMeta={columnMeta}
            sorting={sorting}
            onSortingChange={setSorting}
            loading={isFetching}
            pinFirstColumn
            rankOffset={0}
            onRowClick={(row) => onDrillToTeam(String(row.recent_team))}
            rowLabel={(row) => `View ${TEAM_NAMES[String(row.recent_team)] ?? row.recent_team} roster`}
            maxHeight="calc(100vh - 320px)"
          />
        )}
      </ExpandablePanel>
    </div>
  )
}
