import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useWeekScoreboard, type WeekScoreboard } from '../../api/endpoints'
import { Sparkline } from '../../components/charts/Sparkline'
import { GameLink } from '../../components/ui/EntityLink'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { num } from '../../design/format'
import { Mark } from '../../components/ui/Mark'
import { byesWorthNaming } from '../../lib/byes'



type WeekGame = WeekScoreboard['games'][number]
type BrandTeam = WeekGame['home']

/**
 * The home page's scoreboard strip. It opens on the latest completed week —
 * chosen by the caller, which knows the season is actually finished — and the
 * prev/next arrows step through other weeks of the same season in place,
 * never navigating away from `/`.
 */
export function WeekStrip({ season, weeks }: { season: number; weeks: number[] }) {
  const maxWeek = weeks.length ? Math.max(...weeks) : null
  const minWeek = weeks.length ? Math.min(...weeks) : null
  const [week, setWeek] = useState<number | null>(maxWeek)

  // `weeks` arrives asynchronously; adopt the latest one the first time it
  // resolves, but never fight a visitor who has already stepped elsewhere.
  useEffect(() => {
    setWeek((current) => current ?? maxWeek)
  }, [maxWeek])

  const { data, isLoading, error, refetch } = useWeekScoreboard(season, week ?? undefined)

  if (week === null || minWeek === null || maxWeek === null) return null

  const atStart = week <= minWeek
  const atEnd = week >= maxWeek

  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold leading-5">
          {data?.week_label ?? `Week ${week}`} <span className="font-normal text-ink-3">· {season}</span>
        </h2>
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={atStart}
            onClick={() => setWeek((w) => Math.max(minWeek, (w ?? maxWeek) - 1))}
            aria-label="Previous week"
            className="motion-state rounded border border-line p-1 text-ink-3 hover:border-line-strong hover:text-ink disabled:opacity-30 disabled:hover:border-line disabled:hover:text-ink-3"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            disabled={atEnd}
            onClick={() => setWeek((w) => Math.min(maxWeek, (w ?? maxWeek) + 1))}
            aria-label="Next week"
            className="motion-state rounded border border-line p-1 text-ink-3 hover:border-line-strong hover:text-ink disabled:opacity-30 disabled:hover:border-line disabled:hover:text-ink-3"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
      <QueryBoundary
        isLoading={isLoading}
        error={error}
        onRetry={refetch}
        isEmpty={!data?.games.length}
        emptyMessage="No games are recorded for this week."
      >
        <div className="flex gap-2 overflow-x-auto pb-1">
          {data?.games.map((game) => <GameCard key={game.game_id} game={game} />)}
        </div>
        {byesWorthNaming(data?.bye_teams).length ? (
          <p className="mt-2 text-[11px] text-ink-3">Bye: {byesWorthNaming(data?.bye_teams).join(', ')}</p>
        ) : null}
        {data?.note ? <p className="mt-2 text-[11px] text-ink-3">{data.note}</p> : null}
      </QueryBoundary>
    </section>
  )
}

function GameCard({ game }: { game: WeekGame }) {
  const decided = game.played && game.home_score != null && game.away_score != null
  const homeWon = decided && game.home_score! > game.away_score!
  const awayWon = decided && game.away_score! > game.home_score!
  const wp = (game.wp_sparkline ?? [])
    .map((point) => point?.[1] ?? null)
    .filter((v): v is number => v !== null)

  return (
    <GameLink
      gameId={game.game_id}
      className="motion-state block w-[172px] shrink-0 rounded-lg border border-line bg-raised px-3 py-2.5 no-underline hover:border-line-strong"
    >
      <TeamRow team={game.away} score={game.away_score} won={awayWon} played={game.played} />
      <TeamRow team={game.home} score={game.home_score} won={homeWon} played={game.played} />
      <div className="mt-2 flex h-[14px] items-center justify-between">
        {wp.length > 1 ? <Sparkline values={wp} title="Home win probability across the game" /> : <span />}
        {game.overtime ? <span className="text-[10px] text-ink-3">OT</span> : null}
      </div>
    </GameLink>
  )
}

function TeamRow({
  team,
  score,
  won,
  played,
}: {
  team: BrandTeam
  score: number | null | undefined
  won: boolean
  played: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="flex min-w-0 items-center gap-1.5">
        <Mark src={team.logo} label={team.abbr ?? '?'} size={16} />
        <span className={`truncate text-[13px] ${won ? 'font-semibold' : 'text-ink-2'}`}>{team.abbr}</span>
      </span>
      <span className={`shrink-0 text-[13px] tabular-nums ${won ? 'font-semibold text-positive' : 'text-ink-3'}`}>
        {played ? num(score) : 'Not played'}
      </span>
    </div>
  )
}
