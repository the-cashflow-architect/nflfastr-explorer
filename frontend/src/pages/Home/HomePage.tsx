import {
  BarChart3,
  ClipboardList,
  GitCompare,
  ListOrdered,
  Search,
  ShieldHalf,
  SlidersHorizontal,
  Users,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCoverageQuery, useSeasonHub, useWeekScoreboard } from '../../api/endpoints'
import { SearchPalette } from '../../components/search/SearchLauncher'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { gameDate } from '../../design/format'
import { StandingsPeek } from './StandingsPeek'
import { WeekStrip } from './WeekStrip'

/**
 * The five-second-glance test for the whole product: one oversized search
 * field (the only accent-coloured element on the page), a few real links to
 * prove the data is real, last week's scores, a standings peek, and a way to
 * every top-level route. Nothing here requires a page load to explore one
 * level deeper.
 */

/** The shape actually returned by /api/coverage (see docs' coverage.json sample). */
interface CoverageData {
  datasets: { loaded_at: string | null }[]
  coverage_windows: Record<string, { first_season: number; note: string } | undefined>
  latest_completed_season: number | null
  latest_season_with_games: number | null
  generated_at: string
}

export function HomePage() {
  const coverage = useCoverageQuery()
  const cov = coverage.data as CoverageData | undefined
  const season = cov?.latest_completed_season ?? cov?.latest_season_with_games ?? null

  const seasonHub = useSeasonHub(season ?? undefined)
  const weeks = seasonHub.data?.weeks ?? []
  const latestWeek = weeks.length ? Math.max(...weeks) : undefined
  // Same query key WeekStrip opens with — React Query serves this from the
  // same cache entry rather than firing a second request.
  const latestWeekQuery = useWeekScoreboard(season ?? undefined, latestWeek)

  const chips = useMemo(
    () => buildChips(latestWeekQuery.data, seasonHub.data?.standings, season),
    [latestWeekQuery.data, seasonHub.data, season],
  )

  return (
    <div>
      <SearchHero />

      {chips.length ? (
        <div className="mb-8 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5">
          {chips.map((chip) => (
            <Link
              key={chip.key}
              to={chip.to}
              className="text-[12px] text-ink-2 no-underline hover:text-accent hover:underline"
            >
              {chip.label}
            </Link>
          ))}
        </div>
      ) : null}

      <QueryBoundary
        isLoading={coverage.isLoading || seasonHub.isLoading}
        error={coverage.error ?? seasonHub.error}
        onRetry={() => {
          void coverage.refetch()
          void seasonHub.refetch()
        }}
        isEmpty={!season || !seasonHub.data}
        emptyMessage="Season data is not available right now."
      >
        {season && seasonHub.data ? (
          <>
            <WeekStrip season={season} weeks={weeks} />
            <StandingsPeek season={season} standings={seasonHub.data.standings} />
          </>
        ) : null}
      </QueryBoundary>

      <EntryTiles />

      <CoverageFootline coverage={cov} />
    </div>
  )
}

function SearchHero() {
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // Autofocus is a desktop courtesy — on a phone it would pop the keyboard
    // over half the page before a visitor has decided they want it.
    if (window.matchMedia('(min-width: 768px)').matches) inputRef.current?.focus()
  }, [])

  return (
    <div className="py-10 text-center sm:py-14">
      <div className="mx-auto max-w-xl">
        <label htmlFor="home-search" className="sr-only">
          Find any player, team, or game
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-3" />
          <input
            id="home-search"
            ref={inputRef}
            type="text"
            readOnly
            onFocus={() => setOpen(true)}
            onClick={() => setOpen(true)}
            placeholder="Find any player, team, or game"
            className="motion-state w-full cursor-pointer rounded-xl border border-line bg-raised py-4 pl-12 pr-4 text-[16px] outline-none placeholder:text-ink-3 focus:border-accent focus:ring-2 focus:ring-accent/30 sm:text-[18px]"
          />
        </div>
      </div>
      {open ? <SearchPalette onClose={() => setOpen(false)} /> : null}
    </div>
  )
}

interface Chip {
  key: string
  label: string
  to: string
}

function buildChips(
  week: ReturnType<typeof useWeekScoreboard>['data'],
  standings: NonNullable<ReturnType<typeof useSeasonHub>['data']>['standings'] | undefined,
  season: number | null,
): Chip[] {
  const chips: Chip[] = []

  const topPlayer = week?.week_leaders?.by_epa?.[0]
  if (topPlayer?.gsis_id && topPlayer.player) {
    chips.push({ key: 'player', label: topPlayer.player, to: `/players/${topPlayer.gsis_id}` })
  }

  if (standings && season) {
    const leader = standings.groups
      .flatMap((group) => group.teams)
      .filter((team) => team.division_rank === 1 && team.pct !== null && team.pct !== undefined)
      .sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0))[0]
    if (leader) {
      chips.push({ key: 'team', label: leader.abbr, to: `/teams/${leader.abbr}/${season}` })
    }
  }

  const played = week?.games.filter((g) => g.played && g.home_score !== null && g.away_score !== null) ?? []
  const marquee = [...played].sort(
    (a, b) => Math.abs(b.biggest_play?.wpa ?? 0) - Math.abs(a.biggest_play?.wpa ?? 0),
  )[0]
  if (marquee) {
    // Guaranteed non-null by the `played` filter above.
    chips.push({
      key: 'game',
      label: `${marquee.away.abbr} ${marquee.away_score!}–${marquee.home_score!} ${marquee.home.abbr}`,
      to: `/games/${marquee.game_id}`,
    })
  }

  return chips
}

// Copy deliberately names no year: the real floor (modern-era stats vs. the
// deeper draft archive) lives in /api/coverage, not in this file.
const ENTRY_TILES = [
  { to: '/players', label: 'Players', copy: 'Every modern-era player, searchable and sortable.', icon: Users },
  { to: '/teams', label: 'Teams', copy: 'All 32 franchises, season by season.', icon: ShieldHalf },
  { to: '/seasons', label: 'Seasons', copy: 'Every modern-era season, one page each.', icon: ClipboardList },
  { to: '/leaders', label: 'Leaders', copy: 'Leaderboards across career, season and game scope.', icon: ListOrdered },
  { to: '/draft', label: 'Draft', copy: 'Every draft class in our archive, round by round.', icon: BarChart3 },
  { to: '/finder', label: 'Finder', copy: 'Build any leaderboard, split or streak yourself.', icon: SlidersHorizontal },
  { to: '/compare', label: 'Compare', copy: 'Line up two to six players or teams side by side.', icon: GitCompare },
]

function EntryTiles() {
  return (
    <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {ENTRY_TILES.map(({ to, label, copy, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          className="motion-state rounded-lg border border-line bg-raised px-3 py-3 no-underline hover:border-line-strong"
        >
          <span className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
            <Icon className="h-4 w-4 text-ink-3" />
            {label}
          </span>
          <span className="mt-1 block text-[11px] leading-4 text-ink-3">{copy}</span>
        </Link>
      ))}
    </div>
  )
}

function CoverageFootline({ coverage }: { coverage: CoverageData | undefined }) {
  if (!coverage) return null
  const w = coverage.coverage_windows
  const stats = w.stats?.first_season
  const last = coverage.latest_completed_season
  const parts: string[] = []
  if (stats && last) parts.push(`Play-level data ${stats}–${last}`)
  if (w.next_gen_stats?.first_season) parts.push(`Next Gen Stats ${w.next_gen_stats.first_season}+`)
  if (w.snap_counts?.first_season) parts.push(`snap counts ${w.snap_counts.first_season}+`)
  if (w.draft?.first_season) parts.push(`draft ${w.draft.first_season}+`)

  return (
    <p className="border-t border-line pt-3 text-[11px] leading-4 text-ink-3">
      {parts.join(' · ')}
      {parts.length ? ' · ' : ''}
      last refreshed {gameDate(coverage.generated_at)}
      {' — '}
      <Link to="/about/data" className="no-underline hover:text-accent hover:underline">
        what we have and don't
      </Link>
    </p>
  )
}
