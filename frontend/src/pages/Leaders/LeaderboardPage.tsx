import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useLeaderboard, useLeadersIndex, useTeamIndex, type Leaderboard } from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { PageHeader, Segmented, Chip } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { SeasonLink, TeamLink } from '../../components/ui/EntityLink'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { decimalsFor, num, percent, signed } from '../../design/format'

/**
 * One ranked board. The two things that must never be missable on this page:
 * the era window (never "all-time" — our floor is 1999, and a rate board like
 * CPOE starts later still) and the qualification rule in plain words (a rate
 * board with no stated minimum is a list of people who attempted three passes).
 *
 * Both come from the payload, never from a constant here.
 */

const SCORING_KEY = 'gridiron.scoring'
const POSITION_GROUPS = ['QB', 'RB', 'FB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'SPEC', 'K', 'P']
const SCOPE_LABEL_FALLBACK: Record<string, string> = { career: 'Career', season: 'Single season', game: 'Single game' }
const PAGE_SIZE = 50

type Row = NonNullable<Leaderboard['rows']>[number]

function readScoring(): string | null {
  try {
    return localStorage.getItem(SCORING_KEY)
  } catch {
    return null
  }
}

function writeScoring(value: string): void {
  try {
    localStorage.setItem(SCORING_KEY, value)
  } catch {
    /* A format that cannot be remembered still applies for this visit. */
  }
}

export function LeaderboardPage() {
  const { category = '', stat = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const hub = useLeadersIndex().data
  const teams = useTeamIndex()
  const page = Number(params.get('page') ?? '1') || 1

  const scoring = category === 'fantasy' ? (params.get('scoring') ?? readScoring() ?? hub?.default_scoring ?? 'ppr') : undefined

  const query = useLeaderboard(category, stat, {
    scope: params.get('scope') ?? 'career',
    position: params.get('position'),
    season_min: params.get('season_min') ? Number(params.get('season_min')) : null,
    season_max: params.get('season_max') ? Number(params.get('season_max')) : null,
    active_only: params.get('active_only') === 'true',
    team: params.get('team'),
    qualified: params.get('qualified') !== 'false',
    ...(scoring ? { scoring } : {}),
    page,
    page_size: PAGE_SIZE,
  })
  const data = query.data

  useCrumbLabel(`/leaders/${category}/${stat}`, data ? `${data.category.label} — ${data.stat.label}` : undefined)

  const hubStat = hub?.categories.find((c) => c.id === category)?.stats.find((s) => s.id === stat)

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next, { replace: true })
  }

  const setScoring = (value: string) => {
    writeScoring(value)
    set('scoring', value)
  }

  const scopeOptions = (hubStat?.scopes ?? ['career', 'season', 'game']).map((id) => ({
    value: id,
    label: hub?.scopes.find((o) => o.id === id)?.label ?? SCOPE_LABEL_FALLBACK[id] ?? id,
  }))

  const filtered = ['position', 'season_min', 'season_max', 'active_only', 'team'].some((key) => params.get(key))

  return (
    <>
      <PageHeader
        title={data ? data.stat.label : (hubStat?.label ?? 'Leaderboard')}
        meta={data ? `${data.category.label} · ${data.scope_label}` : undefined}
      />

      <div className="mt-3">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? (
            <Board
              data={data}
              category={category}
              stat={stat}
              params={params}
              page={page}
              teams={teams.data}
              scopeOptions={scopeOptions}
              scoring={scoring}
              scoringOptions={hub?.scoring_formats ?? []}
              filtered={filtered}
              onChange={set}
              onScoring={setScoring}
              onClear={() => setParams({}, { replace: true })}
              onPage={(next) => {
                const search = new URLSearchParams(params)
                search.set('page', String(next))
                setParams(search)
              }}
            />
          ) : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function Board({
  data,
  category,
  stat,
  params,
  page,
  teams,
  scopeOptions,
  scoring,
  scoringOptions,
  filtered,
  onChange,
  onScoring,
  onClear,
  onPage,
}: {
  data: Leaderboard
  category: string
  stat: string
  params: URLSearchParams
  page: number
  teams?: { conferences: { divisions: { teams: { abbr: string; name?: string | null }[] }[] }[] }
  scopeOptions: { value: string; label: string }[]
  scoring?: string
  scoringOptions: { id: string; label: string }[]
  filtered: boolean
  onChange: (key: string, value: string | null) => void
  onScoring: (value: string) => void
  onClear: () => void
  onPage: (page: number) => void
}) {
  const teamOptions = flattenTeams(teams)

  return (
    <>
      <p className="max-w-3xl text-[13px] leading-5">
        {data.stat.definition}
        {data.stat.computed_by_us ? (
          <ComputedByUs formula={data.stat.formula ?? data.stat.definition} label="how this stat is calculated" />
        ) : null}
      </p>
      {data.stat.note ? <p className="mt-1 max-w-3xl text-[12px] leading-5 text-ink-3">{data.stat.note}</p> : null}
      <EraBadge from={data.era.from} to={data.era.to ?? undefined} note={data.era.note} className="mt-2" />

      <div className="mt-4 flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-line pb-4">
        <Field label="Scope">
          <Segmented options={scopeOptions} value={data.scope} onChange={(value) => onChange('scope', value)} ariaLabel="Scope" />
        </Field>

        {category === 'fantasy' && scoringOptions.length ? (
          <Field label="Scoring">
            <Segmented
              options={scoringOptions.map((o) => ({ value: o.id, label: o.label.split(' (')[0] }))}
              value={scoring ?? 'ppr'}
              onChange={onScoring}
              ariaLabel="Fantasy scoring format"
            />
          </Field>
        ) : null}

        <Field label="Position">
          <Select value={params.get('position') ?? ''} onChange={(value) => onChange('position', value)} placeholder="Any position">
            {POSITION_GROUPS.map((group) => (
              <option key={group} value={group}>
                {group}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Team">
          <Select value={params.get('team') ?? ''} onChange={(value) => onChange('team', value)} placeholder="Any team">
            {teamOptions.map((team) => (
              <option key={team.abbr} value={team.abbr}>
                {team.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="From season">
          <input
            type="number"
            defaultValue={params.get('season_min') ?? ''}
            onBlur={(event) => onChange('season_min', event.target.value.trim() || null)}
            placeholder={String(data.era.from)}
            className="w-20 rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none placeholder:text-ink-3"
          />
        </Field>

        <Field label="To season">
          <input
            type="number"
            defaultValue={params.get('season_max') ?? ''}
            onBlur={(event) => onChange('season_max', event.target.value.trim() || null)}
            placeholder={String(data.era.to ?? data.era.from)}
            className="w-20 rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none placeholder:text-ink-3"
          />
        </Field>

        <label className="flex items-center gap-1.5 pb-1.5 text-[12px] text-ink-2">
          <input
            type="checkbox"
            checked={params.get('active_only') === 'true'}
            onChange={(event) => onChange('active_only', event.target.checked ? 'true' : null)}
          />
          Active players only
        </label>

        {filtered ? (
          <button type="button" onClick={onClear} className="motion-state pb-1.5 text-[12px] underline hover:text-accent">
            Clear filters
          </button>
        ) : null}
      </div>

      {data.qualification ? (
        <div className="mt-3 flex items-start gap-2">
          <input
            type="checkbox"
            id="qualified-toggle"
            className="mt-0.5"
            disabled={!data.qualification.applied}
            checked={params.get('qualified') !== 'false'}
            onChange={(event) => onChange('qualified', event.target.checked ? null : 'false')}
          />
          <label htmlFor="qualified-toggle" className="text-[12px] leading-5 text-ink-2">
            <span className="font-medium">Qualified only.</span> {data.qualification.rule_text}
          </label>
        </div>
      ) : null}

      <div className="mt-4">
        {data.available === false ? (
          <p className="rounded-md border border-line bg-raised px-3 py-3 text-[13px] text-ink-3">
            {data.note ?? 'This board is not available.'}
          </p>
        ) : (
          <>
            <DataTable
              rows={data.rows ?? []}
              columns={columns(data)}
              rowKey={(row, index) => `${row.gsis_id}-${row.season ?? ''}-${row.week ?? ''}-${index}`}
              emptyMessage={data.note ?? 'No player clears these filters.'}
              toolbar={
                <button
                  type="button"
                  onClick={() => downloadJson(`${category}-${stat}-leaders.json`, data)}
                  className="motion-state rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-3 hover:border-line-strong hover:text-ink"
                >
                  Export JSON
                </button>
              }
              onExport={(visible, sorted) =>
                downloadCsv(`${category}-${stat}-leaders.csv`, visible, sorted, (row, column) => exportCell(row, column.id))
              }
            />
            <Pager data={data} page={page} onPage={onPage} />

            {data.rules ? (
              <ul className="mt-3 space-y-1 border-t border-line pt-3 text-[11px] leading-4 text-ink-3">
                {Object.entries(data.rules).map(([key, text]) => (
                  <li key={key}>{text}</li>
                ))}
              </ul>
            ) : null}

            {data.scope !== 'career' ? (
              <p className="mt-2 text-[12px] text-ink-3">
                <Link to={finderHref(data, category, stat, params)}>Open in Finder</Link> to edit this board as a query — every
                filter above is one of its conditions.
              </p>
            ) : null}
          </>
        )}
      </div>
    </>
  )
}

function columns(data: Leaderboard): Column<Row>[] {
  const cols: Column<Row>[] = [
    {
      id: 'rank',
      header: 'Rank',
      width: '4.5rem',
      align: 'right',
      sortValue: (row) => row.rank,
      render: (row) => (
        <span>
          {row.rank}
          {row.tied ? <Chip title={`${row.tied_count} players share this rank`}>{`(${row.tied_count} tied)`}</Chip> : null}
        </span>
      ),
    },
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.player,
      render: (row) => <Link to={row.href}>{row.player}</Link>,
    },
    {
      id: 'position',
      header: 'Pos',
      width: '4rem',
      sortValue: (row) => row.position ?? '',
      render: (row) => row.position ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'team',
      header: 'Team',
      width: '8rem',
      sortValue: (row) => row.team ?? '',
      render: (row) => <TeamCell team={row.team} />,
    },
  ]

  if (data.scope === 'career') {
    cols.push(
      {
        id: 'seasons',
        header: 'Seasons',
        width: '7rem',
        sortValue: (row) => row.first_season ?? null,
        render: (row) =>
          row.first_season ? <span>{`${row.first_season}–${row.last_season}`}</span> : <span className="text-ink-3">—</span>,
      },
      {
        id: 'games',
        header: 'G',
        align: 'right',
        sortValue: (row) => row.games ?? null,
        render: (row) => num(row.games ?? null, 0),
      },
    )
  } else if (data.scope === 'season') {
    cols.push(
      {
        id: 'season',
        header: 'Season',
        width: '5.5rem',
        sortValue: (row) => row.season ?? null,
        render: (row) => (row.season ? <SeasonLink season={row.season} /> : <span className="text-ink-3">—</span>),
      },
      {
        id: 'games',
        header: 'G',
        align: 'right',
        sortValue: (row) => row.games ?? null,
        render: (row) => num(row.games ?? null, 0),
      },
    )
  } else {
    cols.push(
      {
        id: 'season',
        header: 'Season',
        width: '5.5rem',
        sortValue: (row) => row.season ?? null,
        render: (row) => (row.season ? <SeasonLink season={row.season} /> : <span className="text-ink-3">—</span>),
      },
      {
        id: 'week',
        header: 'Week',
        width: '8rem',
        sortValue: (row) => row.week ?? null,
        render: (row) =>
          row.week ? (
            row.game_href ? (
              <Link to={row.game_href}>{`Wk ${row.week}`}</Link>
            ) : (
              <span>{`Wk ${row.week}`}</span>
            )
          ) : (
            <span className="text-ink-3">—</span>
          ),
      },
      {
        id: 'opponent',
        header: 'Opp',
        width: '5rem',
        sortValue: (row) => row.opponent ?? '',
        render: (row) => <TeamCell team={row.opponent} />,
      },
    )
  }

  cols.push({
    id: 'value',
    header: data.stat.label,
    align: 'right',
    width: '7.5rem',
    emphasis: true,
    sortValue: (row) => row.value ?? null,
    render: (row) => formatStatValue(row.value, data.stat.id, data.stat.unit),
  })

  for (const support of data.support_columns ?? []) {
    cols.push({
      id: `support-${support.id}`,
      header: support.label,
      align: 'right',
      optional: true,
      sortValue: (row) => row.support?.[support.id] ?? null,
      render: (row) => formatSupportValue(row.support?.[support.id], support.id),
    })
  }

  return cols
}

function exportCell(row: Row, columnId: string): string | number | null {
  if (columnId === 'rank') return row.rank
  if (columnId === 'player') return row.player
  if (columnId === 'position') return row.position ?? null
  if (columnId === 'team') return row.team ?? null
  if (columnId === 'seasons') return row.first_season ? `${row.first_season}-${row.last_season}` : null
  if (columnId === 'games') return row.games ?? null
  if (columnId === 'season') return row.season ?? null
  if (columnId === 'week') return row.week ?? null
  if (columnId === 'opponent') return row.opponent ?? null
  if (columnId === 'value') return row.value ?? null
  if (columnId.startsWith('support-')) return row.support?.[columnId.slice('support-'.length)] ?? null
  return null
}

function formatStatValue(value: number | null | undefined, statId: string, unit: string): string {
  if (value === null || value === undefined) return '—'
  const decimals = decimalsFor(statId)
  if (unit === 'percent') return percent(value, decimals)
  if (unit === 'epa') return signed(value, decimals)
  return num(value, decimals)
}

function formatSupportValue(value: number | null | undefined, id: string): string {
  if (value === null || value === undefined) return '—'
  const decimals = id === 'numerator' || id === 'denominator' ? 0 : decimalsFor(id)
  return num(value, decimals)
}

function TeamCell({ team }: { team?: string | null }) {
  if (!team) return <span className="text-ink-3">—</span>
  if (team.includes(',')) return <span>{team}</span>
  return <TeamLink abbr={team} />
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-[0.04em] text-ink-3">{label}</p>
      {children}
    </div>
  )
}

function Select({
  value,
  onChange,
  placeholder,
  children,
}: {
  value: string
  onChange: (value: string | null) => void
  placeholder: string
  children: React.ReactNode
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value || null)}
      className="rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none"
    >
      <option value="">{placeholder}</option>
      {children}
    </select>
  )
}

function flattenTeams(
  teams?: { conferences: { divisions: { teams: { abbr: string; name?: string | null }[] }[] }[] },
): { abbr: string; name: string }[] {
  const out: { abbr: string; name: string }[] = []
  for (const conference of teams?.conferences ?? []) {
    for (const division of conference.divisions) {
      for (const team of division.teams) out.push({ abbr: team.abbr, name: team.name ?? team.abbr })
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name))
}

function Pager({ data, page, onPage }: { data: Leaderboard; page: number; onPage: (page: number) => void }) {
  const total = data.total ?? 0
  const pageSize = data.page_size ?? PAGE_SIZE
  const rows = data.rows?.length ?? 0
  if (!rows) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(total, first + rows - 1)
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
      <span>{`${num(first, 0)}–${num(last, 0)} of ${num(total, 0)}`}</span>
      <div className="ml-auto flex gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="motion-state rounded border border-line px-2 py-0.5 hover:border-line-strong disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          className="motion-state rounded border border-line px-2 py-0.5 hover:border-line-strong disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}

/** The whole board, exactly as fetched — same shape a Finder query would return. */
function downloadJson(filename: string, data: Leaderboard): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

/** The Finder's player-season / player-game modes take the same readable filters. */
function finderHref(data: Leaderboard, category: string, stat: string, params: URLSearchParams): string {
  const mode = data.scope === 'game' ? 'player_game' : 'player_season'
  const search = new URLSearchParams({ mode, sort: `-${stat}` })
  for (const key of ['position', 'team', 'season_min', 'season_max']) {
    const value = params.get(key)
    if (value) search.set(key, value)
  }
  search.set('category', category)
  return `/finder?${search.toString()}`
}
