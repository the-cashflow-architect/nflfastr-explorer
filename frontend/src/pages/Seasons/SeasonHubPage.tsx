import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useLeadersIndex, useSeasonHub, useSeasonIndex, useWeekScoreboard, type SeasonHub } from '../../api/endpoints'
import { QuadrantScatter } from '../../components/charts/QuadrantScatter'
import { PlayerLink } from '../../components/ui/EntityLink'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { num, signed } from '../../design/format'
import { PlayoffBracket } from './blocks/PlayoffBracket'
import { StandingsTable, type StandingsGroup } from './blocks/StandingsTable'
import { WeekGameCard } from './WeekPage'

type Conference = 'AFC' | 'NFC'
type LeaderCategory = keyof SeasonHub['leaders']
type LeaderRow = NonNullable<SeasonHub['leaders']['passing']>[number]

const CONFERENCES: Conference[] = ['AFC', 'NFC']

/** Groups a division-grouped standings payload into two conference groups,
 * sorted seed-first (unseeded teams follow, by winning percentage) — the
 * hub's own "re-sorts in place" toggle, done client-side because the hub
 * payload carries only one grouping and re-fetching for a local toggle would
 * turn a UI preference into a network round trip. */
function toConferenceGroups(groups: StandingsGroup[]): StandingsGroup[] {
  return CONFERENCES.map((conference) => {
    const teams = groups
      .filter((group) => group.conference === conference)
      .flatMap((group) => group.teams)
      .slice()
      .sort((a, b) => {
        const seedA = a.seed ?? 99
        const seedB = b.seed ?? 99
        if (seedA !== seedB) return seedA - seedB
        return (b.pct ?? 0) - (a.pct ?? 0)
      })
    return { label: conference, conference, division: null, teams }
  }).filter((group) => group.teams.length > 0)
}

/** Same derivation WeekPage uses for its own picker, kept local so this file
 * (which renders a page component) exports components only. */
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

/** Maps this payload's category ids to /api/leaders' category ids — the two
 * endpoints were built at different times and did not settle on one
 * vocabulary ("defense" here, "defence" there; "epa" here, "advanced"
 * there), so a "Full leaderboard" link has to bridge it explicitly rather
 * than assume the ids match. */
const LEADERS_CATEGORY_ID: Record<LeaderCategory, string> = {
  passing: 'passing',
  rushing: 'rushing',
  receiving: 'receiving',
  scoring: 'scoring',
  defense: 'defence',
  epa: 'advanced',
}

const LEADER_LABEL: Record<LeaderCategory, string> = {
  passing: 'Passing',
  rushing: 'Rushing',
  receiving: 'Receiving',
  scoring: 'Scoring',
  defense: 'Defense',
  epa: 'EPA per play',
}

const CATEGORY_ORDER: LeaderCategory[] = ['passing', 'rushing', 'receiving', 'scoring', 'defense', 'epa']

/** EPA is a per-play rate summed to a total and can be negative; every other
 * category is a counting stat that is usually a whole number but is not
 * guaranteed to be one (defensive scores blend several weighted counts) —
 * so a value that happens to carry a fraction keeps it instead of being
 * rounded into a false whole number. */
function leaderValue(value: number | null | undefined, category: LeaderCategory): string {
  if (category === 'epa') return signed(value, 1)
  if (value === null || value === undefined) return '—'
  return num(value, Number.isInteger(value) ? 0 : 1)
}

/**
 * The season cockpit: standings, playoff bracket, the EPA quadrant, and a
 * leaders snapshot, all one level deep from the week strip's primary action.
 *
 * Every block here is conditional on the payload actually carrying it — the
 * bracket most visibly, since roughly a third of any given season's life it
 * has not been played yet.
 */
export function SeasonHubPage() {
  const { season: seasonParam = '' } = useParams()
  const seasonNumber = Number(seasonParam)
  const season = Number.isFinite(seasonNumber) && seasonNumber > 0 ? seasonNumber : undefined

  const query = useSeasonHub(season)
  const seasonIndex = useSeasonIndex()
  const data = query.data

  useCrumbLabel(season ? `/seasons/${season}` : '', season ? `${season}` : undefined)

  const seasons = seasonIndex.data?.seasons.map((s) => s.season) ?? []
  const idx = season !== undefined ? seasons.indexOf(season) : -1
  const prevSeason = idx >= 0 && idx < seasons.length - 1 ? seasons[idx + 1] : undefined
  const nextSeason = idx > 0 ? seasons[idx - 1] : undefined

  return (
    <>
      <PageHeader
        title={`${season ?? seasonParam} NFL Season`}
        meta={
          season ? (
            <>
              <Link to={`/seasons/${season}/standings`} className="no-underline hover:text-accent hover:underline">
                Standings
              </Link>
              {' · '}
              <Link to="/leaders" className="no-underline hover:text-accent hover:underline">
                Leaders
              </Link>
              {data?.draft_href ? (
                <>
                  {' · '}
                  <Link to={data.draft_href} className="no-underline hover:text-accent hover:underline">
                    Draft class
                  </Link>
                </>
              ) : null}
            </>
          ) : undefined
        }
        prev={prevSeason ? { to: `/seasons/${prevSeason}`, label: `${prevSeason} season` } : undefined}
        next={nextSeason ? { to: `/seasons/${nextSeason}`, label: `${nextSeason} season` } : undefined}
      />

      <div className="mt-5">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <SeasonHubBody data={data} season={season ?? data.season} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function SeasonHubBody({ data, season }: { data: SeasonHub; season: number }) {
  const [standingsView, setStandingsView] = useState<'division' | 'conference'>('division')
  const [week, setWeek] = useState<number | undefined>(() => (data.weeks.length ? Math.max(...data.weeks) : undefined))
  const [category, setCategory] = useState<LeaderCategory | undefined>(
    () => CATEGORY_ORDER.find((id) => data.leaders[id]?.length) ?? undefined,
  )
  const navigate = useNavigate()

  const weekQuery = useWeekScoreboard(season, week)
  const leadersIndex = useLeadersIndex()

  const weekLabels = useMemo(() => buildWeekLabels(data.bracket), [data.bracket])
  const sortedWeeks = useMemo(() => [...data.weeks].sort((a, b) => a - b), [data.weeks])

  const teamConference = useMemo(() => {
    const map: Record<string, Conference> = {}
    for (const group of data.standings.groups) {
      for (const team of group.teams) {
        if (team.conference === 'AFC' || team.conference === 'NFC') map[team.abbr] = team.conference
      }
    }
    return map
  }, [data.standings.groups])

  const displayedGroups: StandingsGroup[] =
    standingsView === 'division' ? data.standings.groups : toConferenceGroups(data.standings.groups)

  const quadrantPoints = useMemo(
    () =>
      data.epa_quadrant
        .filter((p) => p.logo && p.off_epa !== null && p.off_epa !== undefined && p.def_epa !== null && p.def_epa !== undefined)
        .map((p) => ({ team: p.team, logo: p.logo as string, offense: p.off_epa as number, defense: p.def_epa as number })),
    [data.epa_quadrant],
  )
  const quadrantHrefs = useMemo(() => new Map(data.epa_quadrant.map((p) => [p.team, p.href])), [data.epa_quadrant])

  const availableCategories = CATEGORY_ORDER.filter((id) => data.leaders[id]?.length)
  const activeCategory = category && data.leaders[category]?.length ? category : availableCategories[0]
  const activeRows: LeaderRow[] = (activeCategory ? data.leaders[activeCategory] : undefined) ?? []
  const leaderHref = activeCategory
    ? leadersIndex.data?.categories.find((c) => c.id === LEADERS_CATEGORY_ID[activeCategory])?.href
    : undefined

  return (
    <>
      {sortedWeeks.length ? (
        <Section
          title="Scoreboard"
          note={weekQuery.data?.week_label ?? (week ? `Week ${week}` : undefined)}
          controls={
            <select
              aria-label="Jump to week"
              value={week ?? ''}
              onChange={(event) => setWeek(Number(event.target.value))}
              className="motion-state rounded border border-line bg-raised px-2 py-1 text-[12px] text-ink hover:border-line-strong"
            >
              {sortedWeeks.map((w) => (
                <option key={w} value={w}>
                  {weekLabels.get(w) ?? `Week ${w}`}
                </option>
              ))}
            </select>
          }
        >
          <QueryBoundary
            isLoading={weekQuery.isLoading}
            error={weekQuery.error}
            onRetry={() => void weekQuery.refetch()}
            isEmpty={!weekQuery.data?.games.length}
            emptyMessage="No games are scheduled for this week."
          >
            <div className="flex gap-2 overflow-x-auto pb-1">
              {weekQuery.data?.games.map((game) => (
                <div key={game.game_id} className="w-[188px] shrink-0">
                  <WeekGameCard game={game} />
                </div>
              ))}
            </div>
            {weekQuery.data?.bye_teams.length ? (
              <p className="mt-2 text-[11px] text-ink-3">Bye: {weekQuery.data.bye_teams.join(', ')}</p>
            ) : null}
          </QueryBoundary>
          {week ? (
            <Link
              to={`/seasons/${season}/week/${week}`}
              className="mt-2 inline-block text-[11px] text-ink-3 no-underline hover:text-accent hover:underline"
            >
              Full week scoreboard →
            </Link>
          ) : null}
        </Section>
      ) : null}

      <Section
        title="Standings"
        controls={
          <Segmented
            ariaLabel="Standings grouping"
            value={standingsView}
            onChange={setStandingsView}
            options={[
              { value: 'division', label: 'Division' },
              { value: 'conference', label: 'Conference seeding' },
            ]}
          />
        }
      >
        <StandingsTable groups={displayedGroups} variant="compact" />
        <Link
          to={`/seasons/${season}/standings`}
          className="mt-2 inline-block text-[11px] text-ink-3 no-underline hover:text-accent hover:underline"
        >
          Full standings with ratings and tiebreak basis →
        </Link>
      </Section>

      {data.bracket ? (
        <Section title="Playoff bracket">
          <PlayoffBracket bracket={data.bracket} teamConference={teamConference} season={season} />
        </Section>
      ) : null}

      {quadrantPoints.length ? (
        <Section title="League EPA quadrant" note="Offence vs. defence, both per play">
          <QuadrantScatter points={quadrantPoints} onSelect={(team) => {
            const href = quadrantHrefs.get(team)
            if (href) navigate(href)
          }} />
        </Section>
      ) : null}

      {availableCategories.length ? (
        <Section
          title="League leaders"
          controls={
            <Segmented
              ariaLabel="Leader category"
              value={activeCategory ?? availableCategories[0]}
              onChange={setCategory}
              options={availableCategories.map((id) => ({ value: id, label: LEADER_LABEL[id] }))}
            />
          }
        >
          <ol className="grid gap-x-6 sm:grid-cols-2">
            {activeRows.slice(0, 10).map((row) => (
              <li key={row.gsis_id} className="flex items-baseline gap-2 border-b border-row-rule py-1">
                <span className="w-4 shrink-0 text-[11px] text-ink-3">{row.rank}</span>
                <span className="min-w-0 flex-1 truncate text-[13px]">
                  <PlayerLink id={row.gsis_id} name={row.player} />
                  {row.position ? <span className="ml-1.5 text-[11px] text-ink-3">{row.position}</span> : null}
                </span>
                <span className="shrink-0 text-[13px] tabular-nums">
                  {activeCategory ? leaderValue(row.value, activeCategory) : '—'}
                  {row.computed_by_us ? <ComputedByUs formula={row.note ?? 'Calculated by Gridiron.'} /> : null}
                </span>
              </li>
            ))}
          </ol>
          {leaderHref ? (
            <Link
              to={`${leaderHref}?scope=season&season_min=${season}&season_max=${season}`}
              className="mt-2 inline-block text-[11px] text-ink-3 no-underline hover:text-accent hover:underline"
            >
              Full leaderboard →
            </Link>
          ) : null}
        </Section>
      ) : null}
    </>
  )
}
