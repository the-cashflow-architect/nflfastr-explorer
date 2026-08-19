import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, Database, Sparkles, Download, BarChart2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchDatasets, fetchSchema, queryDataset, exportDataset } from './api'
import { ColumnPicker } from './components/ColumnPicker'
import { DataTable, type SortState } from './components/DataTable'
import { FilterPanel } from './components/FilterPanel'
import { PlayerCompare } from './components/PlayerCompare'
import { TeamCompare } from './components/TeamCompare'
import { StatTrendChart, MultiStatTrend } from './components/StatTrendChart'
import { SavedQueriesPanel } from './components/SavedQueriesPanel'
import { ShareButton } from './components/ShareButton'
import { SortPanel } from './components/SortPanel'
import { useUrlState } from './hooks/useUrlState'
import { DataQualityIndicator } from './components/DataQualityIndicator'
import { QuickStats } from './components/QuickStats'
import { activeFiltersToConditions } from './lib/filters'
import type { ActiveFilter, ColumnMeta, DatasetSummary, FilterCondition, SortSpec } from './types'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

function ExplorerApp() {
  const [datasetId, setDatasetId] = useState('player_weekly')
  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [visibleColumns, setVisibleColumns] = useState<string[]>([])
  const [sorting, setSorting] = useState<SortState[]>([])
  const [page, setPage] = useState(1)
  const [viewMode, setViewMode] = useState<'explore' | 'compare' | 'team'>('explore')
  const [exploreView, setExploreView] = useState<'table' | 'chart'>('table')
  const pageSize = 50

  const { urlState, isRestoring, updateUrl, getShareableUrl } = useUrlState()

  // Restore state from URL on mount/navigation
  useEffect(() => {
    if (urlState && !isRestoring) {
      setDatasetId(urlState.datasetId)
      setActiveFilters(
        urlState.filters.map((f: FilterCondition) => ({
          def: { id: f.field, field: f.field, label: f.field, type: 'multi_select' as const, category: 'other', depends_on: [] },
          value: f.value,
        })),
      )
      setSorting(
        urlState.sort.map((s: SortSpec) => ({ id: s.field, desc: s.direction === 'desc' })),
      )
      setVisibleColumns(urlState.columns)
      setPage(urlState.page)
      setViewMode(urlState.viewMode)
      setExploreView(urlState.exploreView)
    }
  }, [urlState, isRestoring])

  // Update URL when state changes
  const currentState = useMemo(() => ({
    datasetId,
    filters: activeFiltersToConditions(activeFilters),
    sort: sorting.map((s) => ({ field: s.id, direction: s.desc ? 'desc' as const : 'asc' as const })),
    columns: visibleColumns,
    page,
    viewMode,
    exploreView,
  }), [datasetId, activeFilters, sorting, visibleColumns, page, viewMode, exploreView])

  useEffect(() => {
    if (!isRestoring) {
      updateUrl(currentState, true)
    }
  }, [currentState, isRestoring, updateUrl])

  const { data: datasets } = useQuery({
    queryKey: ['datasets'],
    queryFn: fetchDatasets,
  })

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ['schema', datasetId],
    queryFn: () => fetchSchema(datasetId),
  })

  useEffect(() => {
    if (schema) {
      setVisibleColumns(schema.default_columns)
      setSorting(schema.default_sort.map((s) => ({ id: s.field, desc: s.direction === 'desc' })))
      setActiveFilters([])
      setPage(1)
    }
  }, [schema, datasetId])

  // Load saved query from localStorage event
  useEffect(() => {
    const handleLoad = (event: CustomEvent) => {
      const { filters, sort, visibleColumns } = event.detail
      setActiveFilters(
        filters.map((f: FilterCondition) => ({
          def: { id: f.field, field: f.field, label: f.field, type: 'multi_select' as const, category: 'other', depends_on: [] },
          value: f.value,
        })),
      )
      setSorting(
        sort.map((s: SortSpec) => ({ id: s.field, desc: s.direction === 'desc' })),
      )
      setVisibleColumns(visibleColumns)
      setPage(1)
    }
    window.addEventListener('load-saved-query', handleLoad as EventListener)
    return () => window.removeEventListener('load-saved-query', handleLoad as EventListener)
  }, [])

  const filterConditions = useMemo(
    () => activeFiltersToConditions(activeFilters),
    [activeFilters],
  )

  const sortSpec = useMemo(
    () =>
      sorting.map((s) => ({
        field: s.id,
        direction: s.desc ? ('desc' as const) : ('asc' as const),
      })),
    [sorting],
  )

  const { data: queryData, isFetching } = useQuery({
    queryKey: ['query', datasetId, filterConditions, sortSpec, page, visibleColumns],
    queryFn: () =>
      queryDataset(datasetId, {
        filters: filterConditions,
        sort: sortSpec,
        page,
        page_size: pageSize,
        columns: visibleColumns.length ? visibleColumns : undefined,
      }),
    enabled: !!schema && visibleColumns.length > 0,
  })

  const totalPages = queryData ? Math.max(1, Math.ceil(queryData.total / pageSize)) : 1
  const currentDataset = datasets?.find((d) => d.id === datasetId)

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-white/10 bg-slate-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-4 lg:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 shadow-lg shadow-blue-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">nflfastR Explorer</h1>
              <p className="text-xs text-slate-400">
                nflverse data · smart filters · stat glossary
              </p>
            </div>
          </div>
          <div className="hidden items-center gap-4 text-xs text-slate-400 md:flex">
            <span className="inline-flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5" />
              {currentDataset?.row_count.toLocaleString() ?? '—'} rows
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              Live nflverse
            </span>
          </div>
        </div>

        <div className="mx-auto flex max-w-[1600px] gap-2 overflow-x-auto px-4 pb-3 lg:px-6">
          {(datasets ?? []).map((ds: DatasetSummary) => (
            <button
              key={ds.id}
              type="button"
              onClick={() => setDatasetId(ds.id)}
              className={`shrink-0 rounded-xl px-4 py-2 text-left transition ${
                datasetId === ds.id
                  ? 'bg-blue-500/20 text-blue-100 ring-1 ring-blue-400/40'
                  : 'bg-slate-900/50 text-slate-300 ring-1 ring-white/5 hover:bg-slate-800/80'
              }`}
            >
              <span className="block text-sm font-semibold">{ds.name}</span>
              <span className="block text-[11px] text-slate-400">{ds.row_count.toLocaleString()} rows</span>
            </button>
          ))}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1600px] flex-1 gap-4 overflow-hidden p-4 lg:p-6">
        <div className="hidden w-[320px] shrink-0 lg:block">
          {schema ? (
            <>
              <FilterPanel
                datasetId={datasetId}
                filterDefs={schema.filters}
                activeFilters={activeFilters}
                onChange={(filters) => {
                  setActiveFilters(filters)
                  setPage(1)
                }}
              />
              <SavedQueriesPanel
                datasetId={datasetId}
                sorting={sortSpec}
                visibleColumns={visibleColumns}
                filterConditions={filterConditions}
              />
              {viewMode === 'explore' && schema && (
                <div className="mt-4">
                  <SortPanel
                    sorting={sorting.map((s) => ({ field: s.id, direction: s.desc ? 'desc' as const : 'asc' as const }))}
                    onSortingChange={(next) => {
                      setSorting(next.map((s) => ({ id: s.field, desc: s.direction === 'desc' })))
                      setPage(1)
                    }}
                    columns={schema.columns}
                  />
                </div>
              )}
            </>
          ) : (
            <div className="h-full animate-pulse rounded-2xl bg-slate-900/40" />
          )}
        </div>

        <section className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">
                {schema?.name ?? 'Loading…'}
              </h2>
              <p className="text-xs text-slate-400">{schema?.description}</p>
            </div>
            <div className="flex items-center gap-2">
              {schema ? (
                <ColumnPicker
                  allColumns={schema.columns}
                  selected={visibleColumns}
                  onChange={setVisibleColumns}
                />
              ) : null}
              {schema && queryData && (
                <>
                  <ExportButton
                    datasetId={datasetId}
                    filters={filterConditions}
                    sort={sortSpec}
                    columns={visibleColumns}
                    totalRows={queryData.total}
                  />
                  <ShareButton
                    getShareableUrl={getShareableUrl}
                    currentState={currentState}
                  />
                </>
              )}
              {schema && datasetId !== 'play_by_play' && (
                <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
                  <button
                    type="button"
                    onClick={() => setViewMode('explore')}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      viewMode === 'explore'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-300 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    Explore
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('compare')}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      viewMode === 'compare'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-300 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    Player
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('team')}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      viewMode === 'team'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-300 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    Team
                  </button>
                </div>
              )}
              {schema && viewMode === 'explore' && (
                <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
                  <button
                    type="button"
                    onClick={() => setExploreView('table')}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      exploreView === 'table'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-300 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    Table
                  </button>
                  <button
                    type="button"
                    onClick={() => setExploreView('chart')}
                    className={`rounded-md px-3 py-1.5 text-sm transition ${
                      exploreView === 'chart'
                        ? 'bg-blue-500/20 text-blue-200'
                        : 'text-slate-300 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <BarChart2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          </div>

          {schemaLoading || !schema ? (
            <div className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/30">
              <div className="text-center">
                <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
                <p className="text-sm text-slate-400">Loading nflfastR data…</p>
              </div>
            </div>
) : (
                <>
                  {viewMode === 'explore' ? (
                    <>
                      {exploreView === 'table' ? (
                        <>
                          <DataTable
                            rows={queryData?.rows ?? []}
                            columns={queryData?.columns ?? visibleColumns}
                            columnMeta={schema.columns}
                            sorting={sorting}
                            onSortingChange={(next) => {
                              setSorting(next)
                              setPage(1)
                            }}
                            loading={isFetching}
                          />

                          {queryData && (
                            <DataQualityIndicator
                              datasetId={datasetId}
                              filters={filterConditions}
                              totalRows={queryData.total}
                            />
                          )}

                          {queryData && (
                            <QuickStats
                              rows={queryData.rows}
                              columns={queryData.columns}
                            />
                          )}

                          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-slate-900/40 px-4 py-3 text-sm">
                            <span className="text-slate-400">
                              {queryData
                                ? `${queryData.total.toLocaleString()} matching rows`
                                : '—'}
                            </span>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                disabled={page <= 1}
                                onClick={() => setPage((p) => p - 1)}
                                className="rounded-lg border border-white/10 px-3 py-1.5 text-slate-300 transition hover:bg-white/5 disabled:opacity-40"
                              >
                                Previous
                              </button>
                              <span className="text-slate-400">
                                Page {page} of {totalPages}
                              </span>
                              <button
                                type="button"
                                disabled={page >= totalPages}
                                onClick={() => setPage((p) => p + 1)}
                                className="rounded-lg border border-white/10 px-3 py-1.5 text-slate-300 transition hover:bg-white/5 disabled:opacity-40"
                              >
                                Next
                              </button>
                            </div>
                          </div>
                        </>
                      ) : (
                        <StatCharts
                          schema={schema}
                          queryData={queryData}
                          visibleColumns={visibleColumns}
                        />
                      )}
                    </>
                  ) : viewMode === 'compare' ? (
                    <PlayerCompare datasetId={datasetId} schema={schema} activeFilters={activeFilters} />
                  ) : (
                    <TeamCompare datasetId={datasetId} schema={schema} activeFilters={activeFilters} />
                  )}
                </>
              )}
        </section>
      </main>
    </div>
  )
}

function StatCharts({
  schema,
  queryData,
  visibleColumns,
}: {
  schema: {
    columns: ColumnMeta[]
    default_columns: string[]
    default_sort: SortSpec[]
  }
  queryData: { rows: Record<string, unknown>[]; total: number } | undefined
  visibleColumns: string[]
}) {
  const rows = queryData?.rows ?? []
  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        No data to chart. Adjust your filters.
      </div>
    )
  }

  // Determine x-axis field (season or week)
  const hasWeek = visibleColumns.includes('week')
  const xField = hasWeek ? 'week' : 'season'

  // Get numeric columns that are visible
  const numericColumns = visibleColumns.filter((colId) => {
    const meta = schema.columns.find((c) => c.id === colId)
    return meta && (meta.dtype.includes('INT') || meta.dtype.includes('FLOAT') || meta.dtype.includes('DOUBLE') || meta.dtype.includes('DECIMAL'))
  })

  // Default to key stats if no numeric columns selected
  const defaultStatKeys = ['epa', 'fantasy_points_ppr', 'passing_yards', 'rushing_yards', 'receiving_yards', 'cpoe', 'wpa']
  const chartStats = numericColumns.filter((c) => defaultStatKeys.includes(c)).slice(0, 4)
  const finalStats = chartStats.length > 0 ? chartStats : numericColumns.slice(0, 4)

  // Group by xField and aggregate (mean)
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

  if (aggregated.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        No numeric data available for selected columns
      </div>
    )
  }

  const statMetas = finalStats.map((s) => schema.columns.find((c) => c.id === s)).filter(Boolean) as ColumnMeta[]

  return (
    <div className="space-y-4">
      {statMetas.length === 1 ? (
        <StatTrendChart
          data={aggregated}
          xField="x"
          yField={statMetas[0].id}
          columnMeta={statMetas[0]}
        />
      ) : (
        <MultiStatTrend
          data={aggregated}
          xField="x"
          yFields={finalStats}
          columnsMeta={statMetas}
        />
      )}
    </div>
  )
}

function ExportButton({
  datasetId,
  filters,
  sort,
  columns,
  totalRows,
}: {
  datasetId: string
  filters: FilterCondition[]
  sort: SortSpec[]
  columns: string[]
  totalRows: number
}) {
  const [exporting, setExporting] = useState(false)
  const [format, setFormat] = useState<'csv' | 'json'>('csv')

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await exportDataset(datasetId, { filters, sort, columns, format })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${datasetId}_export.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Export failed:', err)
      alert('Export failed. Check console for details.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex items-center gap-1">
      <div className="flex items-center gap-0.5 rounded-lg border border-white/10 bg-slate-900/60 p-1">
        <button
          type="button"
          onClick={() => setFormat('csv')}
          className={`rounded-md px-2.5 py-1 text-xs transition ${
            format === 'csv'
              ? 'bg-blue-500/20 text-blue-200'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          CSV
        </button>
        <button
          type="button"
          onClick={() => setFormat('json')}
          className={`rounded-md px-2.5 py-1 text-xs transition ${
            format === 'json'
              ? 'bg-blue-500/20 text-blue-200'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          JSON
        </button>
      </div>
      <button
        type="button"
        onClick={handleExport}
        disabled={exporting || totalRows === 0}
        className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/80 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Download className="h-4 w-4" />
        Export ({totalRows.toLocaleString()})
      </button>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ExplorerApp />
    </QueryClientProvider>
  )
}
