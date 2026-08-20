import { useQuery } from '@tanstack/react-query'
import { BarChart2, Table2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchSchema, queryDataset } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import { FILTER_PRESETS } from '../lib/presets'
import type { ActiveFilter, FilterCondition, SortSpec } from '../types'
import type { UrlState } from '../hooks/useUrlState'
import { ColumnPicker } from './ColumnPicker'
import { DataQualityIndicator } from './DataQualityIndicator'
import { DataTable, type SortState } from './DataTable'
import { ExpandablePanel } from './ExpandablePanel'
import { ErrorBanner } from './ErrorBanner'
import { ExportButton } from './ExportButton'
import { FilterPanel } from './FilterPanel'
import { MobileFilterButton, MobileFilterDrawer } from './MobileFilterDrawer'
import { PresetSelector } from './PresetSelector'
import { QuickStats } from './QuickStats'
import { SavedQueriesPanel } from './SavedQueriesPanel'
import { ShareButton } from './ShareButton'
import { StatCharts } from './StatCharts'

interface PlaysExplorerProps {
  urlState: UrlState | null
  isRestoring: boolean
  updateUrl: (state: UrlState, replace?: boolean) => void
  getShareableUrl: (state: UrlState) => string
}

const PAGE_SIZE = 50
const DATASET_ID = 'play_by_play'

export function PlaysExplorer({ urlState, isRestoring, updateUrl, getShareableUrl }: PlaysExplorerProps) {
  const restored = urlState?.route === 'plays' ? urlState : null

  const { data: schema, isLoading: schemaLoading } = useQuery({
    queryKey: ['schema', DATASET_ID],
    queryFn: () => fetchSchema(DATASET_ID),
  })

  const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>([])
  const [presetFilters, setPresetFilters] = useState<FilterCondition[]>([])
  const [visibleColumns, setVisibleColumns] = useState<string[]>(restored?.columns ?? [])
  const [sorting, setSorting] = useState<SortState[]>(
    restored?.sort.map((s) => ({ id: s.field, desc: s.direction === 'desc' })) ?? [],
  )
  const [page, setPage] = useState(restored?.page ?? 1)
  const [chartView, setChartView] = useState(restored?.chartView ?? false)
  const [customPickerOpen, setCustomPickerOpen] = useState(false)
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false)

  useEffect(() => {
    if (schema && visibleColumns.length === 0) {
      setVisibleColumns(schema.default_columns)
      if (sorting.length === 0) {
        setSorting(schema.default_sort.map((s) => ({ id: s.field, desc: s.direction === 'desc' })))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema])

  const filterConditions = [...activeFiltersToConditions(activeFilters), ...presetFilters]
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
  const presetFiltersKey = JSON.stringify(presetFilters)
  useEffect(() => setPage(1), [activeFiltersKey, presetFiltersKey])

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
          def: schema?.filters.find((d) => d.field === f.field) ?? {
            id: f.field, field: f.field, label: f.field, type: 'multi_select' as const, category: 'other', depends_on: [],
          },
          value: f.value,
        })),
      )
      setPresetFilters([])
    }
    window.addEventListener('load-saved-query', handleLoad as EventListener)
    return () => window.removeEventListener('load-saved-query', handleLoad as EventListener)
  }, [schema])

  const totalPages = queryData ? Math.max(1, Math.ceil(queryData.total / PAGE_SIZE)) : 1

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="hidden w-[300px] shrink-0 lg:block">
        <ExpandablePanel title="Filters" className="h-full">
          {schema ? (
            <FilterPanel
              datasetId={DATASET_ID}
              filterDefs={schema.filters}
              activeFilters={activeFilters}
              onChange={(filters) => {
                setActiveFilters(filters)
                setPage(1)
              }}
            />
          ) : (
            <div className="h-full animate-pulse rounded-2xl bg-slate-900/40" />
          )}
          <div className="mt-4">
            <SavedQueriesPanel datasetId={DATASET_ID} sorting={sortSpec} visibleColumns={visibleColumns} filterConditions={filterConditions} />
          </div>
        </ExpandablePanel>
      </div>

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <PresetSelector
          datasetId={DATASET_ID}
          presets={FILTER_PRESETS}
          onSelect={(filters) => {
            setPresetFilters(filters)
            setPage(1)
          }}
        />
        {presetFilters.length > 0 && (
          <button
            onClick={() => setPresetFilters([])}
            className="self-start rounded-lg border border-white/10 bg-slate-900/40 px-2 py-1 text-xs text-slate-400 hover:bg-white/5 hover:text-white"
          >
            Clear preset
          </button>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-white">{schema?.name ?? 'Loading…'}</h2>
            <p className="text-xs text-slate-400">{schema?.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <MobileFilterButton onClick={() => setMobileFiltersOpen(true)} activeCount={activeFilters.length} />
            {schema ? (
              <ColumnPicker
                allColumns={schema.columns}
                selected={visibleColumns}
                onChange={setVisibleColumns}
                open={customPickerOpen}
                onOpenChange={setCustomPickerOpen}
              />
            ) : null}
            {schema && queryData ? (
              <>
                <ExportButton datasetId={DATASET_ID} filters={filterConditions} sort={sortSpec} columns={visibleColumns} totalRows={queryData.total} />
                <ShareButton getShareableUrl={getShareableUrl} currentState={shareState} />
              </>
            ) : null}
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-slate-900/60 p-1">
              <button type="button" onClick={() => setChartView(false)} className={`rounded-md p-1.5 transition ${!chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`} title="Table">
                <Table2 className="h-4 w-4" />
              </button>
              <button type="button" onClick={() => setChartView(true)} className={`rounded-md p-1.5 transition ${chartView ? 'bg-blue-500/20 text-blue-200' : 'text-slate-400 hover:text-white'}`} title="Chart">
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
              <p className="text-sm text-slate-400">Loading play-by-play data…</p>
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
              />
            </ExpandablePanel>

            {queryData && <DataQualityIndicator datasetId={DATASET_ID} filters={filterConditions} totalRows={queryData.total} />}
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
            datasetId={DATASET_ID}
            filterDefs={schema.filters}
            activeFilters={activeFilters}
            onChange={(filters) => {
              setActiveFilters(filters)
              setPage(1)
            }}
          />
        ) : null}
      </MobileFilterDrawer>
    </div>
  )
}
