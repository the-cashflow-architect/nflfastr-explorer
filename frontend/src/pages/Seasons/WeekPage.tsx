import { Link, useNavigate, useParams } from 'react-router-dom'
import { useSeasonHub, useWeekScoreboard, type SeasonHub, type WeekScoreboard } from '../../api/endpoints'
import { Sparkline } from '../../components/charts/Sparkline'
import { PlayerLink } from '../../components/ui/EntityLink'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { num, signed } from '../../design/format'
import { Mark } from '../../components/ui/Mark'
import { byesWorthNaming } from '../../lib/byes'



export type WeekGame = WeekScoreboard['games'][number]
type LeaderRow = NonNullable<NonNullable<WeekScoreboard['week_leaders']>['by_epa']>[number]

/**
 * The full scoreboard for one week — every game as a card, byes named, and
 * week navigation as the primary action, per the spec.
 *
 * `WeekGameCard` is exported so the season hub's own scoreboard strip
 * renders each game identically rather than a second, drifting copy.
 */
export function WeekPage() {
  const { season: seasonParam = '', week: weekParam = '' } = useParams()
  const seasonNumber = Number(seasonParam)
  const weekNumber = Number(weekParam)
  const season = Number.isFinite(seasonNumber) && seasonNumber > 0 ? seasonNumber : undefined
  const week = Number.isFinite(weekNumber) && weekNumber > 0 ? weekNumber : undefined

  const hub = useSeasonHub(season)
  const query = useWeekScoreboard(season, week)
  const data = query.data
  const navigate = useNavigate()

  useCrumbLabel(season && week ? `/seasons/${season}/week/${week}` : '', data?.week_label)

  const sortedWeeks = [...(hub.data?.weeks ?? [])].sort((a, b) => a - b)
  const labels = buildWeekLabels(hub.data?.bracket)
  const idx = week ? sortedWeeks.indexOf(week) : -1
  const prevWeek = idx > 0 ? sortedWeeks[idx - 1] : undefined
  const nextWeek = idx >= 0 && idx < sortedWeeks.length - 1 ? sortedWeeks[idx + 1] : undefined
  const labelFor = (w: number) => labels.get(w) ?? `Week ${w}`

  return (
    <>
      <PageHeader
        title={data?.week_label ?? (week ? `Week ${week}` : 'Week')}
        meta={
          season ? (
            <Link to={`/seasons/${season}`} className="no-underline hover:text-accent hover:underline">
              {season} season
            </Link>
          ) : undefined
        }
        prev={prevWeek ? { to: `/seasons/${season}/week/${prevWeek}`, label: labelFor(prevWeek) } : undefined}
        next={nextWeek ? { to: `/seasons/${season}/week/${nextWeek}`, label: labelFor(nextWeek) } : undefined}
        subnav={
          sortedWeeks.length ? (
            <select
              aria-label="Jump to week"
              value={week ?? ''}
              onChange={(event) => navigate(`/seasons/${season}/week/${event.target.value}`)}
              className="motion-state rounded border border-line bg-raised px-2 py-1 text-[12px] text-ink hover:border-line-strong"
            >
              {sortedWeeks.map((w) => (
                <option key={w} value={w}>
                  {labelFor(w)}
                </option>
              ))}
            </select>
          ) : undefined
        }
      />

      <div className="mt-5">
        <QueryBoundary
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => void query.refetch()}
          isEmpty={!data?.games.length}
          emptyMessage="No games are scheduled for this week."
        >
          {data ? <WeekBody data={data} season={season ?? 0} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

/** Round label for every postseason week the bracket knows about, keyed by
 * the week number embedded in each bracket game's id — never a hardcoded
 * "playoffs start at week N", which is era-dependent and therefore wrong on
 * some slice of 1999–2025. Regular-season weeks fall back to "Week N".
 *
 * Not exported: a file that renders a page component keeps Fast Refresh
 * working only if every export is a component, so the season hub keeps its
 * own copy of this rather than importing it from here. */
function buildWeekLabels(bracket: SeasonHub['bracket'] | undefined | null): Map<number, string> {
  const map = new Map<number, string>()
  if (!bracket) return map
  for (const round of bracket.rounds) {
    for (const game of round.games) {
      const weekNumber = Number(game.game_id.split('_')[1])
      if (Number.isFinite(weekNumber) && !map.has(weekNumber)) map.set(weekNumber, round.round_label)
    }
  }
  return map
}

function WeekBody({ data, season }: { data: WeekScoreboard; season: number }) {
  const pageKey = `week:${season}`
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.games.map((game) => (
          <WeekGameCard key={game.game_id} game={game} />
        ))}
      </div>

      {byesWorthNaming(data.bye_teams).length ? (
        <p className="mt-3 text-[12px] leading-4 text-ink-3">Bye: {byesWorthNaming(data.bye_teams).join(', ')}</p>
      ) : null}
      {data.note ? <p className="mt-2 text-[11px] leading-4 text-ink-3">{data.note}</p> : null}

      {data.week_leaders?.by_epa?.length || data.week_leaders?.by_fantasy?.length ? (
        <div className="mt-6">
          <Section
            title="Week leaders"
            collapsible
            defaultCollapsed
            pageKey={pageKey}
            sectionKey={`leaders-${data.week}`}
            count="Best single-game performances by EPA and fantasy points"
          >
            <div className="grid gap-5 sm:grid-cols-2">
              {data.week_leaders.by_epa?.length ? (
                <LeaderList title="By EPA" rows={data.week_leaders.by_epa} kind="epa" />
              ) : null}
              {data.week_leaders.by_fantasy?.length ? (
                <LeaderList title="By fantasy points" rows={data.week_leaders.by_fantasy} kind="fantasy" />
              ) : null}
            </div>
          </Section>
        </div>
      ) : null}
    </>
  )
}

function LeaderList({ title, rows, kind }: { title: string; rows: LeaderRow[]; kind: 'epa' | 'fantasy' }) {
  return (
    <div>
      <h3 className="text-[13px] font-medium">
        {title}
        {kind === 'epa' ? (
          <ComputedByUs formula="Total EPA on the plays this player was on the field for, this week." anchor="epa" />
        ) : (
          <ComputedByUs formula="Standard box-score fantasy scoring for the week." anchor="fantasy" />
        )}
      </h3>
      <ul className="mt-1.5">
        {rows.map((row) => (
          <li key={row.gsis_id} className="flex items-baseline gap-2 border-b border-row-rule py-1 last:border-b-0">
            <span className="w-4 shrink-0 text-[11px] text-ink-3">{row.rank}</span>
            <span className="min-w-0 flex-1 truncate text-[13px]">
              <PlayerLink id={row.gsis_id} name={row.player} />
              {row.team ? <span className="ml-1.5 text-[11px] text-ink-3">{row.team}</span> : null}
            </span>
            <span className="shrink-0 text-[13px] tabular-nums">{kind === 'epa' ? signed(row.value, 1) : num(row.value, 1)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function WeekGameCard({ game }: { game: WeekGame }) {
  const decided = game.played && game.home_score !== null && game.home_score !== undefined && game.away_score !== null && game.away_score !== undefined
  const homeWon = decided && (game.home_score as number) > (game.away_score as number)
  const awayWon = decided && (game.away_score as number) > (game.home_score as number)
  const wp = (game.wp_sparkline ?? []).map((point) => point?.[1] ?? null).filter((v): v is number => v !== null)

  return (
    <Link
      to={game.href}
      className="motion-state block rounded-lg border border-line bg-raised px-3 py-2.5 no-underline hover:border-line-strong"
    >
      {game.div_game || game.overtime || !game.played ? (
        <div className="mb-1.5 flex items-center gap-2 text-[10px] uppercase tracking-[0.03em] text-ink-3">
          {game.div_game ? <span>Division</span> : null}
          {game.overtime ? <span>OT</span> : null}
          {!game.played ? <span>Not yet played</span> : null}
        </div>
      ) : null}
      <GameTeamRow team={game.away} score={game.away_score} won={awayWon} played={game.played} />
      <GameTeamRow team={game.home} score={game.home_score} won={homeWon} played={game.played} />
      {game.played && wp.length > 1 ? (
        <div className="mt-2 flex items-center gap-2">
          <Sparkline values={wp} title="Home win probability across the game" />
          {game.biggest_play?.description ? (
            <span className="min-w-0 flex-1 truncate text-[11px] text-ink-3" title={game.biggest_play.description}>
              {game.biggest_play.description}
            </span>
          ) : null}
        </div>
      ) : null}
      {game.spread_line !== null && game.spread_line !== undefined ? (
        <p className="mt-1.5 truncate text-[11px] text-ink-3">
          Line {game.home.abbr} {game.spread_line > 0 ? '+' : ''}
          {game.spread_line}
          {game.ats_result ? ` · ${atsLabel(game.ats_result)}` : null}
        </p>
      ) : null}
    </Link>
  )
}

function atsLabel(result: string): string {
  if (result === 'push') return 'Push'
  if (result === 'home') return 'Home covered'
  if (result === 'away') return 'Away covered'
  return result
}

function GameTeamRow({
  team,
  score,
  won,
  played,
}: {
  team: WeekGame['home']
  score: number | null | undefined
  won: boolean
  played: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="flex min-w-0 items-center gap-1.5">
        <Mark src={team.logo} label={team.abbr ?? '?'} size={16} />
        <span className={`truncate text-[13px] ${won ? 'font-semibold text-ink' : 'text-ink-2'}`}>{team.abbr}</span>
      </span>
      <span className={`shrink-0 text-[13px] tabular-nums ${won ? 'font-semibold text-positive' : 'text-ink-3'}`}>
        {played ? num(score) : 'Not played'}
      </span>
    </div>
  )
}

