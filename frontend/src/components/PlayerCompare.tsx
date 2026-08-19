import { Users, X, ChevronDown, BarChart3 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import { formatCell } from '../lib/filters'
import type { ActiveFilter, ColumnMeta, DatasetSchema, FilterDef, SortSpec } from '../types'
import { FILTER_CATEGORIES } from '../types'
import { StatTooltip } from './StatTooltip'
import { PlayerDetail } from './PlayerDetail'

interface PlayerCompareProps {
  datasetId: string
  schema: {
    columns: ColumnMeta[]
    filters: FilterDef[]
    default_columns: string[]
    default_sort: SortSpec[]
  }
  activeFilters: ActiveFilter[]
}

export function PlayerCompare({ datasetId, schema, activeFilters }: PlayerCompareProps) {
  const [playerFilters, setPlayerFilters] = useState<ActiveFilter[]>([])
  const [compareMode, setCompareMode] = useState<'season' | 'weekly'>('season')
  const [detailPlayer, setDetailPlayer] = useState<string | null>(null)

  const conditions = useMemo(
    () => activeFiltersToConditions([...activeFilters, ...playerFilters]),
    [activeFilters, playerFilters],
  )

  const { data: playersData } = useQuery({
    queryKey: ['compare-players', datasetId, conditions],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: conditions,
        sort: [{ field: 'player_display_name', direction: 'asc' }],
        page: 1,
        page_size: 500,
        columns: ['player_display_name', 'player_id', 'position', 'team'],
      }),
    enabled: datasetId !== 'play_by_play',
  })

  const availablePlayers = useMemo(() => {
    if (!playersData) return []
    const seen = new Set<string>()
    return playersData.rows
      .filter((row) => {
        const name = String(row.player_display_name ?? '')
        if (seen.has(name)) return false
        seen.add(name)
        return true
      })
      .map((row) => ({
        name: String(row.player_display_name),
        id: String(row.player_id ?? ''),
        position: String(row.position ?? ''),
        team: String(row.team ?? ''),
      }))
  }, [playersData])

  const selectedPlayers = playerFilters
    .filter((f) => f.def.id === 'player_compare')
    .flatMap((f) => (f.value as string[] ?? []))

  const playerConditions = useMemo(() => {
    if (selectedPlayers.length === 0) return []
    return [{ field: 'player_display_name', operator: 'in' as const, value: selectedPlayers }]
  }, [selectedPlayers])

  const allConditions = useMemo(
    () => [...conditions, ...playerConditions],
    [conditions, playerConditions],
  )

  const sortSpec = useMemo(
    () => schema.default_sort.map((s) => ({ field: s.field, direction: s.direction })),
    [schema.default_sort],
  )

  const { data: compareData, isLoading: compareLoading } = useQuery({
    queryKey: ['compare-data', datasetId, allConditions, sortSpec, compareMode],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: allConditions,
        sort: sortSpec,
        page: 1,
        page_size: selectedPlayers.length * (compareMode === 'season' ? 10 : 18),
        columns: schema.default_columns,
      }),
    enabled: selectedPlayers.length > 0 && !!schema,
  })

  const handlePlayerSelect = (playerName: string) => {
    const current = selectedPlayers
    const isSelected = current.includes(playerName)
    const next = isSelected ? current.filter((p) => p !== playerName) : [...current, playerName].slice(0, 4)
    setPlayerFilters([
      { def: { id: 'player_compare', field: 'player_display_name', label: 'Compare Players', type: 'multi_select', category: 'identity', depends_on: [], description: '' }, value: next },
    ])
  }

  const groupedColumns = useMemo(() => {
    const map = new Map<string, ColumnMeta[]>()
    for (const col of schema.columns) {
      if (!map.has(col.category)) map.set(col.category, [])
      map.get(col.category)!.push(col)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [schema.columns])

  return (
    <div className="flex flex-col gap-4 h-full">
      {detailPlayer ? (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <button
              onClick={() => setDetailPlayer(null)}
              className="rounded-lg border border-white/10 bg-slate-900/60 px-2.5 py-1.5 text-sm text-slate-300 hover:bg-slate-800/80"
            >
              ← Back
            </button>
            <h3 className="text-lg font-semibold text-white">Player Detail: {detailPlayer}</h3>
          </div>
          <PlayerDetail
            datasetId={datasetId}
            schema={schema as DatasetSchema}
            playerName={detailPlayer}
          />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Users className="h-5 w-5" />
            Player Comparison
          </h3>
          <button
            onClick={() => setCompareMode((m) => (m === 'season' ? 'weekly' : 'season'))}
            className="rounded-lg border border-white/10 bg-slate-900/60 px-3 py-1.5 text-sm transition hover:bg-slate-800/80"
          >
            {compareMode === 'season' ? 'Weekly View' : 'Season View'}
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Select Players to Compare (max 4)
          </label>
          <div className="relative">
            <select
              value=""
              onChange={(e) => e.target.value && handlePlayerSelect(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20 appearance-none pr-10"
            >
              <option value="" disabled selected>
                Search for a player…
              </option>
              {availablePlayers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.position}, {p.team})
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
          </div>
        </div>

        {selectedPlayers.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {selectedPlayers.map((name) => (
              <span key={name} className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/20 px-2.5 py-1 text-xs font-medium text-blue-200 ring-1 ring-blue-400/40">
                {name}
                <button
                  type="button"
                  onClick={() => handlePlayerSelect(name)}
                  className="hover:text-blue-400"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setDetailPlayer(name)}
                  className="ml-1 rounded p-0.5 text-slate-400 hover:text-slate-200 hover:bg-white/5"
                  title={`View ${name} detail`}
                >
                  <BarChart3 className="h-3.5 w-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        {selectedPlayers.length > 0 && compareData && (
          <div className="overflow-auto rounded-xl border border-white/10 bg-slate-900/40">
            <table className="min-w-full border-collapse text-sm">
              <thead className="sticky top-0 z-[1] bg-slate-900/95 backdrop-blur-md">
                <tr className="border-b border-white/10">
                  <th className="whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Stat
                  </th>
                  {selectedPlayers.map((name) => (
                    <th key={name} className="whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupedColumns.map(([category, cols]) => (
                  <>
                    <tr>
                      <td colSpan={selectedPlayers.length + 1} className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-950/40 border-t border-white/5">
                        {FILTER_CATEGORIES[category] ?? category}
                      </td>
                    </tr>
                    {cols.map((col) => {
                      const rows = compareData.rows
                      return (
                        <tr key={col.id} className="border-b border-white/5">
                          <td className="whitespace-nowrap px-3 py-2.5 text-slate-300 group relative">
                            <span className="flex items-center gap-1">
                              {col.label}
                              <StatTooltip column={col} />
                            </span>
                          </td>
                          {selectedPlayers.map((name) => {
                            const row = rows.find((r) => String(r.player_display_name) === name)
                            const val = row?.[col.id]
                            return (
                              <td key={name} className="whitespace-nowrap px-3 py-2.5 text-slate-200 font-mono text-sm">
                                {val != null ? formatCell(val) : '—'}
                              </td>
                            )
                          })}
                        </tr>
                      )
                    })}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedPlayers.length > 0 && !compareData && !compareLoading && (
          <div className="text-center py-8 text-slate-500">
            No data found for selected players
          </div>
        )}

{compareLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
          </div>
        )}
      </div>
      )}
    </div>
  )
}