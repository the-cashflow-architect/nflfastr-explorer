import { Link } from 'react-router-dom'
import { useCoverageQuery } from '../api/endpoints'
import { PageHeader } from '../components/ui/Page'

interface CoverageData {
  coverage_windows: Record<string, { first_season: number } | undefined>
  latest_completed_season: number | null
}

/**
 * The one page nobody links to on purpose. It stays honest the same way the
 * rest of the product does: the floor season comes from the live coverage
 * payload, never a number typed into this file — a route that outlives a
 * data-window change should not go on quoting the old one.
 */
export function NotFoundPage() {
  const coverage = useCoverageQuery()
  const cov = coverage.data as CoverageData | undefined
  const from = cov?.coverage_windows.stats?.first_season
  const to = cov?.latest_completed_season

  return (
    <>
      <PageHeader title="Nothing here" meta="That address does not match a player, team, game or season we hold." />
      <p className="mt-4 text-[13px] leading-5 text-ink-2">
        {from && to ? (
          <>Our play-level data covers {from}–{to}, the modern era only — nothing older.</>
        ) : (
          <>Our data has a modern-era floor, not a century of history.</>
        )}{' '}
        If the link is old, it may point at something renamed or removed rather than something we never had —{' '}
        <Link to="/about/data" className="no-underline hover:text-accent hover:underline">
          see exactly what we do and don't have
        </Link>
        , or{' '}
        <Link to="/" className="no-underline hover:text-accent hover:underline">
          start over from the home page
        </Link>
        .
      </p>
    </>
  )
}
