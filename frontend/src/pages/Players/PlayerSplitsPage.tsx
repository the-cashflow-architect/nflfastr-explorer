import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { TeamLink } from '../../components/ui/EntityLink'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { num, plural, rate } from '../../design/format'
import { usePlayerHub, usePlayerSplits, type PlayerSplits } from '../../api/endpoints'
import { StatValue } from './blocks/CareerTable'
import { PlayerMiniHeader, SeasonPicker } from './blocks/PlayerHeader'

/**
 * The situational tables — the thing the incumbent charges for.
 *
 * Every rate here is recomputed from summed counts rather than averaged across
 * seasons, which is why the career scope is the default: it is the view the
 * data supports properly and the one nobody else gives away. Buckets under the
 * payload's own threshold are muted and carry their n; they are never hidden,
 * because a reader deciding whether twelve red-zone plays mean anything needs
 * to see that there were twelve.
 */

const CAREER = 'career'
const PAGE_KEY = 'player-splits'

type Bucket = NonNullable<PlayerSplits['situation']>[number]['buckets'][number]
type Context = NonNullable<PlayerSplits['game_context']>[number]

export function PlayerSplitsPage() {
  const { gsisId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const hubQuery = usePlayerHub(gsisId)
  const hub = hubQuery.data

  const season = params.get('season') ?? CAREER
  const type = params.get('type') ?? 'reg'
  const query = usePlayerSplits(gsisId, { season, type })
  const data = query.data

  useCrumbLabel(`/players/${gsisId}/splits`, hub ? `${hub.identity.display_name} · Splits` : undefined)

  const seasons = useMemo(() => {
    const out = new Set<number>()
    for (const row of hub?.career_regular?.rows ?? []) out.add(row.season)
    for (const row of hub?.career_postseason?.rows ?? []) out.add(row.season)
    return [...out].sort((a, b) => b - a)
  }, [hub])

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PlayerMiniHeader hub={hub} gsisId={gsisId} section="Splits" />
      <PageHeader
        title="Splits"
        meta={
          season === CAREER
            ? 'Career, summed from play-level data — counts added, rates recomputed'
            : `Season ${season}`
        }
      />

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {seasons.length ? (
          <SeasonPicker
            seasons={seasons}
            value={season}
            onChange={(value) => set('season', value)}
            allValue={CAREER}
            allLabel="Career"
            ariaLabel="Split scope"
          />
        ) : null}
        <Segmented
          options={[
            { value: 'reg', label: 'Regular' },
            { value: 'post', label: 'Postseason' },
          ]}
          value={type}
          onChange={(value) => set('type', value)}
          ariaLabel="Season type"
        />
      </div>

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <Splits data={data} gsisId={gsisId} scope={season} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function Splits({ data, gsisId, scope }: { data: PlayerSplits; gsisId: string; scope: string }) {
  if (data.unavailable) {
    return (
      <div className="max-w-2xl rounded-md border border-line bg-raised px-3 py-3 text-[13px]">
        <p className="font-medium">{data.unavailable.reason}</p>
        <p className="mt-1 text-ink-2">{data.unavailable.why}</p>
        <p className="mt-2 text-[12px] text-ink-3">
          {`The three roles the play data names are ${data.unavailable.roles.join(', ')}. `}
          His game-by-game record is on <Link to={`/players/${gsisId}/gamelog`}>the game log</Link>.
        </p>
      </div>
    )
  }

  const situations = data.situation ?? []
  const context = data.game_context ?? []
  const opponents = data.opponents ?? []

  if (!situations.length && !context.length && !opponents.length) {
    return (
      <p className="px-1 py-6 text-[13px] text-ink-3">
        {data.note ?? 'No play in this scope is credited to him, so there is nothing to split.'}
      </p>
    )
  }

  return (
    <>
      {situations.map((role, index) => (
        <Section
          key={role.role}
          title={`${role.label} splits`}
          note={index === 0 ? data.buckets_overlap_note : undefined}
          collapsible={index > 0}
          defaultCollapsed={index > 0}
          count={plural(role.buckets.length, 'bucket')}
          pageKey={PAGE_KEY}
          sectionKey={`situation-${role.role}`}
        >
          <DataTable
            rows={role.buckets}
            columns={bucketColumns(scope, data.small_sample_plays)}
            rowKey={(row) => row.bucket}
            emptyMessage={`No ${role.label.toLowerCase()} play in this scope.`}
            caption={
              <>
                <span className="block">
                  {data.method_note}
                  {data.computed_by_us ? (
                    <ComputedByUs
                      formula="Counts summed from play-by-play; every rate recomputed from the sums"
                      anchor="splits"
                    />
                  ) : null}
                </span>
                {data.low_sample_note ? <span className="block">{data.low_sample_note}</span> : null}
              </>
            }
            onExport={(visible, sorted) =>
              downloadCsv(`splits-${role.role}-${gsisId}.csv`, visible, sorted, (row, column) =>
                bucketExport(row, column.id),
              )
            }
          />
        </Section>
      ))}

      {context.length ? (
        <Section title="Game context" note={`${plural(context.length, 'split')} from the schedule and the box line`}>
          <ContextTable rows={context} name={`context-${gsisId}`} />
        </Section>
      ) : null}

      {opponents.length ? (
        <Section
          title="By opponent"
          collapsible
          defaultCollapsed
          count={plural(opponents.length, 'opponent')}
          pageKey={PAGE_KEY}
          sectionKey="opponents"
        >
          <ContextTable rows={opponents} name={`opponents-${gsisId}`} opponent />
        </Section>
      ) : null}
    </>
  )
}

function bucketColumns(scope: string, threshold: number): Column<Bucket>[] {
  const muted = (row: Bucket, content: React.ReactNode) =>
    row.low_sample ? <span className="text-ink-3">{content}</span> : content

  return [
    {
      id: 'bucket',
      header: 'Split',
      width: '14rem',
      sortValue: (row) => row.label,
      render: (row) => (
        <span className={row.low_sample ? 'text-ink-3' : undefined}>
          {row.label}
          {row.low_sample ? (
            <span className="ml-1.5 text-[11px]" title={`Under ${threshold} plays — read it as a hint, not a rate.`}>
              {`n=${row.plays}`}
            </span>
          ) : null}
        </span>
      ),
    },
    ...(scope === CAREER
      ? [
          {
            id: 'seasons',
            header: 'Seasons',
            width: '7rem',
            optional: true,
            sortValue: (row: Bucket) => row.first_season,
            render: (row: Bucket) => muted(row, `${row.first_season}–${row.last_season}`),
          },
        ]
      : []),
    {
      id: 'plays',
      header: 'Plays',
      align: 'right',
      sortValue: (row) => row.plays,
      render: (row) => muted(row, <StatValue value={row.plays} unit="count" id="plays" />),
    },
    {
      id: 'yards',
      header: 'Yards',
      align: 'right',
      sortValue: (row) => row.yards ?? null,
      render: (row) => muted(row, <StatValue value={row.yards} unit="yards" id="yards" />),
    },
    {
      id: 'yards_per_play',
      header: 'Yds/play',
      align: 'right',
      sortValue: (row) => row.yards_per_play ?? null,
      render: (row) => muted(row, <StatValue value={row.yards_per_play} unit="yards" id="yards_per_play" />),
    },
    {
      id: 'touchdowns',
      header: 'TD',
      align: 'right',
      sortValue: (row) => row.touchdowns ?? null,
      render: (row) => muted(row, <StatValue value={row.touchdowns} unit="count" id="touchdowns" />),
    },
    {
      id: 'first_downs',
      header: '1D',
      help: 'Plays that produced a first down or a touchdown.',
      align: 'right',
      sortValue: (row) => row.first_downs ?? null,
      render: (row) => muted(row, <StatValue value={row.first_downs} unit="count" id="first_downs" />),
    },
    {
      id: 'epa',
      header: 'EPA',
      align: 'right',
      help: 'Total expected points added on those plays.',
      sortValue: (row) => row.epa ?? null,
      render: (row) => muted(row, <StatValue value={row.epa} unit="epa" id="epa" />),
    },
    {
      id: 'epa_per_play',
      header: 'EPA/play',
      align: 'right',
      sortValue: (row) => row.epa_per_play ?? null,
      render: (row) => muted(row, <StatValue value={row.epa_per_play} unit="epa" id="epa_per_play" />),
    },
    {
      id: 'success_rate',
      header: 'Success',
      align: 'right',
      help: 'Share of those plays with positive expected-points added.',
      sortValue: (row) => row.success_rate ?? null,
      render: (row) =>
        muted(
          row,
          row.success_rate === null || row.success_rate === undefined ? (
            <span className="text-ink-3">—</span>
          ) : (
            rate(row.success_rate, 1)
          ),
        ),
    },
  ]
}

function bucketExport(row: Bucket, columnId: string): string | number | null {
  switch (columnId) {
    case 'bucket':
      return row.label
    case 'seasons':
      return `${row.first_season}-${row.last_season}`
    case 'plays':
      return row.plays
    case 'yards':
      return row.yards ?? null
    case 'yards_per_play':
      return row.yards_per_play ?? null
    case 'touchdowns':
      return row.touchdowns ?? null
    case 'first_downs':
      return row.first_downs ?? null
    case 'epa':
      return row.epa ?? null
    case 'epa_per_play':
      return row.epa_per_play ?? null
    case 'success_rate':
      return row.success_rate ?? null
    default:
      return null
  }
}

/**
 * Game-context and opponent rows share a shape. Yardage columns that are empty
 * for this player — a quarterback's receiving yards — are hidden rather than
 * shown as a column of zeroes, and stay in the column picker and the export.
 */
function ContextTable({ rows, name, opponent }: { rows: Context[]; name: string; opponent?: boolean }) {
  const yardColumns: { id: 'passing_yards' | 'rushing_yards' | 'receiving_yards'; header: string }[] = [
    { id: 'passing_yards', header: 'Pass yds' },
    { id: 'rushing_yards', header: 'Rush yds' },
    { id: 'receiving_yards', header: 'Rec yds' },
  ]

  const columns: Column<Context>[] = [
    {
      id: 'group',
      header: opponent ? 'Opponent' : 'Split',
      width: '10rem',
      sortValue: (row) => `${row.group} ${row.bucket ?? ''}`,
      render: (row) =>
        opponent ? (
          <TeamLink abbr={row.opponent ?? row.bucket} />
        ) : (
          <span>
            <span className="text-ink-3">{`${row.group} · `}</span>
            {row.bucket ?? '—'}
          </span>
        ),
    },
    {
      id: 'games',
      header: 'G',
      align: 'right',
      sortValue: (row) => row.games,
      render: (row) => num(row.games, 0),
    },
    ...yardColumns.map(
      (column): Column<Context> => ({
        id: column.id,
        header: column.header,
        align: 'right',
        optional: rows.every((row) => !row[column.id]),
        sortValue: (row) => row[column.id] ?? null,
        render: (row) => <StatValue value={row[column.id]} unit="yards" id={column.id} />,
      }),
    ),
    {
      id: 'fantasy_standard',
      header: 'Fantasy',
      align: 'right',
      help: 'Standard scoring, computed from the box line.',
      sortValue: (row) => row.fantasy_standard ?? null,
      render: (row) => <StatValue value={row.fantasy_standard} unit="count" id="fantasy_per_game" />,
    },
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => `${row.group}-${row.bucket ?? ''}`}
      emptyMessage="No game in this scope carries the context columns these splits are built from."
      caption={
        <>
          Yardage and fantasy points are summed from the box lines of the games in each bucket.
          <ComputedByUs formula="Fantasy points, standard scoring, computed from the box line" anchor="fantasy" />
        </>
      }
      onExport={(visible, sorted) =>
        downloadCsv(`${name}.csv`, visible, sorted, (row, column) =>
          column.id === 'group'
            ? `${row.group} ${row.bucket ?? ''}`.trim()
            : column.id === 'games'
              ? row.games
              : ((row[column.id as 'passing_yards'] ?? null) as number | null),
        )
      }
    />
  )
}
