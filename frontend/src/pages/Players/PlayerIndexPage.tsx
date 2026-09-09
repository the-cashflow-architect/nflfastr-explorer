import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { DraftClassLink, TeamLink } from '../../components/ui/EntityLink'
import { PageHeader, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { num, plural } from '../../design/format'
import { usePlayerIndex, useSeasonIndex, useTeamIndex, type PlayerIndex } from '../../api/endpoints'
import { StatValue } from './blocks/CareerTable'

/**
 * Every player on file, behind a filter rail.
 *
 * The one thing this page must not do is print a zero where a player simply has
 * no row. Offensive linemen and long snappers have no season stat line at all;
 * the payload hands back a null headline with the sentence explaining why, and
 * that sentence is what the cell carries. A 0 there would read as "he gained no
 * yards", which is a different and false claim.
 */

//: The position groups the season file itself uses; the API matches a group or
//: an exact position against the same column.
const POSITION_GROUPS = ['QB', 'RB', 'FB', 'WR', 'TE', 'OL', 'DL', 'LB', 'DB', 'SPEC']

const PAGE_SIZE = 200

type Row = PlayerIndex['rows'][number]

export function PlayerIndexPage() {
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') ?? '1') || 1

  const query = usePlayerIndex({
    q: params.get('q'),
    position: params.get('position'),
    team: params.get('team'),
    season: params.get('season') ? Number(params.get('season')) : null,
    college: params.get('college'),
    draft_year: params.get('draft_year') ? Number(params.get('draft_year')) : null,
    status: params.get('status'),
    sort: params.get('sort') ?? 'recent',
    page,
    page_size: PAGE_SIZE,
  })
  const data = query.data

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    // A filter change is not a navigation: it should not stack up in history.
    next.delete('page')
    setParams(next, { replace: true })
  }

  const filtered = ['q', 'position', 'team', 'season', 'college', 'draft_year', 'status'].some((key) =>
    params.get(key),
  )

  return (
    <>
      <PageHeader
        title="Players"
        meta={
          data
            ? `${data.total.toLocaleString()} players on file · one page per player, keyed on the nflverse gsis id`
            : 'Every player with a row in the nflverse player file.'
        }
      />

      <div className="mt-4 grid gap-6 md:grid-cols-[15rem_minmax(0,1fr)]">
        <FilterRail data={data} params={params} onChange={set} showClear={filtered} onClear={() => setParams({}, { replace: true })} />

        <div className="min-w-0">
          <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
            {data ? (
              <>
                <DataTable
                  rows={data.rows}
                  columns={columns(data)}
                  rowKey={(row) => row.gsis_id}
                  stickyFirstColumn
                  emptyMessage="No player matches these filters. Widen the name search or clear a filter — every player on file has a row, but not every combination of filters has a player."
                  caption={data.rules.headline}
                  toolbar={
                    <Segmented
                      options={[
                        { value: 'recent', label: 'Most recent' },
                        { value: 'name', label: 'Name' },
                        { value: 'games', label: 'Games' },
                      ]}
                      value={params.get('sort') ?? 'recent'}
                      onChange={(value) => set('sort', value)}
                      ariaLabel="Sort players"
                    />
                  }
                  onExport={(visible, sorted) =>
                    downloadCsv('players.csv', visible, sorted, (row, column) => exportCell(row, column.id))
                  }
                />
                <Pager data={data} page={page} onPage={(next) => {
                  const search = new URLSearchParams(params)
                  search.set('page', String(next))
                  setParams(search)
                }} />
              </>
            ) : null}
          </QueryBoundary>

          <p className="mt-4 border-t border-line pt-3 text-[12px] text-ink-3">
            Need a harder question?{' '}
            <Link to={finderHref(params)}>Open the Finder</Link> — every filter here is one of its
            conditions, and it has the ones this page does not expose.
          </p>
        </div>
      </div>
    </>
  )
}

function columns(data: PlayerIndex): Column<Row>[] {
  return [
    {
      id: 'player',
      header: 'Player',
      width: '13rem',
      sortValue: (row) => row.display_name,
      render: (row) =>
        row.display_name ? <Link to={row.href}>{row.display_name}</Link> : <span className="text-ink-3">—</span>,
    },
    {
      id: 'position',
      header: 'Pos',
      width: '4rem',
      sortValue: (row) => row.position,
      render: (row) => row.position ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'team',
      header: 'Team',
      width: '5rem',
      help: 'The most recent franchise on file for him. Older codes are canonicalised, so a St. Louis Rams season reads LA.',
      sortValue: (row) => row.latest_team,
      render: (row) => <TeamLink abbr={row.latest_team} />,
    },
    {
      id: 'teams',
      header: 'Teams',
      optional: true,
      sortValue: (row) => row.teams.join(' '),
      render: (row) =>
        row.teams.length ? (
          <span className="flex flex-wrap gap-x-1.5">
            {row.teams.map((team) => (
              <TeamLink key={team} abbr={team} />
            ))}
          </span>
        ) : (
          <span className="text-ink-3">—</span>
        ),
    },
    {
      id: 'seasons',
      header: 'Seasons',
      width: '7rem',
      help: 'First and last season this player appears in, across every file we load.',
      sortValue: (row) => row.first_season,
      render: (row) =>
        row.first_season ? (
          <span>
            {row.first_season}–{row.last_season}
          </span>
        ) : (
          <span className="text-ink-3">—</span>
        ),
    },
    {
      id: 'status',
      header: 'Status',
      optional: true,
      help: data.rules.active,
      sortValue: (row) => (row.active ? 1 : 0),
      render: (row) =>
        row.active ? 'Active' : row.last_season ? `Last played ${row.last_season}` : <span className="text-ink-3">—</span>,
    },
    {
      id: 'games',
      header: 'G',
      align: 'right',
      sortValue: (row) => row.games,
      render: (row) => <StatValue value={row.games} unit="count" id="games" />,
    },
    {
      id: 'draft',
      header: 'Draft',
      width: '9rem',
      help: 'Round, pick and class from the draft file. Undrafted players have no row in it.',
      sortValue: (row) => row.draft?.season ?? null,
      render: (row) =>
        row.draft ? (
          <span>
            <DraftClassLink year={row.draft.season} />
            {row.draft.round ? <span className="text-ink-3">{` · R${row.draft.round}`}</span> : null}
            {row.draft.pick ? <span className="text-ink-3">{` #${row.draft.pick}`}</span> : null}
          </span>
        ) : (
          <span className="text-ink-3" title="No row for this player in the draft file.">
            —
          </span>
        ),
    },
    {
      id: 'college',
      header: 'College',
      optional: true,
      sortValue: (row) => row.college,
      render: (row) => row.college ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'headline',
      header: 'Career headline',
      align: 'right',
      help: data.rules.headline,
      sortValue: (row) => row.headline.value ?? null,
      render: (row) => <Headline headline={row.headline} />,
    },
  ]
}

function Headline({ headline }: { headline: Row['headline'] }) {
  if (headline.value === null || headline.value === undefined) {
    return (
      <span className="cursor-help text-ink-3 underline decoration-dotted underline-offset-2" title={headline.note ?? undefined}>
        —
      </span>
    )
  }
  return (
    <span title={headline.note ?? undefined}>
      <StatValue value={headline.value} unit={headline.unit} id={headline.id ?? undefined} />
      {headline.label ? <span className="ml-1.5 text-[11px] text-ink-3">{headline.label}</span> : null}
    </span>
  )
}

function exportCell(row: Row, columnId: string): string | number | null {
  switch (columnId) {
    case 'player':
      return row.display_name ?? null
    case 'position':
      return row.position ?? null
    case 'team':
      return row.latest_team ?? null
    case 'teams':
      return row.teams.join(' ')
    case 'seasons':
      return row.first_season ? `${row.first_season}-${row.last_season}` : null
    case 'status':
      return row.active ? 'Active' : row.last_season ? `Last played ${row.last_season}` : null
    case 'games':
      return row.games ?? null
    case 'draft':
      return row.draft ? `${row.draft.season} R${row.draft.round ?? ''} #${row.draft.pick ?? ''}`.trim() : null
    case 'college':
      return row.college ?? null
    case 'headline':
      return row.headline.value ?? row.headline.note ?? null
    default:
      return null
  }
}

function FilterRail({
  data,
  params,
  onChange,
  showClear,
  onClear,
}: {
  data?: PlayerIndex
  params: URLSearchParams
  onChange: (key: string, value: string | null) => void
  showClear: boolean
  onClear: () => void
}) {
  const teams = useTeamIndex()
  const seasons = useSeasonIndex()
  const [name, setName] = useState(params.get('q') ?? '')

  // The URL is the source of truth, so a back button or a shared link refills
  // the box; typing debounces into it rather than out of it.
  const urlName = params.get('q') ?? ''
  useEffect(() => setName(urlName), [urlName])
  useEffect(() => {
    if (name === urlName) return
    const timer = setTimeout(() => onChange('q', name.trim() || null), 200)
    return () => clearTimeout(timer)
  }, [name, urlName, onChange])

  const teamOptions = useMemo(() => {
    const out: { abbr: string; name: string }[] = []
    for (const conference of teams.data?.conferences ?? []) {
      for (const division of conference.divisions) {
        for (const team of division.teams) out.push({ abbr: team.abbr, name: team.name ?? team.abbr })
      }
    }
    return out.sort((a, b) => a.name.localeCompare(b.name))
  }, [teams.data])

  const seasonOptions = useMemo(
    () => (seasons.data?.seasons ?? []).map((season) => season.season).sort((a, b) => b - a),
    [seasons.data],
  )

  return (
    <aside className="md:sticky md:top-[56px] md:self-start">
      <div className="space-y-3">
        <label className="block">
          <span className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] text-ink-3">
            <Search className="h-4 w-4" aria-hidden />
            Name
          </span>
          <input
            type="search"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Any part of a name"
            className="w-full rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none placeholder:text-ink-3"
          />
        </label>

        <Field label="Position">
          <Select value={params.get('position') ?? ''} onChange={(value) => onChange('position', value)} placeholder="Any position">
            {POSITION_GROUPS.map((group) => (
              <option key={group} value={group}>
                {group === 'SPEC' ? 'SPEC — kickers, punters, snappers' : group}
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
          <p className="mt-1 text-[11px] leading-4 text-ink-3">Matches any season he spent with that franchise.</p>
        </Field>

        <Field label="Status">
          <Select value={params.get('status') ?? ''} onChange={(value) => onChange('status', value)} placeholder="Any status">
            <option value="active">Active</option>
            <option value="retired">Retired</option>
          </Select>
          {data ? <p className="mt-1 text-[11px] leading-4 text-ink-3">{data.rules.active}</p> : null}
        </Field>

        <Field label="Season active in">
          <Select value={params.get('season') ?? ''} onChange={(value) => onChange('season', value)} placeholder="Any season">
            {seasonOptions.map((season) => (
              <option key={season} value={String(season)}>
                {season}
              </option>
            ))}
          </Select>
          {data ? <p className="mt-1 text-[11px] leading-4 text-ink-3">{data.rules.season_filter}</p> : null}
        </Field>

        <Field label="College">
          <input
            type="text"
            defaultValue={params.get('college') ?? ''}
            onBlur={(event) => onChange('college', event.target.value.trim() || null)}
            placeholder="Exact name, e.g. Alabama"
            className="w-full rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none placeholder:text-ink-3"
          />
        </Field>

        <Field label="Draft year">
          <input
            type="number"
            defaultValue={params.get('draft_year') ?? ''}
            onBlur={(event) => onChange('draft_year', event.target.value.trim() || null)}
            placeholder="Four-digit year"
            className="w-full rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none placeholder:text-ink-3"
          />
        </Field>

        {showClear ? (
          <button
            type="button"
            onClick={onClear}
            className="motion-state rounded-md border border-line px-2 py-1 text-[12px] hover:border-line-strong"
          >
            Clear filters
          </button>
        ) : null}
      </div>
    </aside>
  )
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
      className="w-full rounded-md border border-line bg-raised px-2 py-1.5 text-[13px] outline-none"
    >
      <option value="">{placeholder}</option>
      {children}
    </select>
  )
}

function Pager({ data, page, onPage }: { data: PlayerIndex; page: number; onPage: (page: number) => void }) {
  const first = (page - 1) * data.page_size + 1
  const last = Math.min(data.total, first + data.rows.length - 1)
  const pages = Math.max(1, Math.ceil(data.total / data.page_size))
  if (!data.rows.length) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
      <span>{`${num(first, 0)}–${num(last, 0)} of ${num(data.total, 0)}`}</span>
      <span>{plural(pages, 'page')}</span>
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

/** The Finder opens on the same filters this page was showing. */
function finderHref(params: URLSearchParams): string {
  const search = new URLSearchParams({ mode: 'player_season' })
  for (const key of ['position', 'team', 'season', 'college', 'draft_year']) {
    const value = params.get(key)
    if (value) search.set(key, value)
  }
  return `/finder?${search.toString()}`
}
