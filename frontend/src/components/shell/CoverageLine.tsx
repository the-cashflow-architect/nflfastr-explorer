import { Link } from 'react-router-dom'
import { useCoverage } from '../../api/coverage'

/**
 * The footer's one honest sentence about what this site knows, built from the
 * server's actual load log rather than from copy somebody wrote once.
 *
 * It replaces the "Live nflverse" badge the old header carried: nflverse
 * publishes after games, there is no live feed, and a green dot implying
 * otherwise was the least true thing on the page.
 */
export function CoverageLine() {
  const { data } = useCoverage()
  if (!data) return null

  const stats = data.windows.stats_first_season
  const last = data.latest_completed_season
  const parts: string[] = []
  if (stats && last) parts.push(`Play-level data ${stats}–${last}`)
  if (data.windows.ngs_first_season) parts.push(`Next Gen Stats ${data.windows.ngs_first_season}+`)
  if (data.windows.snap_counts_first_season) parts.push(`snap counts ${data.windows.snap_counts_first_season}+`)
  if (data.windows.draft_first_season) parts.push(`draft ${data.windows.draft_first_season}+`)

  const refreshed = data.datasets
    .map((d) => d.loaded_at)
    .filter(Boolean)
    .sort()
    .pop()

  return (
    <span>
      {parts.join(' · ')}
      {refreshed ? ` · updated ${refreshed.slice(0, 10)}` : null}{' '}
      <Link to="/about/data" className="no-underline hover:underline">
        What we do and don’t have
      </Link>
    </span>
  )
}
