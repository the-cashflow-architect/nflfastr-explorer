import { Users, X, ChevronDown, Shield, Target } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import { formatCell } from '../lib/filters'
import type { ActiveFilter, ColumnMeta, FilterDef, SortSpec } from '../types'
import { FILTER_CATEGORIES } from '../types'
import { StatTooltip } from './StatTooltip'

interface TeamCompareProps {
  datasetId: string
  schema: {
    columns: ColumnMeta[]
    filters: FilterDef[]
    default_columns: string[]
    default_sort: SortSpec[]
  }
  activeFilters: ActiveFilter[]
}

export function TeamCompare({ datasetId, schema, activeFilters }: TeamCompareProps) {
  const [teamFilters, setTeamFilters] = useState<ActiveFilter[]>([])
  const [compareMode, setCompareMode] = useState<'offense' | 'defense' | 'overall'>('overall')

  const conditions = useMemo(
    () => activeFiltersToConditions([...activeFilters, ...teamFilters]),
    [activeFilters, teamFilters],
  )

  const teamField = compareMode === 'offense' ? 'posteam' : compareMode === 'defense' ? 'defteam' : 'team'
  const teamLabel = compareMode === 'offense' ? 'Offense' : compareMode === 'defense' ? 'Defense' : 'Team'

  const { data: teamsData } = useQuery({
    queryKey: ['compare-teams', datasetId, conditions, teamField],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: conditions,
        sort: [{ field: teamField, direction: 'asc' }],
        page: 1,
        page_size: 500,
        columns: [teamField],
      }),
    enabled: !!schema,
  })

  const availableTeams = useMemo(() => {
    if (!teamsData) return []
    const seen = new Set<string>()
    return teamsData.rows
      .filter((row) => {
        const team = String(row[teamField] ?? '')
        if (!team || seen.has(team)) return false
        seen.add(team)
        return true
      })
      .map((row) => String(row[teamField]))
      .sort()
  }, [teamsData, teamField])

  const selectedTeams = teamFilters
    .filter((f) => f.def.id === 'team_compare')
    .flatMap((f) => (f.value as string[] ?? []))

  const teamConditions = useMemo(() => {
    if (selectedTeams.length === 0) return []
    return [{ field: teamField, operator: 'in' as const, value: selectedTeams }]
  }, [selectedTeams, teamField])

  const allConditions = useMemo(
    () => [...conditions, ...teamConditions],
    [conditions, teamConditions],
  )

  const sortSpec = useMemo(
    () => schema.default_sort.map((s) => ({ field: s.field, direction: s.direction })),
    [schema.default_sort],
  )

  const { data: compareData, isLoading: compareLoading } = useQuery({
    queryKey: ['team-compare-data', datasetId, allConditions, sortSpec, compareMode],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: allConditions,
        sort: sortSpec,
        page: 1,
        page_size: selectedTeams.length * 20,
        columns: schema.default_columns,
      }),
    enabled: selectedTeams.length > 0 && !!schema,
  })

  const handleTeamSelect = (teamName: string) => {
    const current = selectedTeams
    const isSelected = current.includes(teamName)
    const next = isSelected ? current.filter((t) => t !== teamName) : [...current, teamName].slice(0, 4)
    setTeamFilters([
      { def: { id: 'team_compare', field: teamField, label: `Compare ${teamLabel}s`, type: 'multi_select', category: 'team', depends_on: [], description: '' }, value: next },
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
      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            {compareMode === 'offense' ? <Target className="h-5 w-5" /> : compareMode === 'defense' ? <Shield className="h-5 w-5" /> : <Users className="h-5 w-5" />}
            Team Comparison
          </h3>
          <div className="flex gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
            {(['overall', 'offense', 'defense'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setCompareMode(mode)}
                className={`rounded-md px-3 py-1.5 text-sm transition capitalize ${
                  compareMode === mode
                    ? 'bg-blue-500/20 text-blue-200'
                    : 'text-slate-300 hover:text-white hover:bg-white/5'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Select {teamLabel}s to Compare (max 4)
          </label>
          <div className="relative">
            <select
              value=""
              onChange={(e) => e.target.value && handleTeamSelect(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20 appearance-none pr-10"
            >
              <option value="" disabled selected>
                Search for a {teamLabel.toLowerCase()}…
              </option>
              {availableTeams.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
          </div>
        </div>

        {selectedTeams.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {selectedTeams.map((name) => (
              <span key={name} className="inline-flex items-center gap-1.5 rounded-full bg-green-500/20 px-2.5 py-1 text-xs font-medium text-green-200 ring-1 ring-green-400/40">
                {name}
                <button
                  type="button"
                  onClick={() => handleTeamSelect(name)}
                  className="hover:text-green-400"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        {selectedTeams.length > 0 && compareData && (
          <div className="overflow-auto rounded-xl border border-white/10 bg-slate-900/40">
            <table className="min-w-full border-collapse text-sm">
              <thead className="sticky top-0 z-[1] bg-slate-900/95 backdrop-blur-md">
                <tr className="border-b border-white/10">
                  <th className="whitespace-nowrap px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Stat
                  </th>
                  {selectedTeams.map((name) => (
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
                      <td colSpan={selectedTeams.length + 1} className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-950/40 border-t border-white/5">
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
                          {selectedTeams.map((name) => {
                            const row = rows.find((r) => String(r[teamField]) === name)
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

        {selectedTeams.length > 0 && !compareData && !compareLoading && (
          <div className="text-center py-8 text-slate-500">
            No data found for selected teams
          </div>
        )}

        {compareLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
          </div>
        )}
      </div>
    </div>
  )
}