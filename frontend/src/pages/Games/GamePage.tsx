import { useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useGame, type Game } from '../../api/endpoints'
import { WinProbabilityChart, type WpPoint } from '../../components/charts/WinProbabilityChart'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { Chip, PageHeader, Section } from '../../components/ui/Page'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { clock, num, ordinal, plural, rate, signed, stat } from '../../design/format'
import { BoxScore, SnapCounts } from './blocks/BoxScore'
import { GameHeader, LineScore } from './blocks/GameHeader'
import { PlayLog } from './blocks/PlayLog'
import { DriveBlock, ScoringSummary } from './blocks/ScoringSummary'

type TeamStatRow = NonNullable<Game['team_stats']>['rows'][number]
type StatContext = NonNullable<TeamStatRow['home_context']>

const PAGE_KEY = 'game'

/**
 * One game, top to bottom.
 *
 * Two states have to be right before any of the depth matters. A game that has
 * not been played renders its fixture, its closing line and the payload's own
 * sentence saying the result does not exist yet — no zeroed box score, no empty
 * chart frames, because every block below a result is simply absent from the
 * payload and therefore from the page. And a pre-2020 game whose season is still
 * materialising answers the play log with a 503, which `QueryBoundary` renders
 * as that sentence plus a retry: an empty play list would read as "this game had
 * no plays".
 */
export function GamePage() {
  const { gameId = '' } = useParams()
  const query = useGame(gameId)
  const data = query.data
  const header = data?.header

  useCrumbLabel(
    `/games/${gameId}`,
    header ? `${header.away.abbr ?? 'Away'} at ${header.home.abbr ?? 'Home'}` : undefined,
  )
  useAnchorScroll(!!data)

  return (
    <>
      {data ? null : <PageFallback gameId={gameId} />}
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {data ? <GameBody data={data} /> : null}
      </QueryBoundary>
    </>
  )
}

/** Before the payload lands the id is all we honestly know; it is also readable. */
function PageFallback({ gameId }: { gameId: string }) {
  return <PageHeader title={gameId.replace(/_/g, ' ')} meta="Game" />
}

function GameBody({ data }: { data: Game }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  const hasPlayFilter = ['team', 'quarter', 'down', 'play_type', 'min_epa', 'drive'].some((key) => params.get(key))
  const [logOpen, setLogOpen] = useState(() => hasPlayFilter || location.hash.startsWith('#play-'))

  const { header, win_probability: wp, team_stats: teamStats, box_score: box, snaps, drives, scoring } = data
  const home = header.home
  const away = header.away

  const points = useMemo<WpPoint[]>(
    () =>
      (wp?.points ?? []).flatMap((point) =>
        point.play_id === null ||
        point.play_id === undefined ||
        point.secs === null ||
        point.secs === undefined ||
        point.home_wp === null ||
        point.home_wp === undefined
          ? []
          : [
              {
                play_id: point.play_id,
                seconds_remaining: point.secs,
                home_wp: point.home_wp,
                home_score: point.home_score ?? 0,
                away_score: point.away_score ?? 0,
              },
            ],
      ),
    [wp],
  )

  const setParam = (key: string, value: string | null) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        if (value === null) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  }

  /** Opening the log and pointing at one play is what both charts do on a click. */
  const focusPlay = (playId: number) => {
    setLogOpen(true)
    navigate({ pathname: location.pathname, search: location.search, hash: `#play-${playId}` })
  }

  const selectedDrive = params.get('drive') ? Number(params.get('drive')) : null
  const boxCategory = params.get('box') ?? box?.categories[0]?.id ?? ''

  return (
    <>
      <GameHeader data={data} />

      {data.line_score ? (
        <div id="line-score">
          <Section title="Line score" note="By quarter">
            <LineScore line={data.line_score} header={header} />
          </Section>
        </div>
      ) : null}

      {scoring?.length ? (
        <div id="scoring">
          <Section title="Scoring summary" note={plural(scoring.length, 'scoring play')}>
            <ScoringSummary plays={scoring} data={data} />
          </Section>
        </div>
      ) : null}

      {wp && points.length > 1 ? (
        <div id="win-probability">
          <Section title="Win probability" note={`${home.abbr ?? 'Home'} perspective, kickoff to final whistle`}>
            <WinProbabilityChart
              points={points}
              homeTeam={home.abbr ?? 'Home'}
              awayTeam={away.abbr ?? 'Away'}
              height={280}
              onSelectPlay={focusPlay}
            />
            <BiggestSwing wp={wp} homeAbbr={home.abbr ?? 'Home'} onFocus={focusPlay} />
            <p className="mt-1 text-[11px] leading-4 text-ink-3">
              {wp.note} Click the chart to open that moment in the play log.
            </p>
          </Section>
        </div>
      ) : null}

      {drives?.length ? (
        <div id="drives">
          <Section title="Drive chart" note={plural(drives.length, 'drive')}>
            <DriveBlock
              drives={drives}
              data={data}
              selected={selectedDrive}
              onSelect={(drive) => {
                setParam('drive', drive === null ? null : String(drive))
                if (drive !== null) setLogOpen(true)
              }}
            />
          </Section>
        </div>
      ) : null}

      {teamStats?.rows.length ? (
        <div id="team-stats">
          <Section title="Team stats" note="Each figure placed among that season's team-games">
            <TeamStatsComparison stats={teamStats} data={data} />
          </Section>
        </div>
      ) : null}

      {box?.categories.length ? (
        <div id="box-score">
          <Section title="Box score" note={`${away.abbr ?? 'Away'} first`}>
            <BoxScore box={box} data={data} category={boxCategory} onCategoryChange={(id) => setParam('box', id)} />
          </Section>
        </div>
      ) : null}

      {snaps && (snaps.home.length > 0 || snaps.away.length > 0) ? (
        <div id="snaps">
          <Section
            title="Snap counts"
            collapsible
            defaultCollapsed
            count={plural(snaps.home.length + snaps.away.length, 'player')}
            pageKey={PAGE_KEY}
            sectionKey="snaps"
          >
            <SnapCounts snaps={snaps} data={data} />
          </Section>
        </div>
      ) : null}

      {data.play_log ? (
        <PlayLog
          gameId={data.game_id}
          info={data.play_log}
          season={data.season}
          open={logOpen}
          onOpenChange={setLogOpen}
        />
      ) : null}

      <footer className="mt-8 border-t border-line pt-3">
        <EraBadge from={data.coverage.first_season} to={data.coverage.last_season} note={data.coverage.note} />
      </footer>
    </>
  )
}

/**
 * The page's one accent is the marker on this swing; the sentence beneath names
 * it in words and opens the play that caused it.
 */
function BiggestSwing({
  wp,
  homeAbbr,
  onFocus,
}: {
  wp: NonNullable<Game['win_probability']>
  homeAbbr: string
  onFocus: (playId: number) => void
}) {
  const swing = wp.biggest_swing
  if (!swing || swing.delta === null || swing.delta === undefined) return null
  const playId = swing.play_id
  return (
    <p className="mt-2 text-[12px] leading-5 text-ink-2">
      {`Biggest swing we hold: ${homeAbbr} win probability `}
      {rate(swing.home_wp_before, 0)} → {rate(swing.home_wp_after, 0)} ({signed(swing.delta * 100, 1)} percentage points)
      {swing.description ? ` — ${swing.description}` : ''}.
      {swing.computed_by_us ? <ComputedByUs formula={swing.note} anchor="win-probability" /> : null}
      {playId ? (
        <>
          {' '}
          <button
            type="button"
            onClick={() => onFocus(playId)}
            className="motion-state underline hover:text-accent"
          >
            Open that play in the log
          </button>
        </>
      ) : null}
    </p>
  )
}

/**
 * Away beside home, with each figure's standing given as a percentile among
 * that season's team-games rather than a rank out of 32 — one afternoon is not
 * a season (SPEC section 3, correction 5).
 */
function TeamStatsComparison({ stats, data }: { stats: NonNullable<Game['team_stats']>; data: Game }) {
  const away = data.header.away
  const home = data.header.home

  const columns: Column<TeamStatRow>[] = [
    {
      id: 'stat',
      header: 'Stat',
      width: '13rem',
      sortValue: (row) => row.label,
      render: (row) => (
        <span>
          {row.label}
          {row.higher_is_better ? null : <span className="ml-1.5 text-[11px] text-ink-3">lower is better</span>}
        </span>
      ),
    },
    {
      id: 'away',
      header: away.abbr ?? 'Away',
      align: 'right',
      sortValue: (row) => row.away,
      render: (row) => <TeamStatCell value={row.away} row={row} context={row.away_context} />,
    },
    {
      id: 'home',
      header: home.abbr ?? 'Home',
      align: 'right',
      sortValue: (row) => row.home,
      render: (row) => <TeamStatCell value={row.home} row={row} context={row.home_context} />,
    },
  ]

  return (
    <div>
      <DataTable
        rows={stats.rows}
        columns={columns}
        rowKey={(row) => row.stat}
        emptyMessage="We hold no per-game team totals for this game."
        onExport={(visible, sorted) =>
          downloadCsv(`${data.game_id}-team-stats.csv`, visible, sorted, (row, column) =>
            column.id === 'stat' ? row.label : column.id === 'away' ? row.away : row.home,
          )
        }
      />
      <p className="mt-1.5 text-[11px] leading-4 text-ink-3">
        {stats.percentile_method}
        {stats.computed_by_us ? <ComputedByUs formula={stats.percentile_method} anchor="game-team-stats" /> : null}
      </p>
      <p className="mt-1 text-[11px] leading-4 text-ink-3">{stats.note}</p>
    </div>
  )
}

function TeamStatCell({
  value,
  row,
  context,
}: {
  value: number | null | undefined
  row: TeamStatRow
  context: StatContext | null | undefined
}) {
  const percentile =
    context && context.percentile !== null && context.percentile !== undefined
      ? Math.round(context.percentile * 100)
      : null
  return (
    <span className="whitespace-nowrap">
      {formatTeamStat(value, row)}
      {percentile !== null && context ? (
        <Chip
          title={`${ordinal(percentile)} percentile among ${context.n.toLocaleString()} team-games in ${context.season}${
            row.higher_is_better ? '' : ' — lower is better for this stat'
          }`}
        >
          {ordinal(percentile)} pct
        </Chip>
      ) : null}
    </span>
  )
}

/** Unit decides the shape; the decimals still come from `design/format`. */
function formatTeamStat(value: number | null | undefined, row: TeamStatRow): string {
  if (value === null || value === undefined) return '—'
  if (row.unit === 'rate') return rate(value, 1)
  if (row.unit === 'seconds') return clock(value)
  if (row.unit === 'count') return num(value, 0)
  return stat(value, row.stat)
}
