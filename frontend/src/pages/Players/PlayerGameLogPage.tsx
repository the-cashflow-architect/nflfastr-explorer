import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { GameLink, TeamLink } from '../../components/ui/EntityLink'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented, Tile, TileRow } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { gameDate, num, rate } from '../../design/format'
import { usePlayerGameLog, usePlayerHub, type PlayerGameLog } from '../../api/endpoints'
import { StatValue } from './blocks/CareerTable'
import { PlayerMiniHeader, SeasonPicker } from './blocks/PlayerHeader'

/**
 * Every game, one row each, for a season or for a career.
 *
 * Two columns here are ours rather than the league's and are labelled as such:
 * "Started" is a snap-share proxy because nothing in the verified data marks a
 * starter, and fantasy points are computed in SQL from the box line. Both carry
 * the payload's own wording — the rule, and why it is a rule — rather than a
 * sentence written here.
 */

const ALL = 'all'
const SCORING_KEY = 'gridiron.fantasy'
const SCORING = [
  { value: 'standard', label: 'Standard' },
  { value: 'ppr', label: 'PPR' },
  { value: 'half', label: 'Half PPR' },
]

type Row = PlayerGameLog['rows'][number]

export function PlayerGameLogPage() {
  const { gsisId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const hubQuery = usePlayerHub(gsisId)
  const hub = hubQuery.data

  const season = params.get('season') ?? ALL
  const type = params.get('type') ?? ALL
  const scoring = params.get('scoring') ?? storedScoring()

  const query = usePlayerGameLog(gsisId, {
    season: season === ALL ? null : Number(season),
    type,
  })
  const data = query.data

  useCrumbLabel(`/players/${gsisId}/gamelog`, hub ? `${hub.identity.display_name} · Game log` : undefined)

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value === ALL && key !== 'scoring') next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  const seasons = useMemo(() => seasonRange(hub), [hub])

  return (
    <>
      <PlayerMiniHeader hub={hub} gsisId={gsisId} section="Game log" />
      <PageHeader
        title="Game log"
        meta={
          data
            ? `${num(data.games ?? data.rows.length, 0)} games · ${scopeLabel(season, type)}`
            : 'One row per game played.'
        }
      />

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {seasons.length ? (
          <SeasonPicker
            seasons={seasons}
            value={season}
            onChange={(value) => set('season', value)}
            allValue={ALL}
            allLabel="All seasons"
            ariaLabel="Season"
          />
        ) : null}
        <Segmented
          options={[
            { value: ALL, label: 'Both' },
            { value: 'reg', label: 'Regular' },
            { value: 'post', label: 'Postseason' },
          ]}
          value={type}
          onChange={(value) => set('type', value)}
          ariaLabel="Season type"
        />
        <label className="flex items-center gap-2 text-[12px] text-ink-3">
          Fantasy scoring
          <Segmented
            options={SCORING}
            value={scoring}
            onChange={(value) => {
              rememberScoring(value)
              set('scoring', value)
            }}
            ariaLabel="Fantasy scoring format"
          />
        </label>
      </div>

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <GameLog data={data} scoring={scoring} gsisId={gsisId} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function GameLog({ data, scoring, gsisId }: { data: PlayerGameLog; scoring: string; gsisId: string }) {
  if (!data.rows.length) {
    return (
      <p className="px-1 py-6 text-[13px] text-ink-3">
        {data.note ?? 'No game in this range has a row for him in the weekly stats file.'}
      </p>
    )
  }

  const statColumns = data.columns ?? []
  const hasSnaps = data.rows.some((row) => row.offense_snaps !== null && row.offense_snaps !== undefined)
  const hasStarted = data.rows.some((row) => row.started_proxy !== null && row.started_proxy !== undefined)
  const hasAge = data.rows.some((row) => row.age !== null && row.age !== undefined)
  // Week 21 next to week 3 means nothing without it; one season type does not
  // need a column repeating itself on every row.
  const mixedTypes =
    data.rows.some((row) => row.season_type === 'POST') && data.rows.some((row) => row.season_type === 'REG')
  const hasEpa = data.rows.some((row) => row.epa !== null && row.epa !== undefined)
  const fantasyKey = fantasyField(scoring)

  const columns: Column<Row>[] = [
    {
      id: 'date',
      header: 'Date',
      width: '8.5rem',
      sortValue: (row) => row.gameday ?? `${row.season}-${row.week}`,
      render: (row) => (
        <GameLink gameId={row.game_id} className="whitespace-nowrap">
          {gameDate(row.gameday)}
        </GameLink>
      ),
    },
    {
      id: 'week',
      header: 'Wk',
      width: '4rem',
      align: 'right',
      sortValue: (row) => (row.season ?? 0) * 100 + (row.week ?? 0),
      render: (row) => (row.week === null || row.week === undefined ? <span className="text-ink-3">—</span> : row.week),
    },
    {
      id: 'type',
      header: 'Type',
      width: '4.5rem',
      optional: !mixedTypes,
      sortValue: (row) => row.game_type ?? row.season_type,
      render: (row) => row.game_type ?? row.season_type ?? <span className="text-ink-3">—</span>,
    },
    ...(hasAge
      ? [
          {
            id: 'age',
            header: 'Age',
            align: 'right' as const,
            sortValue: (row: Row) => row.age ?? null,
            render: (row: Row) => <StatValue value={row.age} unit="count" id="age" />,
          },
        ]
      : []),
    {
      id: 'team',
      header: 'Team',
      width: '5rem',
      sortValue: (row) => row.team,
      render: (row) => (row.team_href && row.team ? <Link to={row.team_href}>{row.team}</Link> : <TeamLink abbr={row.team} />),
    },
    {
      id: 'opponent',
      header: 'Opp',
      width: '6rem',
      sortValue: (row) => row.opponent,
      render: (row) => (
        <span className="whitespace-nowrap">
          <span className="text-ink-3">{row.home_away === 'away' ? '@ ' : 'vs '}</span>
          {row.opponent_href && row.opponent ? (
            <Link to={row.opponent_href}>{row.opponent}</Link>
          ) : (
            <TeamLink abbr={row.opponent} season={row.season} />
          )}
        </span>
      ),
    },
    {
      id: 'result',
      header: 'Result',
      width: '7rem',
      sortValue: (row) => (row.team_score ?? 0) - (row.opp_score ?? 0),
      render: (row) => (
        <GameLink gameId={row.game_id} className="whitespace-nowrap">
          <span className={row.result === 'W' ? 'text-positive' : row.result === 'L' ? 'text-negative' : ''}>
            {row.result ?? '—'}
          </span>{' '}
          {row.team_score === null || row.opp_score === null ? null : `${num(row.team_score, 0)}–${num(row.opp_score, 0)}`}
        </GameLink>
      ),
    },
    ...(hasStarted
      ? [
          {
            id: 'started',
            header: 'Started',
            width: '5rem',
            help: data.started_proxy
              ? `${data.started_proxy.rule} ${data.started_proxy.why}`
              : 'A proxy, not the official designation.',
            sortValue: (row: Row) => (row.started_proxy ? 1 : 0),
            render: (row: Row) =>
              row.started_proxy === null || row.started_proxy === undefined ? (
                <span className="text-ink-3">—</span>
              ) : (
                <span>{row.started_proxy ? 'Yes' : 'No'}</span>
              ),
          },
        ]
      : []),
    ...statColumns.map(
      (column): Column<Row> => ({
        id: column.id,
        header: column.label,
        align: 'right',
        sortValue: (row) => row.stats[column.id] ?? null,
        render: (row) => <StatValue value={row.stats[column.id]} unit={column.unit} id={column.id} />,
      }),
    ),
    ...(hasSnaps
      ? [
          {
            id: 'offense_snaps',
            header: 'Snaps',
            align: 'right' as const,
            help: 'Offensive snaps he played, from the snap-count file.',
            sortValue: (row: Row) => row.offense_snaps ?? null,
            render: (row: Row) => <StatValue value={row.offense_snaps} unit="count" id="snaps" />,
          },
          {
            id: 'offense_pct',
            header: 'Snap %',
            align: 'right' as const,
            help: "Share of his team's offensive snaps in that game.",
            sortValue: (row: Row) => row.offense_pct ?? null,
            render: (row: Row) => <StatValue value={row.offense_pct} unit="percent" id="snap_pct" />,
          },
          {
            id: 'defense_snaps',
            header: 'Def snaps',
            align: 'right' as const,
            optional: true,
            sortValue: (row: Row) => row.defense_snaps ?? null,
            render: (row: Row) => <StatValue value={row.defense_snaps} unit="count" id="snaps" />,
          },
          {
            id: 'st_snaps',
            header: 'ST snaps',
            align: 'right' as const,
            optional: true,
            sortValue: (row: Row) => row.st_snaps ?? null,
            render: (row: Row) => <StatValue value={row.st_snaps} unit="count" id="snaps" />,
          },
        ]
      : []),
    ...(hasEpa
      ? [
          {
            id: 'epa',
            header: 'EPA',
            align: 'right' as const,
            help: 'Expected points added on the plays he was credited with, from the nflfastR model.',
            sortValue: (row: Row) => row.epa ?? null,
            render: (row: Row) => <StatValue value={row.epa} unit="epa" id="epa" />,
          },
          {
            id: 'plays',
            header: 'Plays',
            align: 'right' as const,
            optional: true,
            sortValue: (row: Row) => row.plays ?? null,
            render: (row: Row) => <StatValue value={row.plays} unit="count" id="plays" />,
          },
          {
            id: 'success_rate',
            header: 'Success',
            align: 'right' as const,
            help: 'Share of his plays with positive expected-points added.',
            sortValue: (row: Row) => row.success_rate ?? null,
            render: (row: Row) =>
              row.success_rate === null || row.success_rate === undefined ? (
                <span className="text-ink-3">—</span>
              ) : (
                rate(row.success_rate, 1)
              ),
          },
        ]
      : []),
    {
      id: 'fantasy',
      header: 'Fantasy',
      align: 'right',
      help: data.fantasy?.note,
      sortValue: (row) => row[fantasyKey] ?? null,
      render: (row) => <StatValue value={row[fantasyKey]} unit="count" id="fantasy_points_per_game" />,
    },
  ]

  return (
    <>
      <TileRow>
        <Tile
          label="Games"
          value={num(data.games ?? data.rows.length, 0)}
          context={summaryLine(data)}
        />
        {headlineAverages(data).map(({ column, value }) => (
          <Tile
            key={column.id}
            label={`${column.label} / game`}
            value={<StatValue value={value} unit={column.unit} id={`${column.id}_per_game`} />}
            context={`Per game · ${num(data.games ?? data.rows.length, 0)} games · ${
              data.season ? data.season : 'every season on file'
            }`}
          />
        ))}
      </TileRow>

      <DataTable
        rows={data.rows}
        columns={columns}
        rowKey={(row) => row.game_id ?? `${row.season}-${row.week}`}
        emptyMessage="No game in this range has a row for him in the weekly stats file."
        caption={<Captions data={data} hasSnaps={hasSnaps} />}
        onExport={(visible, sorted) =>
          downloadCsv(`gamelog-${gsisId}.csv`, visible, sorted, (row, column) => exportCell(row, column.id, fantasyKey))
        }
      />

      {data.splits_summary ? (
        <Section
          title="This range at a glance"
          collapsible
          defaultCollapsed
          count={`${data.splits_summary.games} games`}
          pageKey="player-gamelog"
          sectionKey="summary"
        >
          <p className="text-[13px]">
            {`${data.splits_summary.home} home · ${data.splits_summary.away} away · `}
            {`${data.splits_summary.wins}-${data.splits_summary.losses}`}
            {data.splits_summary.ties ? `-${data.splits_summary.ties}` : ''}
            {' in games he played'}
          </p>
          <p className="mt-1 text-[11px] leading-4 text-ink-3">
            Roof, surface, rest and opponent splits live on{' '}
            <Link to={`/players/${gsisId}/splits`}>Splits</Link>.
          </p>
        </Section>
      ) : null}
    </>
  )
}

function Captions({ data, hasSnaps }: { data: PlayerGameLog; hasSnaps: boolean }) {
  return (
    <>
      {data.started_proxy ? (
        <span className="block">
          {data.started_proxy.rule} {data.started_proxy.why}
          {data.started_proxy.computed_by_us ? (
            <ComputedByUs formula={data.started_proxy.rule} anchor="started-proxy" />
          ) : null}
        </span>
      ) : null}
      {!hasSnaps && data.started_proxy ? (
        <span className="block">
          {`Snap counts begin in ${data.started_proxy.first_season}, so these games carry no snap columns at all.`}
        </span>
      ) : null}
      {data.fantasy ? (
        <span className="block">
          {data.fantasy.note}
          {data.fantasy.computed_by_us ? (
            <ComputedByUs formula={`Fantasy points from ${data.fantasy.columns_used.join(', ')}`} anchor="fantasy" />
          ) : null}
        </span>
      ) : null}
    </>
  )
}

/** The stats a reader of this position looks at first: yards, then scores, then EPA. */
function headlineAverages(data: PlayerGameLog): { column: NonNullable<PlayerGameLog['columns']>[number]; value: number | null }[] {
  const columns = data.columns ?? []
  const rank = (id: string) => (/_yards$/.test(id) ? 0 : /_tds$/.test(id) ? 1 : /_epa$/.test(id) ? 2 : 3)
  return [...columns]
    .sort((a, b) => rank(a.id) - rank(b.id))
    .slice(0, 3)
    .map((column) => ({ column, value: data.averages?.[column.id] ?? null }))
}

function summaryLine(data: PlayerGameLog): string {
  const summary = data.splits_summary
  if (!summary) return scopeLabel(data.season ? String(data.season) : ALL, data.season_type ?? ALL)
  return `${summary.home} home · ${summary.away} away`
}

function scopeLabel(season: string, type: string): string {
  const seasonPart = season === ALL ? 'every season on file' : season
  const typePart = type === 'reg' ? 'regular season' : type === 'post' ? 'postseason' : 'regular season and postseason'
  return `${seasonPart} · ${typePart}`
}

function fantasyField(scoring: string): 'fantasy_standard' | 'fantasy_ppr' | 'fantasy_half' {
  if (scoring === 'ppr') return 'fantasy_ppr'
  if (scoring === 'half') return 'fantasy_half'
  return 'fantasy_standard'
}

function exportCell(row: Row, columnId: string, fantasyKey: keyof Row): string | number | null {
  switch (columnId) {
    case 'date':
      return row.gameday ?? null
    case 'week':
      return row.week ?? null
    case 'type':
      return row.game_type ?? row.season_type ?? null
    case 'age':
      return row.age ?? null
    case 'team':
      return row.team ?? null
    case 'opponent':
      return `${row.home_away === 'away' ? '@' : 'vs'} ${row.opponent ?? ''}`.trim()
    case 'result':
      return row.result ? `${row.result} ${row.team_score ?? ''}-${row.opp_score ?? ''}` : null
    case 'started':
      return row.started_proxy === null || row.started_proxy === undefined ? null : row.started_proxy ? 'Yes' : 'No'
    case 'offense_snaps':
      return row.offense_snaps ?? null
    case 'offense_pct':
      return row.offense_pct ?? null
    case 'defense_snaps':
      return row.defense_snaps ?? null
    case 'st_snaps':
      return row.st_snaps ?? null
    case 'epa':
      return row.epa ?? null
    case 'plays':
      return row.plays ?? null
    case 'success_rate':
      return row.success_rate ?? null
    case 'fantasy': {
      const value = row[fantasyKey]
      return typeof value === 'number' ? value : null
    }
    default:
      return row.stats[columnId] ?? null
  }
}

/** The seasons he has weekly rows in, taken from his own coverage window. */
function seasonRange(hub: ReturnType<typeof usePlayerHub>['data']): number[] {
  const window = hub?.coverage.find((entry) => entry.source === 'player_week')
  if (!window?.first_season || !window.last_season) return []
  const out: number[] = []
  for (let season = window.last_season; season >= window.first_season; season -= 1) out.push(season)
  return out
}

function storedScoring(): string {
  try {
    const stored = localStorage.getItem(SCORING_KEY)
    return stored === 'ppr' || stored === 'half' || stored === 'standard' ? stored : 'standard'
  } catch {
    // Private windows throw rather than return null; the default still applies.
    return 'standard'
  }
}

function rememberScoring(value: string): void {
  try {
    localStorage.setItem(SCORING_KEY, value)
  } catch {
    /* A preference that cannot be stored still holds for this visit. */
  }
}
