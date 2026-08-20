import { useQuery } from '@tanstack/react-query'
import { BarChart2, Table2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchSchema, queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import {
  advancedColumnsFor,
  basicColumnsFor,
  fantasyColumnsFor,
  FANTASY_SORT,
  getStatFamily,
  POSITION_PILLS,
  type StatTab,
} from '../lib/statViews'
import type { ActiveFilter, FilterCondition, SortSpec } from '../types'
import type { UrlState } from '../hooks/useUrlState'
import type { NavOptions } from './HomeView'
import { ColumnPicker } from './ColumnPicker'
import { DataTable, type SortState } from './DataTable'
import { ExpandablePanel } from './ExpandablePanel'
import { FilterPanel } from './FilterPanel'
import { MobileFilterButton, MobileFilterDrawer } from './MobileFilterDrawer'
import { PlayerDetail } from './PlayerDetail'
import { PositionPills } from './PositionPills'
import { StatTabs } from './StatTabs'
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
  const [sorting, setSorting] = useState<SortState[]>([])
  const [page, setPage] = useState(restored?.page ?? 1)
  const [chartView, setChartView] = useState(restored?.chartView ?? false)
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false)

  const datasetId = granularity === 'week' ? 'player_weekly' : 'player_season'

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ['schema', datasetId],
    queryFn: () => fetchSchema(datasetId),
  })

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
    if (!schema) return
    setActiveFilters((current) =>
      current
        .map((f) => {
          const next = schema.filters.find((d) => d.id === f.def.id)
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
    enabled: !!schema && visibleColumns.length > 0,
  })

  useEffect(() => setPage(1), [datasetId, positionId, statTab, activeFilters])

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
          def: schema?.filters.find((d) => d.field === f.field) ?? {
            id: f.field, field: f.field, label: f.field, type: 'multi_select' as const, category: 'other', depends_on: [],
          },
          value: f.value,
        })),
      )
    }
    window.addEventListener('load-saved-query', handleLoad as EventListener)
    return () => window.removeEventListener('load-saved-query', handleLoad as EventListener)
  }, [schema])

  const totalPages = queryData ? Math.max(1, Math.ceil(queryData.total / PAGE_SIZE)) : 1

  if (detailPlayer && schema) {
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setDetailPlayer(null)}
          className="text-sm text-slate-400 transition hover:text-white"
        >
          ← Back to Players
        </button>
        <PlayerDetail datasetId={datasetId} schema={schema} playerName={detailPlayer} />
      </div>
    )
  }

  const filterDefsForPanel = (schema?.filters ?? []).filter((f) => f.id !== 'position_group')

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="hidden w-[300px] shrink-0 lg:block">
        <ExpandablePanel title="Filters" className="h-full">
          {schema ? (
            <FilterPanel
              datasetId={datasetId}
              filterDefs={filterDefsForPanel}
              activeFilters={activeFilters}
              onChange={setActiveFilters}
            />
          ) : (
            <div className="h-full animate-pulse rounded-2xl bg-slate-900/40" />
          )}
          <div className="mt-4">
            <SavedQueriesPanel
              datasetId={datasetId}
              sorting={effectiveSort}
              visibleColumns={visibleColumns}
              filterConditions={filterConditions}
            />
          </div>
        </ExpandablePanel>
      </div>

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <PositionPills active={positionId} onChange={setPositionId} />
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1 text-sm">
              <button
                type="button"
                onClick={() => setGranularity('week')}
                className={`rounded-md px-2.5 py-1 transition ${granularity === 'week' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`}
              >
                Weekly
              </button>
              <button
                type="button"
                onClick={() => setGranularity('season')}
                className={`rounded-md px-2.5 py-1 transition ${granularity === 'season' ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`}
              >
                Season
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MobileFilterButton onClick={() => setMobileFiltersOpen(true)} activeCount={activeFilters.length} />
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
            {schema && queryData ? (
              <>
                <ExportButton datasetId={datasetId} filters={filterConditions} sort={effectiveSort} columns={visibleColumns} totalRows={queryData.total} />
                <ShareButton getShareableUrl={getShareableUrl} currentState={shareState} />
              </>
            ) : null}
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
              <button
                type="button"
                onClick={() => setChartView(false)}
                className={`rounded-md p-1.5 transition ${!chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`}
                title="Table"
              >
                <Table2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setChartView(true)}
                className={`rounded-md p-1.5 transition ${chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`}
                title="Chart"
              >
                <BarChart2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {queryError && <ErrorBanner error={queryError} />}

        {schemaLoading || !schema ? (
          <div className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/30">
            <div className="text-center">
              <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
              <p className="text-sm text-slate-400">Loading player data…</p>
            </div>
          </div>
        ) : chartView ? (
          <StatCharts schema={schema} queryData={queryData} visibleColumns={visibleColumns} />
        ) : (
          <>
            <ExpandablePanel title="Players">
              <DataTable
                rows={queryData?.rows ?? []}
                columns={queryData?.columns ?? visibleColumns}
                columnMeta={schema.columns}
                sorting={sorting}
                onSortingChange={(next) => {
                  setSorting(next)
                  setManualSort(true)
                }}
                loading={isFetching}
                pinFirstColumn
                onRowClick={(row) => {
                  const name = String(row.player_display_name ?? '')
                  if (name) setDetailPlayer(name)
                }}
                rowLabel={(row) => `View ${String(row.player_display_name ?? '')}`}
              />
            </ExpandablePanel>

            {queryData && <DataQualityIndicator datasetId={datasetId} filters={filterConditions} totalRows={queryData.total} />}
            {queryData && <QuickStats rows={queryData.rows} columns={queryData.columns} />}

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-slate-900/40 px-4 py-3 text-sm">
              <span className="text-slate-400">{queryData ? `${queryData.total.toLocaleString()} matching rows` : '—'}</span>
              <div className="flex items-center gap-2">
                <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-white/10 px-3 py-1.5 text-slate-300 transition hover:bg-white/5 disabled:opacity-40">
                  Previous
                </button>
                <span className="text-slate-400">Page {page} of {totalPages}</span>
                <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-white/10 px-3 py-1.5 text-slate-300 transition hover:bg-white/5 disabled:opacity-40">
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <MobileFilterDrawer open={mobileFiltersOpen} onClose={() => setMobileFiltersOpen(false)}>
        {schema ? (
          <FilterPanel
            datasetId={datasetId}
            filterDefs={filterDefsForPanel}
            activeFilters={activeFilters}
            onChange={setActiveFilters}
          />
        ) : null}
      </MobileFilterDrawer>
    </div>
  )
}

