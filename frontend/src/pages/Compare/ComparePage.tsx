import { Search, UserPlus, X } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  usePlayerHub,
  usePlayerIndex,
  usePlayerPercentiles,
  type PlayerHub,
  type PlayerPercentiles,
} from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { PlayerLink } from '../../components/ui/EntityLink'
import { ComputedByUs, Empty } from '../../components/ui/Honesty'
import { PageHeader, PrimaryAction, Section, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { num, ordinal, percent } from '../../design/format'

/**
 * Two to six players, side by side.
 *
 * Bars rather than a radar: a radar chart's area is a function of the arbitrary
 * order of its axes, and past two players the shapes overlap into mud. A sorted
 * list of bars is readable at six and stays honest about what is being compared.
 *
 * The comparison is assembled from the same percentile endpoint the player hub
 * uses, so a number here and a number there cannot disagree. The cost of that is
 * printed rather than hidden: each player's percentile is measured inside *his
 * own* cohort — their position group, their scope — so the cohort line under every
 * player is part of the comparison, not decoration.
 */

const MAX_ENTITIES = 6

type Metric = NonNullable<PlayerPercentiles['metrics']>[number]

interface Entity {
  id: string
  hub: PlayerHub | undefined
  percentiles: PlayerPercentiles | undefined
  loading: boolean
  error: unknown
}

function shortName(hub: PlayerHub | undefined, id: string): string {
  const name = hub?.identity.display_name
  if (!name) return id
  const parts = name.split(' ')
  return parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(' ')}` : name
}

/** Units come from the payload; the decimals for each are decided once, here. */
function metricValue(metric: Metric | undefined): string {
  if (!metric || metric.value === null || metric.value === undefined) return '—'
  switch (metric.unit) {
    case 'percent':
      return percent(metric.value, 1)
    case 'epa':
      return num(metric.value, 3)
    case 'yards':
      return num(metric.value, 1)
    case 'count':
      return num(metric.value, 0)
    default:
      return num(metric.value, 1)
  }
}

export function ComparePage() {
  const [params, setParams] = useSearchParams()

  // `entities` is what a player hub's Compare button writes; `players` is the
  // canonical spelling. Both are read, and the canonical one is written back.
  const ids = (params.get('players') ?? params.get('entities') ?? '')
    .split(',')
    .map((id) => id.trim())
    .filter(Boolean)
    .slice(0, MAX_ENTITIES)

  const scope = params.get('scope') === 'season' ? 'season' : 'career'

  const hub0 = usePlayerHub(ids[0])
  const hub1 = usePlayerHub(ids[1])
  const hub2 = usePlayerHub(ids[2])
  const hub3 = usePlayerHub(ids[3])
  const hub4 = usePlayerHub(ids[4])
  const hub5 = usePlayerHub(ids[5])
  const hubs = [hub0, hub1, hub2, hub3, hub4, hub5]

  // Which seasons can be compared is a fact about the players on screen, not a
  // range typed here: it is the seasons they actually have rows for. Six short
  // lists, so it is cheaper to rebuild than to memoise.
  const seasons = (() => {
    const set = new Set<number>()
    for (const hub of hubs) {
      for (const row of hub.data?.career_regular?.rows ?? []) set.add(row.season)
    }
    return Array.from(set).sort((a, b) => b - a)
  })()

  const seasonParam = params.get('season')
  const season = scope === 'season' ? (seasonParam ?? (seasons.length ? String(seasons[0]) : null)) : 'career'
  // With no season resolved yet there is nothing honest to request, so the
  // percentile calls wait rather than quietly answering for the career.
  const gate = (id: string | undefined) => (season ? id : undefined)
  const query = { season: season ?? 'career' }

  const pct0 = usePlayerPercentiles(gate(ids[0]), query)
  const pct1 = usePlayerPercentiles(gate(ids[1]), query)
  const pct2 = usePlayerPercentiles(gate(ids[2]), query)
  const pct3 = usePlayerPercentiles(gate(ids[3]), query)
  const pct4 = usePlayerPercentiles(gate(ids[4]), query)
  const pct5 = usePlayerPercentiles(gate(ids[5]), query)
  const pcts = [pct0, pct1, pct2, pct3, pct4, pct5]

  const entities: Entity[] = ids.map((id, index) => ({
    id,
    hub: hubs[index].data,
    percentiles: pcts[index].data,
    loading: hubs[index].isLoading || pcts[index].isLoading,
    error: hubs[index].error ?? pcts[index].error,
  }))

  const setIds = (next: string[]) => {
    const search = new URLSearchParams(params)
    search.delete('entities')
    if (next.length) search.set('players', next.join(','))
    else search.delete('players')
    setParams(search, { replace: true })
  }

  const set = (key: string, value: string | null) => {
    const search = new URLSearchParams(params)
    if (value === null) search.delete(key)
    else search.set(key, value)
    setParams(search, { replace: true })
  }

  // Every metric anyone here has, ordered so the ones everybody has come first.
  const union = (() => {
    const order: string[] = []
    const byId = new Map<string, { metric: Metric; count: number }>()
    for (const entity of entities) {
      for (const metric of entity.percentiles?.metrics ?? []) {
        const existing = byId.get(metric.id)
        if (existing) existing.count += 1
        else {
          byId.set(metric.id, { metric, count: 1 })
          order.push(metric.id)
        }
      }
    }
    return order
      .map((id) => byId.get(id) as { metric: Metric; count: number })
      .sort((a, b) => b.count - a.count)
  })()

  const withData = entities.filter((entity) => entity.percentiles?.metrics?.length).length
  const shared = union.filter((row) => row.count === withData && withData > 0)
  const chosen = params.get('metrics')?.split(',').filter(Boolean) ?? null
  const visible = chosen
    ? union.filter((row) => chosen.includes(row.metric.id))
    : shared.length
      ? shared
      : union

  const view = params.get('view') === 'table' ? 'table' : 'bars'
  const anyLoading = entities.some((entity) => entity.loading)
  const firstError = entities.find((entity) => entity.error)?.error

  return (
    <>
      <PageHeader
        title="Compare"
        meta="Two to six players, on the same cohort percentiles the player pages use."
        action={<AddEntity ids={ids} onAdd={(id) => setIds([...ids, id])} />}
      />

      <div className="mt-4">
        {ids.length ? (
          <ul className="mb-3 flex flex-wrap gap-2">
            {entities.map((entity) => (
              <li
                key={entity.id}
                className="flex items-center gap-2 rounded-md border border-line px-2 py-1 text-[12px]"
              >
                <PlayerLink id={entity.id} name={entity.hub?.identity.display_name ?? entity.id} />
                <span className="text-ink-3">
                  {[entity.hub?.identity.position, entity.hub?.identity.team].filter(Boolean).join(' · ')}
                </span>
                <button
                  type="button"
                  onClick={() => setIds(ids.filter((id) => id !== entity.id))}
                  aria-label={`Remove ${entity.hub?.identity.display_name ?? entity.id}`}
                  className="motion-state rounded p-0.5 text-ink-3 hover:text-ink"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {ids.length < 2 ? (
          <Empty>
            {ids.length === 0
              ? 'Add two players to compare them. Every player page has a Compare button that starts here with that player already in.'
              : 'One more player and the bars have something to sit against.'}
          </Empty>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <Segmented
                ariaLabel="Scope"
                options={[
                  { value: 'career', label: 'Career' },
                  { value: 'season', label: 'Single season' },
                ]}
                value={scope}
                onChange={(next) => set('scope', next === 'career' ? null : next)}
              />
              {scope === 'season' && seasons.length ? (
                <label className="text-[12px]">
                  <span className="mr-1.5 text-[11px] uppercase tracking-[0.04em] text-ink-3">Season</span>
                  <select
                    value={season ?? ''}
                    onChange={(event) => set('season', event.target.value)}
                    className="rounded-md border border-line bg-raised px-2 py-1 text-[12px]"
                  >
                    {seasons.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <Segmented
                ariaLabel="How to read the comparison"
                options={[
                  { value: 'bars', label: 'Bars' },
                  { value: 'table', label: 'Table' },
                ]}
                value={view}
                onChange={(next) => set('view', next === 'bars' ? null : next)}
              />
            </div>

            <QueryBoundary
              isLoading={anyLoading}
              error={firstError}
              onRetry={() => {
                for (const hub of hubs) void hub.refetch()
                for (const pct of pcts) void pct.refetch()
              }}
            >
              {visible.length === 0 ? (
                <Empty>
                  None of these players has a qualified cohort in this scope, so there is nothing to line up.
                  Try career scope, or a season each of them played.
                </Empty>
              ) : (
                <>
                  {view === 'bars' ? (
                    <BarsView entities={entities} rows={visible} />
                  ) : (
                    <TableView entities={entities} rows={visible} />
                  )}

                  <p className="mt-3 text-[11px] leading-4 text-ink-3">
                    {shared.length} of {union.length}{' '}
                    {union.length === 1 ? 'metric is' : 'metrics are'} measured for every player here; the
                    rest show an em dash where a position does not produce that stat. Each percentile is
                    measured inside that player&rsquo;s own cohort, listed below.
                  </p>

                  <CohortLegend entities={entities} />

                  <Section
                    title="Metrics shown"
                    collapsible
                    defaultCollapsed
                    count={`${visible.length} of ${union.length}`}
                    pageKey="compare"
                    sectionKey="metrics"
                  >
                    <div className="mb-2 flex flex-wrap gap-1">
                      {union.map((row) => {
                        const on = visible.some((entry) => entry.metric.id === row.metric.id)
                        return (
                          <button
                            key={row.metric.id}
                            type="button"
                            aria-pressed={on}
                            onClick={() => {
                              const current = visible.map((entry) => entry.metric.id)
                              const next = on
                                ? current.filter((id) => id !== row.metric.id)
                                : [...current, row.metric.id]
                              set('metrics', next.length ? next.join(',') : null)
                            }}
                            className={`motion-state rounded border px-1.5 py-0.5 text-[11px] ${
                              on ? 'border-line-strong text-ink' : 'border-line text-ink-3'
                            }`}
                          >
                            {row.metric.label}
                          </button>
                        )
                      })}
                    </div>
                    {chosen ? (
                      <button
                        type="button"
                        onClick={() => set('metrics', null)}
                        className="motion-state text-[11px] text-ink-3 hover:text-ink"
                      >
                        Back to the metrics they all share
                      </button>
                    ) : null}
                  </Section>
                </>
              )}
            </QueryBoundary>
          </>
        )}
      </div>
    </>
  )
}

function BarsView({ entities, rows }: { entities: Entity[]; rows: { metric: Metric }[] }) {
  return (
    <div className="space-y-4">
      {rows.map(({ metric }) => (
        <div key={metric.id}>
          <div className="mb-1 flex items-baseline gap-1.5">
            <h3 className="text-[12px] font-medium text-ink-2">{metric.label}</h3>
            {metric.computed_by_us ? (
              <ComputedByUs
                formula={metric.note ?? 'Percentile against a qualified cohort of the same position group.'}
                anchor="percentiles"
              />
            ) : null}
            {metric.coverage_note ? (
              <span className="text-[11px] text-ink-3">{metric.coverage_note}</span>
            ) : null}
          </div>
          {entities.map((entity) => {
            const own = entity.percentiles?.metrics?.find((candidate) => candidate.id === metric.id)
            const percentile = own?.percentile ?? null
            return (
              <div
                key={entity.id}
                className="grid grid-cols-[minmax(0,8rem)_1fr_auto] items-center gap-3 py-0.5"
              >
                <span className="truncate text-[11px] text-ink-3">{shortName(entity.hub, entity.id)}</span>
                <div className="relative h-2 rounded-full bg-track">
                  {percentile !== null ? (
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-ink-2"
                      style={{ width: `${Math.max(1, Math.min(100, percentile))}%` }}
                    />
                  ) : null}
                  {/* The median tick is what turns a bar into a comparison. */}
                  <div className="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong" aria-hidden />
                </div>
                <span className="whitespace-nowrap text-right text-[12px]">
                  {metricValue(own)}
                  {percentile !== null ? (
                    <span className="ml-2 text-[11px] text-ink-3">{ordinal(Math.round(percentile))}</span>
                  ) : null}
                </span>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

interface TableRow {
  metric: Metric
  values: { entity: Entity; own: Metric | undefined }[]
}

function TableView({ entities, rows }: { entities: Entity[]; rows: { metric: Metric }[] }) {
  const tableRows: TableRow[] = rows.map(({ metric }) => ({
    metric,
    values: entities.map((entity) => ({
      entity,
      own: entity.percentiles?.metrics?.find((candidate) => candidate.id === metric.id),
    })),
  }))

  const columns: Column<TableRow>[] = [
    {
      id: 'metric',
      header: 'Metric',
      render: (row) => row.metric.label,
      sortValue: (row) => row.metric.label,
    },
    ...entities.map<Column<TableRow>>((entity, index) => ({
      id: entity.id,
      header: shortName(entity.hub, entity.id),
      help: entity.hub?.identity.display_name ?? undefined,
      align: 'right',
      sortValue: (row) => row.values[index].own?.value ?? null,
      render: (row) => {
        const own = row.values[index].own
        return (
          <span className="whitespace-nowrap">
            {metricValue(own)}
            {own?.percentile != null ? (
              <span className="ml-2 text-[11px] text-ink-3">{ordinal(Math.round(own.percentile))}</span>
            ) : null}
          </span>
        )
      },
    })),
  ]

  return (
    <DataTable
      rows={tableRows}
      columns={columns}
      rowKey={(row) => row.metric.id}
      emptyMessage="No shared metrics for these players in this scope."
      caption="Value, then the percentile inside that player's own cohort."
    />
  )
}

function CohortLegend({ entities }: { entities: Entity[] }) {
  return (
    <ul className="mt-2 space-y-0.5">
      {entities.map((entity) => {
        const cohort = entity.percentiles?.cohort
        const name = entity.hub?.identity.display_name ?? entity.id
        if (!cohort) {
          return (
            <li key={entity.id} className="text-[11px] text-ink-3">
              {name} — no qualified cohort in this scope.
            </li>
          )
        }
        return (
          <li key={entity.id} className="text-[11px] leading-4 text-ink-3">
            {name} — {[cohort.position_group, cohort.season].filter(Boolean).join(', ')} ·{' '}
            {cohort.n.toLocaleString()} qualified · {cohort.qualification}
            {entity.percentiles?.in_cohort === false
              ? ' This player is below that bar, so the percentile is where they would fall, not a standing inside it.'
              : null}
          </li>
        )
      })}
    </ul>
  )
}

/** The page's one accent action: the field that puts another player in. */
function AddEntity({ ids, onAdd }: { ids: string[]; onAdd: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const full = ids.length >= MAX_ENTITIES

  const results = usePlayerIndex({ q: term.trim().length >= 2 ? term.trim() : null, page_size: 8 })

  if (full) {
    return (
      <p className="max-w-[14rem] text-right text-[11px] text-ink-3">
        Six is the most that stays readable side by side. Remove one to add another.
      </p>
    )
  }

  if (!open) {
    return (
      <PrimaryAction onClick={() => setOpen(true)}>
        <UserPlus className="h-4 w-4" aria-hidden />
        Add player
      </PrimaryAction>
    )
  }

  const rows = (results.data?.rows ?? []).filter((row) => !ids.includes(row.gsis_id))

  return (
    <div className="relative w-64">
      <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-ink-3" aria-hidden />
      <input
        autoFocus
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        onBlur={() => {
          if (!term) setOpen(false)
        }}
        placeholder="Search a player by name"
        aria-label="Search a player by name"
        className="w-full rounded-md border border-line bg-raised py-1.5 pl-8 pr-2 text-[12px] outline-none"
      />
      {term.trim().length >= 2 ? (
        <div className="absolute right-0 z-30 mt-1 w-72 rounded-md border border-line bg-raised p-1 shadow-lg">
          {results.error ? (
            <p className="px-2 py-1.5 text-[12px] text-ink-3">
              Could not reach the player index — this is not &ldquo;no matches&rdquo;.
            </p>
          ) : results.isLoading ? (
            <p className="px-2 py-1.5 text-[12px] text-ink-3">Searching…</p>
          ) : rows.length === 0 ? (
            <p className="px-2 py-1.5 text-[12px] text-ink-3">
              No player on file matches &ldquo;{term.trim()}&rdquo;.
            </p>
          ) : (
            rows.map((row) => (
              <button
                key={row.gsis_id}
                type="button"
                // Mouse-down fires before the input's blur, so the pick lands.
                onMouseDown={(event) => {
                  event.preventDefault()
                  onAdd(row.gsis_id)
                  setTerm('')
                  setOpen(false)
                }}
                className="motion-state block w-full rounded px-2 py-1 text-left text-[12px] hover:bg-row-hover"
              >
                {row.display_name ?? row.gsis_id}
                <span className="ml-1.5 text-[11px] text-ink-3">
                  {[row.position, row.latest_team, row.first_season && row.last_season
                    ? `${row.first_season}–${row.last_season}`
                    : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
