import { Link } from 'react-router-dom'
import { useCoverageQuery, useSeasonIndex, type SeasonIndex } from '../../api/endpoints'
import { PageHeader } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { gameDate } from '../../design/format'

type SeasonRow = SeasonIndex['seasons'][number]

interface CoverageData {
  coverage_windows: Record<string, { first_season: number; note: string } | undefined>
  latest_completed_season: number | null
  generated_at: string
}

/**
 * The menu: pick a season. Newest first, because that is the one most people
 * came for, and every cell that has a real answer is a real link — a season
 * still in progress has no champion yet and says so instead of guessing.
 */
export function SeasonIndexPage() {
  const query = useSeasonIndex()
  const coverage = useCoverageQuery()
  const data = query.data
  const cov = coverage.data as CoverageData | undefined

  const first = data?.seasons.at(-1)?.season
  const last = data?.seasons[0]?.season

  return (
    <>
      <PageHeader
        title="Seasons"
        meta={first && last ? `Modern era — ${first} through ${last}. We do not have pre-${first} seasons.` : undefined}
      />

      <div className="mt-5">
        <QueryBoundary
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => void query.refetch()}
          isEmpty={!data?.seasons.length}
          emptyMessage="No seasons are loaded yet."
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {data?.seasons.map((season) => <SeasonCard key={season.season} season={season} />)}
          </div>
        </QueryBoundary>

        <CoverageStrip coverage={cov} coverageHref={data?.coverage_href} />
      </div>
    </>
  )
}

function SeasonCard({ season }: { season: SeasonRow }) {
  return (
    <div className="rounded-lg border border-line bg-raised p-3">
      <Link
        to={season.href}
        className="text-[18px] font-semibold leading-6 text-ink no-underline hover:text-accent hover:underline"
      >
        {season.season}
      </Link>
      {season.complete ? (
        <dl className="mt-1.5 space-y-0.5 text-[12px] leading-4">
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-ink-3">Champion</dt>
            <dd>
              <TeamCell abbr={season.champion} href={season.champion_href} />
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-ink-3">Top scoring</dt>
            <dd>
              <TeamCell abbr={season.top_scoring_team} href={season.top_scoring_team_href} />
            </dd>
          </div>
        </dl>
      ) : (
        <p className="mt-1.5 text-[12px] leading-4 text-ink-3">Season in progress — no champion yet.</p>
      )}
    </div>
  )
}

/** The payload hands us the href directly — building `/teams/{abbr}/{season}`
 * by hand here would drift the moment a franchise's route shape changes. */
function TeamCell({ abbr, href }: { abbr: string | null | undefined; href: string | null | undefined }) {
  if (!abbr) return <span className="text-ink-3">—</span>
  if (!href) return <span>{abbr}</span>
  return (
    <Link to={href} className="no-underline hover:text-accent hover:underline">
      {abbr}
    </Link>
  )
}

function CoverageStrip({ coverage, coverageHref }: { coverage: CoverageData | undefined; coverageHref?: string }) {
  if (!coverage) return null
  const w = coverage.coverage_windows
  const parts = [
    w.stats?.first_season && coverage.latest_completed_season
      ? `Play-level data ${w.stats.first_season}–${coverage.latest_completed_season}`
      : null,
    w.next_gen_stats?.first_season ? `Next Gen Stats ${w.next_gen_stats.first_season}+` : null,
    w.snap_counts?.first_season ? `snap counts ${w.snap_counts.first_season}+` : null,
    w.draft?.first_season ? `draft ${w.draft.first_season}+` : null,
  ].filter((part): part is string => !!part)

  return (
    <p className="mt-6 border-t border-line pt-3 text-[11px] leading-4 text-ink-3">
      {parts.join(' · ')}
      {parts.length ? ' · ' : ''}
      last refreshed {gameDate(coverage.generated_at)}
      {' — '}
      <Link to={coverageHref ?? '/about/data'} className="no-underline hover:text-accent hover:underline">
        what we have and don't
      </Link>
    </p>
  )
}
