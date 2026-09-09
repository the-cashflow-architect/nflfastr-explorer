import { useQuery } from '@tanstack/react-query'
import { Download, Play } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  exportDataset,
  fetchDatasets,
  fetchFilterOptions,
  fetchRankings,
  fetchSchema,
  queryDataset,
} from '../../api/datasets'
import { FilterBar } from '../../components/finder/FilterBar'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { GameLink, PlayerLink, SeasonLink, TeamLink } from '../../components/ui/EntityLink'
import { Empty } from '../../components/ui/Honesty'
import { PageHeader, PrimaryAction, Section } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { num, stat } from '../../design/format'
import { buildFilterDefs, isNumeric } from '../../lib/filterDefs'
import { activeFiltersToConditions } from '../../lib/filters'
import { PLAY_QUICK_SUGGESTIONS } from '../../lib/quickFilterSuggestions'
import type {
  ActiveFilter,
  ColumnMeta,
  DatasetSummary,
  FilterDef,
  QueryResponse,
  SortSpec,
} from '../../types'
import { FILTER_CATEGORIES, HIDDEN_CATEGORIES } from '../../types'
import { ModeSelector, type FinderMode } from './ModeSelector'
import { SavedViews } from './SavedViews'

/**
 * The Finder: the generic query engine, driven entirely by the URL.
 *
 * Two rules shape this page and both are load-bearing.
 *
 * **It opens with one empty condition and a mode, and nothing else.** Ranking,
 * qualification, field and export controls exist only once a result set does.
 * A query builder that shows every control at once is a database console, and a
 * database console is a thing people bounce off rather than a thing they use.
 *
 * **Nothing runs until Run.** Conditions are edited as a draft; Run commits them
 * to the URL and the URL is what executes. That keeps the address bar an honest
 * record of the query on screen — copy it and you get this table, not something
 * close to it — and it stops a half-typed condition from firing a scan of a
 * quarter of a million plays.
 */

const PAGE_SIZE = 200

/** Readable URL spellings for the datasets the product links to by name. */
const MODE_SLUGS: Record<string, string> = {
  player_season: 'player_season',
  player_weekly: 'player_game',
  play_by_play: 'plays',
}

const modesFrom = (datasets: DatasetSummary[] | undefined): FinderMode[] =>
  (datasets ?? []).map((dataset) => ({
    slug: MODE_SLUGS[dataset.id] ?? dataset.id,
    datasetId: dataset.id,
    name: dataset.name,
    description: dataset.description,
    source: dataset.source,
  }))

/** Accepts either the URL slug or the raw dataset id, so both kinds of link resolve. */
const modeFor = (modes: FinderMode[], value: string | null): FinderMode | undefined =>
  modes.find((mode) => mode.slug === value) ?? modes.find((mode) => mode.datasetId === value)


/** Query-string keys this page owns that are not filters. */
const RESERVED = new Set([
  'mode',
  'run',
  'sort',
  'rank',
  'qualify',
  'qualify_min',
  'cols',
  'page',
  'season_min',
  'season_max',
])

/** Columns fetched for their links even when they are not on display. */
const LINK_KEYS = ['player_id', 'game_id', 'season']

const TEAM_COLUMNS = new Set(['recent_team', 'team', 'posteam', 'defteam', 'opponent_team'])
const NAME_COLUMNS = new Set(['player_display_name', 'player_name'])
/** Codes and identifiers, never quantities: a season is not "2,024". */
const UNGROUPED = new Set(['season', 'week', 'down', 'qtr', 'play_id'])

type Row = Record<string, unknown>

const RANGE_PATTERN = /^(-?[\d.]*)\.\.(-?[\d.]*)$/

function decodeValue(def: FilterDef, raw: string, numericFields: Set<string>): unknown {
  const asValue = (text: string): unknown =>
    numericFields.has(def.field) && text !== '' && Number.isFinite(Number(text)) ? Number(text) : text

  switch (def.type) {
    case 'multi_select':
      return raw.split(',').filter(Boolean).map(asValue)
    case 'single_select':
      return asValue(raw)
    case 'search':
      return raw
    case 'boolean':
      return raw === 'yes'
    case 'range': {
      const match = RANGE_PATTERN.exec(raw)
      if (!match) return null
      const min = match[1] === '' ? null : Number(match[1])
      const max = match[2] === '' ? null : Number(match[2])
      if (min === null && max === null) return null
      return { min, max }
    }
    default:
      return null
  }
}

function encodeValue(def: FilterDef, value: unknown): string | null {
  switch (def.type) {
    case 'multi_select':
      return Array.isArray(value) && value.length ? value.map(String).join(',') : null
    case 'single_select':
    case 'search':
      return value == null || value === '' ? null : String(value)
    case 'boolean':
      return value ? 'yes' : 'no'
    case 'range': {
      const range = value as { min?: number | null; max?: number | null }
      if (range?.min == null && range?.max == null) return null
      return `${range.min ?? ''}..${range.max ?? ''}`
    }
    default:
      return null
  }
}

/**
 * The URL is the query. Every parameter is read independently, so one this
 * build does not understand is dropped on its own rather than taking the view
 * down with it — which is the specific failure an opaque encoded blob cannot
 * survive.
 */
function decodeFilters(
  params: URLSearchParams,
  defs: FilterDef[],
  numericFields: Set<string>,
  seasons: number[],
): { filters: ActiveFilter[]; ignored: string[] } {
  const byId = new Map(defs.map((def) => [def.id, def]))
  const filters: ActiveFilter[] = []
  const ignored: string[] = []

  for (const [key, raw] of params.entries()) {
    if (RESERVED.has(key)) continue
    const def = byId.get(key)
    if (!def) {
      ignored.push(key)
      continue
    }
    const value = decodeValue(def, raw, numericFields)
    if (value !== null && value !== undefined && !(Array.isArray(value) && value.length === 0)) {
      filters.push({ def, value })
    }
  }

  // `season_min` / `season_max` are what leaderboards and index pages write.
  // The season filter is a list of real seasons, so the range is resolved
  // against the seasons the dataset actually holds rather than assumed.
  const seasonDef = byId.get('season')
  if (seasonDef && !params.get('season') && (params.get('season_min') || params.get('season_max'))) {
    const min = Number(params.get('season_min') ?? seasons[0])
    const max = Number(params.get('season_max') ?? seasons[seasons.length - 1])
    const picked = seasons.filter((season) => season >= min && season <= max)
    if (picked.length) filters.push({ def: seasonDef, value: picked })
  }

  return { filters, ignored }
}

function encodeFilters(filters: ActiveFilter[]): [string, string][] {
  const pairs: [string, string][] = []
  for (const { def, value } of filters) {
    const encoded = encodeValue(def, value)
    if (encoded !== null) pairs.push([def.id, encoded])
  }
  return pairs.sort(([a], [b]) => a.localeCompare(b))
}

function renderNumber(value: number, column: ColumnMeta | undefined): string {
  if (!column) return num(value, Number.isInteger(value) ? 0 : 2)
  if (UNGROUPED.has(column.id)) return String(value)
  if (Number.isInteger(value)) return num(value, 0)
  return stat(value, column.id)
}

export function FinderPage() {
  const [params, setParams] = useSearchParams()

  const datasets = useQuery({ queryKey: ['datasets'], queryFn: fetchDatasets, staleTime: 60 * 60 * 1000 })
  const modes = useMemo(() => modesFrom(datasets.data), [datasets.data])
  const requestedMode = params.get('mode')
  const mode = modeFor(modes, requestedMode) ?? modes[0]
  const datasetId = mode?.datasetId
  // A link can name a mode this server does not register. Falling back quietly
  // would show a different dataset's rows under the caller's heading.
  const unknownMode = !!requestedMode && modes.length > 0 && !modeFor(modes, requestedMode)

  const schema = useQuery({
    queryKey: ['dataset-schema', datasetId],
    queryFn: () => fetchSchema(datasetId as string),
    enabled: !!datasetId,
    staleTime: 60 * 60 * 1000,
  })

  // The mode's coverage window, read from the dataset's own season column —
  // the only source that cannot drift from what is loaded.
  const seasonOptions = useQuery({
    queryKey: ['dataset-seasons', datasetId],
    queryFn: () => fetchFilterOptions(datasetId as string, { field: 'season', filters: [], limit: 100 }),
    enabled: !!datasetId,
    staleTime: 60 * 60 * 1000,
  })
  const seasons = useMemo(
    () =>
      (seasonOptions.data?.options ?? [])
        .map((option) => Number(option))
        .filter((season) => Number.isFinite(season))
        .sort((a, b) => a - b),
    [seasonOptions.data],
  )

  const columnMeta = useMemo(
    () => new Map((schema.data?.columns ?? []).map((column) => [column.id, column])),
    [schema.data],
  )
  const numericFields = useMemo(
    () => new Set((schema.data?.columns ?? []).filter(isNumeric).map((column) => column.id)),
    [schema.data],
  )
  const defs = useMemo(
    () => (schema.data ? buildFilterDefs(schema.data.columns, schema.data.filters) : []),
    [schema.data],
  )

  const { filters: applied, ignored } = useMemo(
    () => decodeFilters(params, defs, numericFields, seasons),
    [params, defs, numericFields, seasons],
  )
  const appliedKey = useMemo(() => JSON.stringify(encodeFilters(applied)), [applied])

  // The chips are a draft until Run. Re-seeding on an external URL change (a
  // saved view, the back button, a link from another page) is done during
  // render rather than in an effect so the bar never paints last query's chips.
  const [draft, setDraft] = useState<{ key: string; filters: ActiveFilter[] }>({
    key: appliedKey,
    filters: applied,
  })
  if (draft.key !== appliedKey) setDraft({ key: appliedKey, filters: applied })

  const hasRun = params.get('run') === '1'
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)

  const defaultSort = schema.data?.default_sort ?? []
  const sortParam = params.get('sort')
  const sort: SortSpec[] = sortParam
    ? [
        {
          field: sortParam.startsWith('-') ? sortParam.slice(1) : sortParam,
          direction: sortParam.startsWith('-') ? 'desc' : 'asc',
        },
      ]
    : defaultSort
  const sortField = sort[0]?.field
  const sortIsNumeric = !!sortField && numericFields.has(sortField)

  const selected = useMemo(() => {
    const requested = params.get('cols')?.split(',').filter(Boolean) ?? []
    const valid = requested.filter((id) => columnMeta.has(id))
    return valid.length ? valid : (schema.data?.default_columns ?? [])
  }, [params, columnMeta, schema.data])

  // Identity keys ride along so names and games can link; they are not shown
  // unless they were chosen, and the export sends only what is on screen.
  const requestColumns = useMemo(() => {
    const set = new Set(selected)
    for (const key of LINK_KEYS) if (columnMeta.has(key)) set.add(key)
    return Array.from(set)
  }, [selected, columnMeta])

  const rankOn = params.get('rank') === '1' && sortIsNumeric
  const qualifyField = params.get('qualify')
  const qualifyMin = params.get('qualify_min') ? Number(params.get('qualify_min')) : null
  const qualifies = rankOn && qualifyField && columnMeta.has(qualifyField) && qualifyMin != null

  const conditions = useMemo(() => activeFiltersToConditions(applied), [applied])

  const ready = hasRun && !!datasetId && !!schema.data && seasonOptions.isSuccess
  const results = useQuery({
    queryKey: [
      'finder',
      datasetId,
      conditions,
      sort,
      page,
      requestColumns,
      rankOn ? sortField : null,
      qualifies ? [qualifyField, qualifyMin] : null,
    ],
    enabled: ready,
    queryFn: (): Promise<QueryResponse> => {
      const body = { filters: conditions, sort, page, page_size: PAGE_SIZE, columns: requestColumns }
      if (rankOn && sortField) {
        return fetchRankings(datasetId as string, {
          ...body,
          rank_fields: [sortField],
          qualify_field: qualifies ? qualifyField : null,
          qualify_min: qualifies ? qualifyMin : null,
        })
      }
      return queryDataset(datasetId as string, body)
    },
  })

  const setQuery = (next: URLSearchParams, options?: { push?: boolean }) =>
    setParams(next, { replace: !options?.push })

  /** A filter-level change keeps the rest of the view and does not push history. */
  const patch = (changes: Record<string, string | null>, options?: { push?: boolean }) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key)
      else next.set(key, value)
    }
    if (!('page' in changes)) next.delete('page')
    setQuery(next, options)
  }

  const run = () => {
    const next = new URLSearchParams()
    if (mode) next.set('mode', mode.slug)
    for (const [key, value] of encodeFilters(draft.filters)) next.set(key, value)
    for (const key of ['sort', 'rank', 'qualify', 'qualify_min', 'cols']) {
      const value = params.get(key)
      if (value) next.set(key, value)
    }
    next.set('run', '1')
    // A new query is a new place: pushing means Back returns to the last one.
    setQuery(next, { push: true })
  }

  const changeMode = (slug: string) => {
    // Fields, filters and sort all belong to one dataset; carrying them across
    // would silently drop most of them.
    setQuery(new URLSearchParams({ mode: slug }), { push: true })
  }

  const dirty = JSON.stringify(encodeFilters(draft.filters)) !== appliedKey

  const suggestions = useMemo(() => {
    const ids = new Set(defs.map((def) => def.id))
    return PLAY_QUICK_SUGGESTIONS.filter((suggestion) =>
      suggestion.filters.every((filter) => ids.has(filter.defId)),
    )
  }, [defs])

  const coverage = seasons.length ? { from: seasons[0], to: seasons[seasons.length - 1] } : null

  return (
    <>
      <PageHeader
        title="Finder"
        meta="Query the datasets directly. Every condition, sort and field is in the address bar."
      />

      <div className="mt-4">
        <QueryBoundary
          isLoading={datasets.isLoading || schema.isLoading}
          error={datasets.error ?? schema.error}
          onRetry={() => void (datasets.error ? datasets.refetch() : schema.refetch())}
          isEmpty={!datasets.isLoading && modes.length === 0}
          emptyMessage="No datasets are registered on the server, so there is nothing to query yet."
        >
          {mode && schema.data ? (
            <>
              <ModeSelector
                modes={modes}
                value={mode.slug}
                onChange={changeMode}
                seasons={seasons}
                rowCount={schema.data.row_count}
              />

              {unknownMode ? (
                <p className="mb-2 text-[11px] text-ink-3">
                  This server does not register a “{requestedMode}” mode, so these are{' '}
                  {mode.name} rows.
                </p>
              ) : null}

              <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <FilterBar
                    datasetId={mode.datasetId}
                    allDefs={defs}
                    activeFilters={draft.filters}
                    onChange={(filters) => setDraft({ key: draft.key, filters })}
                    quickSuggestions={suggestions}
                  />
                </div>
                <PrimaryAction onClick={run}>
                  <Play className="h-4 w-4" aria-hidden />
                  Run
                </PrimaryAction>
              </div>

              {ignored.length ? (
                <p className="mb-2 text-[11px] text-ink-3">
                  {ignored.join(', ')} {ignored.length === 1 ? 'is not a field' : 'are not fields'} in{' '}
                  {mode.name}, so {ignored.length === 1 ? 'it was' : 'they were'} ignored. The rest of the
                  query ran as written.
                </p>
              ) : null}

              {!hasRun ? (
                <p className="mb-4 text-[12px] text-ink-3">
                  Add a condition, or run it as it stands to see every row in this mode.
                </p>
              ) : (
                <>
                  {dirty ? (
                    <p className="mb-2 text-[11px] text-ink-3">
                      Conditions have changed since this table was built. Run to update it.
                    </p>
                  ) : null}

                  <QueryBoundary
                    isLoading={results.isLoading}
                    error={results.error}
                    onRetry={() => void results.refetch()}
                  >
                    {results.data ? (
                      <ResultBlock
                        data={results.data}
                        mode={mode.name}
                        columnMeta={columnMeta}
                        numericFields={numericFields}
                        selected={selected}
                        allColumns={schema.data.columns}
                        defaultColumns={schema.data.default_columns}
                        sortField={sortField}
                        sortDesc={sort[0]?.direction !== 'asc'}
                        sortIsNumeric={sortIsNumeric}
                        rankOn={rankOn}
                        qualifyField={qualifies ? qualifyField : null}
                        qualifyMin={qualifies ? qualifyMin : null}
                        page={page}
                        coverage={coverage}
                        datasetId={mode.datasetId}
                        conditions={conditions}
                        sort={sort}
                        onPatch={patch}
                      />
                    ) : null}
                  </QueryBoundary>
                </>
              )}

              <SavedViews
                search={params.toString()}
                canSave={hasRun}
                onLoad={(search) => setQuery(new URLSearchParams(search), { push: true })}
              />
            </>
          ) : (
            <Empty>Pick a mode to start a query.</Empty>
          )}
        </QueryBoundary>
      </div>
    </>
  )
}

function ResultBlock({
  data,
  mode,
  columnMeta,
  numericFields,
  selected,
  allColumns,
  defaultColumns,
  sortField,
  sortDesc,
  sortIsNumeric,
  rankOn,
  qualifyField,
  qualifyMin,
  page,
  coverage,
  datasetId,
  conditions,
  sort,
  onPatch,
}: {
  data: QueryResponse
  mode: string
  columnMeta: Map<string, ColumnMeta>
  numericFields: Set<string>
  selected: string[]
  allColumns: ColumnMeta[]
  defaultColumns: string[]
  sortField: string | undefined
  sortDesc: boolean
  sortIsNumeric: boolean
  rankOn: boolean
  qualifyField: string | null
  qualifyMin: number | null
  page: number
  coverage: { from: number; to: number } | null
  datasetId: string
  conditions: ReturnType<typeof activeFiltersToConditions>
  sort: SortSpec[]
  onPatch: (changes: Record<string, string | null>, options?: { push?: boolean }) => void
}) {
  const rows: Row[] = data.rows
  const total = data.total
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const singlePage = total <= PAGE_SIZE
  const rankKey = sortField ? `__rank__${sortField}` : null
  const qualifiedCount = rows.length ? Number(rows[0].__total_qualified ?? 0) : 0

  const columns = useMemo<Column<Row>[]>(() => {
    const built: Column<Row>[] = []

    if (rankOn && rankKey) {
      built.push({
        id: rankKey,
        header: '#',
        help: `Standing on ${columnMeta.get(sortField as string)?.label ?? sortField} across all ${total.toLocaleString()} matching rows, not just this page.`,
        align: 'right',
        width: '3.5rem',
        // A row below the qualification bar gets no rank rather than the
        // hypothetical one the engine can compute: a number printed in a rank
        // column is read as a standing, and that one is not.
        render: (row) => (row.__qualifies === false ? '—' : num(Number(row[rankKey]), 0)),
      })
    }

    for (const id of data.columns) {
      if (id.startsWith('__')) continue
      if (!selected.includes(id)) continue
      const meta = columnMeta.get(id)
      const numeric = numericFields.has(id)
      built.push({
        id,
        header: meta?.label ?? id,
        help: meta?.description || undefined,
        align: numeric ? 'right' : 'left',
        // Sorting inside the table would only order the rows on this page,
        // which on a paged result is a lie. It is offered only when the whole
        // result set is on screen; otherwise the Sort control does it in SQL.
        sortValue: singlePage
          ? (row) => {
              const value = row[id]
              return typeof value === 'number' || typeof value === 'string' ? value : null
            }
          : undefined,
        render: (row) => renderCell(row, id, meta, numeric),
      })
    }
    return built
  }, [data.columns, selected, columnMeta, numericFields, rankOn, rankKey, sortField, singlePage, total])

  const sortLabel = sortField ? (columnMeta.get(sortField)?.label ?? sortField) : 'the dataset default'
  const qualifyLabel = qualifyField ? (columnMeta.get(qualifyField)?.label ?? qualifyField) : null

  return (
    <>
      <Section
        title="Ranking and fields"
        collapsible
        defaultCollapsed
        count={`Sorted by ${sortLabel} · ${selected.length} fields`}
        pageKey="finder"
        sectionKey="controls"
      >
        <RankingControls
          columnMeta={columnMeta}
          numericFields={numericFields}
          selected={selected}
          allColumns={allColumns}
          defaultColumns={defaultColumns}
          sortField={sortField}
          sortDesc={sortDesc}
          sortIsNumeric={sortIsNumeric}
          rankOn={rankOn}
          qualifyField={qualifyField}
          qualifyMin={qualifyMin}
          qualifiedCount={qualifiedCount}
          total={total}
          onPatch={onPatch}
        />
      </Section>

      <Section
        title="Results"
        note={`${total.toLocaleString()} matching ${total === 1 ? 'row' : 'rows'}`}
        controls={
          <ExportControls datasetId={datasetId} conditions={conditions} sort={sort} columns={selected} total={total} />
        }
      >
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(_row, index) => `${page}-${index}`}
          emptyMessage={
            <>
              Nothing in {mode}
              {coverage ? ` (${coverage.from}–${coverage.to})` : ''} matches these conditions. Loosen one, or widen
              the seasons.
            </>
          }
          caption={
            rankOn && qualifyLabel
              ? `Ranked among the ${qualifiedCount.toLocaleString()} rows with at least ${num(qualifyMin ?? 0, 0)} ${qualifyLabel}. Rows below that bar are listed without a rank.`
              : singlePage
                ? undefined
                : `Sorted by ${sortLabel} on the server, across all ${total.toLocaleString()} matching rows.`
          }
        />

        {pages > 1 ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-ink-3">
            <span>
              Rows {((page - 1) * PAGE_SIZE + 1).toLocaleString()}–
              {Math.min(page * PAGE_SIZE, total).toLocaleString()} of {total.toLocaleString()}
            </span>
            <div className="ml-auto flex gap-1">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => onPatch({ page: String(page - 1) })}
                className="motion-state rounded border border-line px-2 py-0.5 hover:border-line-strong disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= pages}
                onClick={() => onPatch({ page: String(page + 1) })}
                className="motion-state rounded border border-line px-2 py-0.5 hover:border-line-strong disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </Section>
    </>
  )
}

function renderCell(row: Row, id: string, meta: ColumnMeta | undefined, numeric: boolean): React.ReactNode {
  const value = row[id]
  // A blank is not a zero. Every gap prints as an em dash.
  if (value === null || value === undefined || value === '') return <span className="text-ink-3">—</span>

  if (NAME_COLUMNS.has(id)) {
    return <PlayerLink id={typeof row.player_id === 'string' ? row.player_id : null} name={String(value)} />
  }
  if (TEAM_COLUMNS.has(id)) {
    return <TeamLink abbr={String(value)} season={typeof row.season === 'number' ? row.season : undefined} />
  }
  if (id === 'game_id') {
    return <GameLink gameId={String(value)}>{String(value)}</GameLink>
  }
  if (id === 'season' && typeof value === 'number') {
    return <SeasonLink season={value} />
  }
  if (id === 'desc') {
    return (
      <span className="block max-w-[34rem] truncate" title={String(value)}>
        {String(value)}
      </span>
    )
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number' && numeric) return renderNumber(value, meta)
  return String(value)
}

function RankingControls({
  columnMeta,
  numericFields,
  selected,
  allColumns,
  defaultColumns,
  sortField,
  sortDesc,
  sortIsNumeric,
  rankOn,
  qualifyField,
  qualifyMin,
  qualifiedCount,
  total,
  onPatch,
}: {
  columnMeta: Map<string, ColumnMeta>
  numericFields: Set<string>
  selected: string[]
  allColumns: ColumnMeta[]
  defaultColumns: string[]
  sortField: string | undefined
  sortDesc: boolean
  sortIsNumeric: boolean
  rankOn: boolean
  qualifyField: string | null
  qualifyMin: number | null
  qualifiedCount: number
  total: number
  onPatch: (changes: Record<string, string | null>) => void
}) {
  const pickable = useMemo(
    () => allColumns.filter((column) => !HIDDEN_CATEGORIES.has(column.category)),
    [allColumns],
  )
  const grouped = useMemo(() => {
    const map = new Map<string, ColumnMeta[]>()
    for (const column of pickable) {
      const list = map.get(column.category) ?? []
      list.push(column)
      map.set(column.category, list)
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      (FILTER_CATEGORIES[a] ?? a).localeCompare(FILTER_CATEGORIES[b] ?? b),
    )
  }, [pickable])

  const toggleColumn = (id: string) => {
    const next = selected.includes(id) ? selected.filter((column) => column !== id) : [...selected, id]
    // A table with no fields is not a table.
    if (!next.length) return
    onPatch({ cols: next.join(',') })
  }

  const numericColumns = pickable.filter((column) => numericFields.has(column.id))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-[12px]">
          <span className="mb-1 block text-[11px] uppercase tracking-[0.04em] text-ink-3">Sort by</span>
          <select
            value={sortField ?? ''}
            onChange={(event) => onPatch({ sort: `${sortDesc ? '-' : ''}${event.target.value}` })}
            className="rounded-md border border-line bg-raised px-2 py-1 text-[12px]"
          >
            {sortField && !columnMeta.has(sortField) ? <option value={sortField}>{sortField}</option> : null}
            {pickable.map((column) => (
              <option key={column.id} value={column.id}>
                {column.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => onPatch({ sort: `${sortDesc ? '' : '-'}${sortField ?? ''}` })}
          disabled={!sortField}
          className="motion-state rounded-md border border-line px-2 py-1 text-[12px] hover:border-line-strong disabled:opacity-40"
        >
          {sortDesc ? 'Highest first' : 'Lowest first'}
        </button>

        <label className="flex items-center gap-1.5 text-[12px]">
          <input
            type="checkbox"
            checked={rankOn}
            disabled={!sortIsNumeric}
            onChange={(event) => onPatch({ rank: event.target.checked ? '1' : null })}
          />
          Rank column
        </label>
        {!sortIsNumeric ? (
          <span className="text-[11px] text-ink-3">A rank needs a numeric sort column.</span>
        ) : null}
      </div>

      {rankOn ? (
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[12px]">
            <span className="mb-1 block text-[11px] uppercase tracking-[0.04em] text-ink-3">
              Qualify on
            </span>
            <select
              value={qualifyField ?? ''}
              onChange={(event) => onPatch({ qualify: event.target.value || null })}
              className="rounded-md border border-line bg-raised px-2 py-1 text-[12px]"
            >
              <option value="">No qualification</option>
              {numericColumns.map((column) => (
                <option key={column.id} value={column.id}>
                  {column.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[12px]">
            <span className="mb-1 block text-[11px] uppercase tracking-[0.04em] text-ink-3">At least</span>
            <input
              type="number"
              value={qualifyMin ?? ''}
              disabled={!qualifyField}
              onChange={(event) => onPatch({ qualify_min: event.target.value || null })}
              className="w-24 rounded-md border border-line bg-raised px-2 py-1 text-[12px] disabled:opacity-40"
            />
          </label>
          {qualifyField && qualifyMin != null ? (
            <p className="text-[11px] text-ink-3">
              Ranked among rows with at least {num(qualifyMin, 0)}{' '}
              {columnMeta.get(qualifyField)?.label ?? qualifyField} — {qualifiedCount.toLocaleString()} of{' '}
              {total.toLocaleString()} matching rows qualify.
            </p>
          ) : (
            <p className="text-[11px] text-ink-3">
              Without a rule every matching row is ranked, including one-attempt seasons.
            </p>
          )}
        </div>
      ) : null}

      <div>
        <div className="mb-1 flex items-baseline gap-2">
          <p className="text-[11px] uppercase tracking-[0.04em] text-ink-3">Fields in this query</p>
          <button
            type="button"
            onClick={() => onPatch({ cols: null })}
            className="motion-state text-[11px] text-ink-3 hover:text-ink"
          >
            Reset to the {defaultColumns.length} default fields
          </button>
        </div>
        <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border border-line p-2">
          {grouped.map(([category, columns]) => (
            <div key={category}>
              <p className="mb-1 text-[11px] text-ink-3">{FILTER_CATEGORIES[category] ?? category}</p>
              <div className="flex flex-wrap gap-1">
                {columns.map((column) => {
                  const on = selected.includes(column.id)
                  return (
                    <button
                      key={column.id}
                      type="button"
                      onClick={() => toggleColumn(column.id)}
                      aria-pressed={on}
                      title={column.description}
                      className={`motion-state rounded border px-1.5 py-0.5 text-[11px] ${
                        on ? 'border-line-strong text-ink' : 'border-line text-ink-3'
                      }`}
                    >
                      {column.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ExportControls({
  datasetId,
  conditions,
  sort,
  columns,
  total,
}: {
  datasetId: string
  conditions: ReturnType<typeof activeFiltersToConditions>
  sort: SortSpec[]
  columns: string[]
  total: number
}) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const download = async (format: 'csv' | 'json') => {
    setBusy(true)
    setNote(null)
    try {
      const result = await exportDataset(datasetId, { filters: conditions, sort, columns, format })
      const url = URL.createObjectURL(result.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${datasetId}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
      // The cap is the server's, so it is reported from what came back rather
      // than from a number typed here.
      setNote(
        result.truncated && result.rows != null && result.matchingRows != null
          ? `Exported ${result.rows.toLocaleString()} of ${result.matchingRows.toLocaleString()} matching rows — the server caps a single export.`
          : `Exported ${(result.rows ?? total).toLocaleString()} rows.`,
      )
    } catch (error) {
      setNote(error instanceof Error ? error.message : 'The export did not complete.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-right">
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={busy || total === 0}
          onClick={() => void download('csv')}
          className="motion-state inline-flex items-center gap-1.5 rounded border border-line px-2 py-1 text-[12px] hover:border-line-strong disabled:opacity-40"
        >
          <Download className="h-4 w-4" aria-hidden />
          CSV
        </button>
        <button
          type="button"
          disabled={busy || total === 0}
          onClick={() => void download('json')}
          className="motion-state inline-flex items-center gap-1.5 rounded border border-line px-2 py-1 text-[12px] hover:border-line-strong disabled:opacity-40"
        >
          <Download className="h-4 w-4" aria-hidden />
          JSON
        </button>
      </div>
      <p className="mt-1 max-w-xs text-[11px] text-ink-3">
        {note ??
          (total === 0
            ? 'Nothing matches, so there is nothing to export.'
            : `${total.toLocaleString()} rows and ${columns.length} fields, capped by the server on large exports — we will say if yours was.`)}
      </p>
    </div>
  )
}
