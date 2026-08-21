import { useQuery } from '@tanstack/react-query'
import { BarChart2, Bookmark, CalendarRange, Table2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchSchema, fetchWeeklyBreakdown, queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import { buildFilterDefs, isNumeric } from '../lib/filterDefs'
import { quickSuggestionsFor } from '../lib/quickFilterSuggestions'
import {
  advancedColumnsFor,
  basicColumnsFor,
  fantasyColumnsFor,
  FANTASY_SORT,
  getStatFamily,
  POSITION_PILLS,
  type StatTab,
} from '../lib/statViews'
import type { ActiveFilter, ColumnMeta, FilterCondition, SortSpec } from '../types'
import type { UrlState } from '../hooks/useUrlState'
import type { NavOptions } from './HomeView'
import { ColumnPicker } from './ColumnPicker'
import { DataTable, type SortState } from './DataTable'
import { ExpandablePanel } from './ExpandablePanel'
import { FilterBar } from './FilterBar'
import { PlayerDetail } from './PlayerDetail'
import { PositionPills } from './PositionPills'
import { StatTabs } from './StatTabs'
import { TimeFilter } from './TimeFilter'
import { QuickStats } from './QuickStats'
import { DataQualityIndicator } from './DataQualityIndicator'
import { ErrorBanner } from './ErrorBanner'
import { SavedQueriesPanel } from './SavedQueriesPanel'
import { ShareButton } from './ShareButton'
import { StatCharts } from './StatCharts'
import { ExportButton } from './ExportButton'

interface PlayersExplorerProps {
  navOpts: NavOptions | null
  detailPlayer: string | null
  setDetailPlayer: (name: string | null) => void
  urlState: UrlState | null
  isRestoring: boolean
  updateUrl: (state: UrlState, replace?: boolean) => void
  getShareableUrl: (state: UrlState) => string
}

const PAGE_SIZE = 50

export function PlayersExplorer({
  navOpts,
  detailPlayer,
  setDetailPlayer,
  urlState,
  isRestoring,
  updateUrl,
  getShareableUrl,
}: PlayersExplorerProps) {
  const restored = urlState?.route === 'players' ? urlState : null

  const [granularity, setGranularity] = useState<'week' | 'season'>(restored?.playerGranularity ?? 'week')
  const [positionId, setPositionId] = useState(restored?.position ?? navOpts?.position ?? 'all')
  const [statTab, setStatTab] = useState<StatTab>(restored?.statTab ?? navOpts?.statTab ?? 'basic')
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [customColumns, setCustomColumns] = useState<string[] | null>(null)
  const [customPickerOpen, setCustomPickerOpen] = useState(false)
  const [savedOpen, setSavedOpen] = useState(false)
  const [sorting, setSorting] = useState<SortState[]>([])
  const [page, setPage] = useState(restored?.page ?? 1)
  const [chartView, setChartView] = useState(restored?.chartView ?? false)
  const [weeklyBreakdownField, setWeeklyBreakdownField] = useState<string | null>(null)

  const datasetId = granularity === 'week' ? 'player_weekly' : 'player_season'

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ['schema', datasetId],
    queryFn: () => fetchSchema(datasetId),
  })

  // Every filterable field on the dataset, not just the handful the backend
  // hand-curates: team/position/search fields come from the schema, every
  // other numeric or flag column is generated on the fly. Season and week
  // get their own always-visible TimeFilter row instead of a chip, so
  // they're excluded here to avoid showing up twice.
  const allFilterDefs = useMemo(() => {
    if (!schema) return []
    const backendDefs = schema.filters.filter((f) => f.id !== 'position_group' && f.id !== 'season' && f.id !== 'week')
    return buildFilterDefs(schema.columns, backendDefs)
  }, [schema])

  const seasonDef = schema?.filters.find((f) => f.id === 'season') ?? null
  const weekDef = schema?.filters.find((f) => f.id === 'week') ?? null

  // The full universe of filter defs (including season/week/position_group,
  // unlike allFilterDefs above) — used only to re-point active filters at
  // the right def object, never rendered as chips directly.
  const remapDefs = useMemo(() => {
    if (!schema) return []
    return buildFilterDefs(schema.columns, schema.filters)
  }, [schema])

  // Apply a team filter arriving from the Home page's "jump to a team" grid.
  useEffect(() => {
    if (navOpts?.team && schema) {
      const def = schema.filters.find((f) => f.id === 'team')
      if (def) setActiveFilters([{ def, value: [navOpts.team] }])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navOpts?.team, schema?.id])

  // Weekly and season data name some fields differently (season's team
  // column is "recent_team", not "team"; it has no per-game week or
  // opponent). Re-point each active filter at the new schema's FilterDef
  // when granularity changes, so a stale field name never reaches the API —
  // that would otherwise 500 rather than just returning no rows.
  useEffect(() => {
    if (!schema || remapDefs.length === 0) return
    setActiveFilters((current) =>
      current
        .map((f) => {
          const next = remapDefs.find((d) => d.id === f.def.id)
          return next ? { def: next, value: f.value } : null
        })
        .filter((f): f is ActiveFilter => f !== null),
    )
    // Only when the schema itself changes (i.e. granularity flipped) — not
    // on every activeFilters edit, which would fight the setter above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema?.id])

  const hasWeek = granularity === 'week'

  const family = getStatFamily(positionId)
  const advancedAvailable = advancedColumnsFor(positionId, hasWeek) != null

  useEffect(() => {
    if (statTab === 'advanced' && !advancedAvailable) setStatTab('basic')
  }, [advancedAvailable, statTab])

  const presetColumns = useMemo(() => {
    if (statTab === 'basic') return basicColumnsFor(positionId, hasWeek)
    if (statTab === 'advanced') return advancedColumnsFor(positionId, hasWeek) ?? basicColumnsFor(positionId, hasWeek)
    if (statTab === 'fantasy') return fantasyColumnsFor(hasWeek)
    return customColumns ?? basicColumnsFor(positionId, hasWeek)
  }, [statTab, positionId, hasWeek, customColumns])

  const visibleColumns = statTab === 'custom' && customColumns ? customColumns : presetColumns

  const presetSort: SortSpec[] = useMemo(() => {
    if (statTab === 'basic') return family.basicSort
    if (statTab === 'advanced') return family.advancedSort
    if (statTab === 'fantasy') return FANTASY_SORT
    return []
  }, [statTab, family])

  // Position/stat-tab changes reset explicit column sorting back to the
  // preset's natural order, unless the user has manually clicked a header.
  const [manualSort, setManualSort] = useState(false)
  useEffect(() => {
    setManualSort(false)
  }, [statTab, positionId])

  const effectiveSort: SortSpec[] = manualSort
    ? sorting.map((s) => ({ field: s.id, direction: s.desc ? 'desc' : 'asc' }))
    : presetSort

  const positionGroups = POSITION_PILLS.find((p) => p.id === positionId)?.positionGroups ?? []
  const positionFilterCondition: FilterCondition[] =
    positionGroups.length === 0 ? [] : [{ field: 'position_group', operator: 'in', value: positionGroups }]

  const filterConditions = useMemo(
    () => [...positionFilterCondition, ...activeFiltersToConditions(activeFilters)],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [positionId, activeFilters],
  )

  const { data: queryData, isFetching, error: queryError } = useQuery({
    queryKey: ['players-query', datasetId, filterConditions, effectiveSort, page, visibleColumns],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: filterConditions,
        sort: effectiveSort,
        page,
        page_size: PAGE_SIZE,
        columns: visibleColumns,
      }),
    enabled: !!schema && visibleColumns.length > 0 && !weeklyBreakdownField,
  })

  // A numeric stat, currently visible, that isn't itself an identity/team
  // column — the choices offered for "show this one broken out by week".
  // Only meaningful on the weekly dataset; season rows have no week to break
  // out.
  const weeklyBreakdownOptions = useMemo(() => {
    if (!hasWeek || !schema) return []
    return visibleColumns
      .map((id) => schema.columns.find((c) => c.id === id))
      .filter(
        (c): c is ColumnMeta =>
          !!c && isNumeric(c) && c.category !== 'identity' && c.category !== 'team' && c.category !== 'time',
      )
  }, [hasWeek, schema, visibleColumns])

  useEffect(() => {
    if (weeklyBreakdownField && !weeklyBreakdownOptions.some((c) => c.id === weeklyBreakdownField)) {
      setWeeklyBreakdownField(null)
    }
  }, [weeklyBreakdownOptions, weeklyBreakdownField])

  const breakdownActive = hasWeek && !!weeklyBreakdownField

  // Everything that identifies the row (season/name/position/team) stays a
  // single value per group; player name leads so it can be the pinned
  // column, matching the normal table. "opponent_team" is deliberately
  // excluded even though it's a "team"-category column — it changes every
  // week, so grouping by it would split one player into a separate row per
  // week instead of one row with a week per column (the exact bug that
  // made week 1 look "complete" and every other week look sparse: each
  // week's row was really a different opponent-specific group).
  const groupColumns = useMemo(() => {
    if (!breakdownActive || !schema) return []
    const cols = visibleColumns.filter((id) => {
      if (id === 'week' || id === 'opponent_team' || id === weeklyBreakdownField) return false
      const meta = schema.columns.find((c) => c.id === id)
      return id === 'season' || (meta && (meta.category === 'identity' || meta.category === 'team'))
    })
    const ordered = cols.includes('player_display_name')
      ? ['player_display_name', ...cols.filter((c) => c !== 'player_display_name')]
      : cols
    return ordered.length > 0 ? ordered : ['player_display_name']
  }, [breakdownActive, schema, visibleColumns, weeklyBreakdownField])

  // Every other visible stat stays in the table too, just summed across the
  // whole filtered range instead of split out per week. Opponent isn't a
  // stat and can't be summed, so it's dropped entirely from this view
  // rather than shown as a nonsensical total.
  const breakdownAggColumns = useMemo(() => {
    if (!breakdownActive) return []
    return visibleColumns.filter(
      (id) => id !== 'week' && id !== 'opponent_team' && id !== weeklyBreakdownField && !groupColumns.includes(id),
    )
  }, [breakdownActive, visibleColumns, weeklyBreakdownField, groupColumns])

  const { data: breakdownData, isFetching: breakdownFetching, error: breakdownError } = useQuery({
    queryKey: [
      'players-weekly-breakdown',
      datasetId,
      filterConditions,
      groupColumns,
      weeklyBreakdownField,
      breakdownAggColumns,
      effectiveSort,
      page,
    ],
    queryFn: () =>
      fetchWeeklyBreakdown(datasetId, {
        filters: filterConditions,
        group_columns: groupColumns,
        weekly_field: weeklyBreakdownField as string,
        agg_columns: breakdownAggColumns,
        sort: effectiveSort,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: breakdownActive && !!schema && groupColumns.length > 0,
  })

  const weeklyFieldMeta = schema?.columns.find((c) => c.id === weeklyBreakdownField) ?? null

  const breakdownColumns = useMemo(() => {
    if (!breakdownActive || !breakdownData) return []
    return [...groupColumns, ...breakdownData.weeks.map((w) => `week_${w}`), ...breakdownAggColumns]
  }, [breakdownActive, breakdownData, groupColumns, breakdownAggColumns])

  const breakdownColumnMeta = useMemo(() => {
    if (!schema) return []
    if (!breakdownActive || !breakdownData || !weeklyFieldMeta) return schema.columns
    const synthetic: ColumnMeta[] = breakdownData.weeks.map((w) => ({
      id: `week_${w}`,
      label: `Wk ${w}`,
      description: weeklyFieldMeta.description,
      formula: weeklyFieldMeta.formula,
      dtype: weeklyFieldMeta.dtype,
      category: weeklyFieldMeta.category,
    }))
    return [...schema.columns, ...synthetic]
  }, [schema, breakdownActive, breakdownData, weeklyFieldMeta])

  const breakdownColumnGroups = useMemo(() => {
    if (!breakdownActive || !breakdownData || !weeklyFieldMeta) return undefined
    return [{ label: weeklyFieldMeta.label, columnIds: breakdownData.weeks.map((w) => `week_${w}`) }]
  }, [breakdownActive, breakdownData, weeklyFieldMeta])

  useEffect(() => setPage(1), [datasetId, positionId, statTab, activeFilters, weeklyBreakdownField])

  // Persist to the URL so the current view is shareable.
  const shareState: UrlState = {
    route: 'players',
    playerGranularity: granularity,
    position: positionId,
    statTab,
    filters: filterConditions,
    sort: effectiveSort,
    columns: visibleColumns,
    page,
    chartView,
  }
  useEffect(() => {
    if (!isRestoring) updateUrl(shareState, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, positionId, statTab, JSON.stringify(filterConditions), JSON.stringify(effectiveSort), JSON.stringify(visibleColumns), page, chartView, isRestoring])

  useEffect(() => {
    const handleLoad = (event: CustomEvent) => {
      const { filters, sort, visibleColumns: cols } = event.detail
      setStatTab('custom')
      setCustomColumns(cols)
      setManualSort(true)
      setSorting(sort.map((s: SortSpec) => ({ id: s.field, desc: s.direction === 'desc' })))
      setActiveFilters(
        (filters as FilterCondition[]).map((f) => ({
          def: remapDefs.find((d) => d.field === f.field) ?? {
            id: f.field, field: f.field, label: f.field, type: 'multi_select' as const, category: 'other', depends_on: [],
          },
          value: f.value,
        })),
      )
    }
    window.addEventListener('load-saved-query', handleLoad as EventListener)
    return () => window.removeEventListener('load-saved-query', handleLoad as EventListener)
  }, [remapDefs])

  const activeTotal = breakdownActive ? breakdownData?.total : queryData?.total
  const totalPages = activeTotal != null ? Math.max(1, Math.ceil(activeTotal / PAGE_SIZE)) : 1

  if (detailPlayer && schema) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setDetailPlayer(null)}
          className="text-sm text-slate-400 light:text-slate-500 transition hover:text-white"
        >
          ← Back to Players
        </button>
        <PlayerDetail datasetId={datasetId} schema={schema} playerName={detailPlayer} />
      </div>
    )
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col gap-3">
      {schema ? (
        <TimeFilter
          datasetId={datasetId}
          seasonDef={seasonDef}
          weekDef={hasWeek ? weekDef : null}
          activeFilters={activeFilters}
          onChange={setActiveFilters}
        />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <PositionPills active={positionId} onChange={setPositionId} />
          <div className="flex items-center gap-1 rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white p-1 text-sm">
            <button
              type="button"
              onClick={() => setGranularity('week')}
              className={`rounded-md px-2.5 py-1 transition ${granularity === 'week' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`}
            >
              Weekly
            </button>
            <button
              type="button"
              onClick={() => setGranularity('season')}
              className={`rounded-md px-2.5 py-1 transition ${granularity === 'season' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`}
            >
              Season
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatTabs
            active={statTab}
            onChange={(tab) => {
              setStatTab(tab)
              if (tab === 'custom') {
                setCustomColumns((cur) => cur ?? basicColumnsFor(positionId, hasWeek))
                setCustomPickerOpen(true)
              }
            }}
            advancedDisabled={!advancedAvailable}
            advancedDisabledReason={family.advancedUnavailableReason}
          />
          {statTab === 'custom' && schema ? (
            <ColumnPicker
              allColumns={schema.columns}
              selected={visibleColumns}
              onChange={(cols) => setCustomColumns(cols)}
              open={customPickerOpen}
              onOpenChange={setCustomPickerOpen}
            />
          ) : null}
          {hasWeek && weeklyBreakdownOptions.length > 0 ? (
            <label className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white px-3 py-2 text-sm text-slate-300 light:text-slate-600">
              <CalendarRange className="h-4 w-4 text-slate-400 light:text-slate-500" />
              <select
                value={weeklyBreakdownField ?? ''}
                onChange={(e) => setWeeklyBreakdownField(e.target.value || null)}
                title="Break one stat out into a column per week, instead of one total"
                className="bg-transparent text-sm text-slate-200 light:text-slate-700 outline-none"
              >
                <option value="">Weekly breakdown: off</option>
                {weeklyBreakdownOptions.map((c) => (
                  <option key={c.id} value={c.id}>
                    Weekly: {c.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="relative">
            <button
              type="button"
              onClick={() => setSavedOpen((o) => !o)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white px-3 py-2 text-sm text-slate-200 light:text-slate-700 transition hover:bg-slate-800/80"
            >
              <Bookmark className="h-4 w-4" />
              Saved
            </button>
            {savedOpen ? (
              <>
                <button type="button" className="fixed inset-0 z-40" aria-label="Close" onClick={() => setSavedOpen(false)} />
                <div className="absolute right-0 z-50 mt-2 w-80 rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/95 light:bg-white/95 p-1 shadow-2xl backdrop-blur-xl">
                  <SavedQueriesPanel
                    datasetId={datasetId}
                    sorting={effectiveSort}
                    visibleColumns={visibleColumns}
                    filterConditions={filterConditions}
                  />
                </div>
              </>
            ) : null}
          </div>
          {schema && queryData && !breakdownActive ? (
            <>
              <ExportButton datasetId={datasetId} filters={filterConditions} sort={effectiveSort} columns={visibleColumns} totalRows={queryData.total} />
              <ShareButton getShareableUrl={getShareableUrl} currentState={shareState} />
            </>
          ) : null}
          <div className="flex items-center gap-1 rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white p-1">
            <button
              type="button"
              onClick={() => setChartView(false)}
              className={`rounded-md p-1.5 transition ${!chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`}
              title="Table"
            >
              <Table2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setChartView(true)}
              className={`rounded-md p-1.5 transition ${chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`}
              title="Chart"
            >
              <BarChart2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {schema ? (
        <FilterBar
          datasetId={datasetId}
          allDefs={allFilterDefs}
          activeFilters={activeFilters}
          onChange={setActiveFilters}
          quickSuggestions={quickSuggestionsFor(positionId)}
        />
      ) : null}

      {(breakdownActive ? breakdownError : queryError) ? (
        <ErrorBanner error={(breakdownActive ? breakdownError : queryError) as Error} />
      ) : null}

      {schemaLoading || !schema ? (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/30 light:bg-slate-100/70">
          <div className="text-center">
            <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
            <p className="text-sm text-slate-400 light:text-slate-500">Loading player data…</p>
          </div>
        </div>
      ) : chartView && !breakdownActive ? (
        <StatCharts schema={schema} queryData={queryData} visibleColumns={visibleColumns} />
      ) : (
        <>
          <ExpandablePanel title="Players">
            <DataTable
              rows={(breakdownActive ? breakdownData?.rows : queryData?.rows) ?? []}
              columns={(breakdownActive ? breakdownColumns : queryData?.columns) ?? visibleColumns}
              columnMeta={breakdownActive ? breakdownColumnMeta : schema.columns}
              columnGroups={breakdownActive ? breakdownColumnGroups : undefined}
              sorting={sorting}
              onSortingChange={(next) => {
                setSorting(next)
                setManualSort(true)
              }}
              loading={breakdownActive ? breakdownFetching : isFetching}
              pinFirstColumn
              rankOffset={(page - 1) * PAGE_SIZE}
              onRowClick={(row) => {
                const name = String(row.player_display_name ?? '')
                if (name) setDetailPlayer(name)
              }}
              rowLabel={(row) => `View ${String(row.player_display_name ?? '')}`}
            />
          </ExpandablePanel>

          {!breakdownActive && queryData ? (
            <DataQualityIndicator datasetId={datasetId} filters={filterConditions} totalRows={queryData.total} />
          ) : null}
          {breakdownActive && breakdownData ? (
            <QuickStats rows={breakdownData.rows} columns={breakdownColumns} />
          ) : !breakdownActive && queryData ? (
            <QuickStats rows={queryData.rows} columns={queryData.columns} />
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white px-4 py-3 text-sm">
            <span className="text-slate-400 light:text-slate-500">{activeTotal != null ? `${activeTotal.toLocaleString()} matching rows` : '—'}</span>
            <div className="flex items-center gap-2">
              <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-white/10 light:border-slate-200 px-3 py-1.5 text-slate-300 light:text-slate-600 transition hover:bg-white/5 disabled:opacity-40">
                Previous
              </button>
              <span className="text-slate-400 light:text-slate-500">Page {page} of {totalPages}</span>
              <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-white/10 light:border-slate-200 px-3 py-1.5 text-slate-300 light:text-slate-600 transition hover:bg-white/5 disabled:opacity-40">
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
