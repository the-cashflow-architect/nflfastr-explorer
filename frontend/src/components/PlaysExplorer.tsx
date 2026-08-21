import { useQuery } from '@tanstack/react-query'
import { BarChart2, Bookmark, Table2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchSchema, queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import { buildFilterDefs } from '../lib/filterDefs'
import { PLAY_QUICK_SUGGESTIONS } from '../lib/quickFilterSuggestions'
import type { ActiveFilter, FilterCondition, SortSpec } from '../types'
import type { UrlState } from '../hooks/useUrlState'
import { ColumnPicker } from './ColumnPicker'
import { DataQualityIndicator } from './DataQualityIndicator'
import { DataTable, type SortState } from './DataTable'
import { ExpandablePanel } from './ExpandablePanel'
import { ErrorBanner } from './ErrorBanner'
import { ExportButton } from './ExportButton'
import { FilterBar } from './FilterBar'
import { QuickStats } from './QuickStats'
import { SavedQueriesPanel } from './SavedQueriesPanel'
import { ShareButton } from './ShareButton'
import { StatCharts } from './StatCharts'
import { TimeFilter } from './TimeFilter'

interface PlaysExplorerProps {
  urlState: UrlState | null
  isRestoring: boolean
  updateUrl: (state: UrlState, replace?: boolean) => void
  getShareableUrl: (state: UrlState) => string
  /** Jump to that team's players — clicking a team code (offense or defense) in a play row. */
  onTeamClick?: (team: string) => void
}

const PAGE_SIZE = 50
const DATASET_ID = 'play_by_play'
const LINKABLE_COLUMNS = ['posteam', 'defteam']

export function PlaysExplorer({ urlState, isRestoring, updateUrl, getShareableUrl, onTeamClick }: PlaysExplorerProps) {
  const restored = urlState?.route === 'plays' ? urlState : null

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ['schema', DATASET_ID],
    queryFn: () => fetchSchema(DATASET_ID),
  })

  // Every filterable field on the dataset, not just the handful the backend
  // hand-curates: team/down/etc. come from the schema, every other numeric
  // or flag column (yards_gained, epa, touchdown, ...) is generated. Season
  // and week get their own always-visible TimeFilter row instead of a
  // chip, so they're excluded here to avoid showing up twice.
  const allFilterDefs = useMemo(() => {
    if (!schema) return []
    const backendDefs = schema.filters.filter((f) => f.id !== 'season' && f.id !== 'week')
    return buildFilterDefs(schema.columns, backendDefs)
  }, [schema])

  const seasonDef = schema?.filters.find((f) => f.id === 'season') ?? null
  const weekDef = schema?.filters.find((f) => f.id === 'week') ?? null

  // The full universe of filter defs, including season/week — used only to
  // re-point active filters at the right def object on saved-query loads.
  const remapDefs = useMemo(() => {
    if (!schema) return []
    return buildFilterDefs(schema.columns, schema.filters)
  }, [schema])

  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [visibleColumns, setVisibleColumns] = useState<string[]>(restored?.columns ?? [])
  const [sorting, setSorting] = useState<SortState[]>(
    restored?.sort.map((s) => ({ id: s.field, desc: s.direction === 'desc' })) ?? [],
  )
  const [page, setPage] = useState(restored?.page ?? 1)
  const [chartView, setChartView] = useState(restored?.chartView ?? false)
  const [customPickerOpen, setCustomPickerOpen] = useState(false)
  const [savedOpen, setSavedOpen] = useState(false)

  useEffect(() => {
    if (schema && visibleColumns.length === 0) {
      setVisibleColumns(schema.default_columns)
      if (sorting.length === 0) {
        setSorting(schema.default_sort.map((s) => ({ id: s.field, desc: s.direction === 'desc' })))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema])

  const filterConditions = activeFiltersToConditions(activeFilters)
  const sortSpec: SortSpec[] = sorting.map((s) => ({ field: s.id, direction: s.desc ? 'desc' : 'asc' }))

  const { data: queryData, isFetching, error: queryError } = useQuery({
    queryKey: ['plays-query', filterConditions, sortSpec, page, visibleColumns],
    queryFn: () =>
      queryDataset(DATASET_ID, {
        filters: filterConditions,
        sort: sortSpec,
        page,
        page_size: PAGE_SIZE,
        columns: visibleColumns,
      }),
    enabled: !!schema && visibleColumns.length > 0,
  })

  const activeFiltersKey = JSON.stringify(activeFilters)
  useEffect(() => setPage(1), [activeFiltersKey])

  const shareState: UrlState = {
    route: 'plays',
    playerGranularity: 'week',
    position: 'all',
    statTab: 'basic',
    filters: filterConditions,
    sort: sortSpec,
    columns: visibleColumns,
    page,
    chartView,
  }
  useEffect(() => {
    if (!isRestoring) updateUrl(shareState, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filterConditions), JSON.stringify(sortSpec), JSON.stringify(visibleColumns), page, chartView, isRestoring])

  useEffect(() => {
    const handleLoad = (event: CustomEvent) => {
      const { filters, sort, visibleColumns: cols } = event.detail
      setVisibleColumns(cols)
      setSorting((sort as SortSpec[]).map((s) => ({ id: s.field, desc: s.direction === 'desc' })))
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

  const totalPages = queryData ? Math.max(1, Math.ceil(queryData.total / PAGE_SIZE)) : 1

  return (
    <section className="flex min-w-0 flex-1 flex-col gap-3">
      {schema ? (
        <TimeFilter
          datasetId={DATASET_ID}
          seasonDef={seasonDef}
          weekDef={weekDef}
          activeFilters={activeFilters}
          onChange={setActiveFilters}
        />
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white light:text-slate-900">{schema?.name ?? 'Loading…'}</h2>
          <p className="text-xs text-slate-400 light:text-slate-500">{schema?.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {schema ? (
            <ColumnPicker
              allColumns={schema.columns}
              selected={visibleColumns}
              onChange={setVisibleColumns}
              open={customPickerOpen}
              onOpenChange={setCustomPickerOpen}
            />
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
                    datasetId={DATASET_ID}
                    sorting={sortSpec}
                    visibleColumns={visibleColumns}
                    filterConditions={filterConditions}
                  />
                </div>
              </>
            ) : null}
          </div>
          {schema && queryData ? (
            <>
              <ExportButton datasetId={DATASET_ID} filters={filterConditions} sort={sortSpec} columns={visibleColumns} totalRows={queryData.total} />
              <ShareButton getShareableUrl={getShareableUrl} currentState={shareState} />
            </>
          ) : null}
          <div className="flex items-center gap-1 rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white p-1">
            <button type="button" onClick={() => setChartView(false)} className={`rounded-md p-1.5 transition ${!chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`} title="Table">
              <Table2 className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setChartView(true)} className={`rounded-md p-1.5 transition ${chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 light:text-slate-500 hover:text-white'}`} title="Chart">
              <BarChart2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {schema ? (
        <FilterBar
          datasetId={DATASET_ID}
          allDefs={allFilterDefs}
          activeFilters={activeFilters}
          onChange={setActiveFilters}
          quickSuggestions={PLAY_QUICK_SUGGESTIONS}
        />
      ) : null}

      {queryError && <ErrorBanner error={queryError} />}

      {schemaLoading || !schema ? (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 light:border-slate-200 bg-slate-900/30 light:bg-slate-100/70">
          <div className="text-center">
            <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400" />
            <p className="text-sm text-slate-400 light:text-slate-500">Loading play-by-play data…</p>
          </div>
        </div>
      ) : chartView ? (
        <StatCharts schema={schema} queryData={queryData} visibleColumns={visibleColumns} />
      ) : (
        <>
          <ExpandablePanel title="Plays">
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
              pinFirstColumn
              rankOffset={(page - 1) * PAGE_SIZE}
              linkableColumns={onTeamClick ? LINKABLE_COLUMNS : undefined}
              onCellClick={
                onTeamClick
                  ? (colId, row) => {
                      const team = row[colId]
                      if (typeof team === 'string' && team) onTeamClick(team)
                    }
                  : undefined
              }
            />
          </ExpandablePanel>

          {queryData && <DataQualityIndicator datasetId={DATASET_ID} filters={filterConditions} totalRows={queryData.total} />}
          {queryData && <QuickStats rows={queryData.rows} columns={queryData.columns} />}

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white px-4 py-3 text-sm">
            <span className="text-slate-400 light:text-slate-500">{queryData ? `${queryData.total.toLocaleString()} matching rows` : '—'}</span>
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
