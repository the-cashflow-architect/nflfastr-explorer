import { Link } from 'react-router-dom'
import { useCoverageQuery } from '../../api/endpoints'

/**
 * The footer's one honest sentence about what this site knows, built from the
 * server's actual load log rather than from copy somebody wrote once.
 *
 * It replaces the "Live nflverse" badge the old header carried: nflverse
 * publishes after games, there is no live feed, and a green dot implying
 * otherwise was the least true thing on the page.
 *
 * Every window here comes from the payload. Typing a year into this component
 * is how the footer ends up claiming coverage the database does not have.
 */
export function CoverageLine() {
  const { data } = useCoverageQuery()
  if (!data) return null

  const windows = data.coverage_windows ?? {}
  const stats = windows.stats?.first_season
  const last = data.latest_completed_season

  const parts: string[] = []
  if (stats && last) parts.push(`Play-level data ${stats}–${last}`)
  if (windows.next_gen_stats?.first_season) parts.push(`Next Gen Stats ${windows.next_gen_stats.first_season}+`)
  if (windows.snap_counts?.first_season) parts.push(`snap counts ${windows.snap_counts.first_season}+`)
  if (windows.draft?.first_season) parts.push(`draft ${windows.draft.first_season}+`)

  const refreshed = data.generated_at?.slice(0, 10)

  return (
    <span>
      {parts.join(' · ')}
      {refreshed ? ` · updated ${refreshed}` : null}{' '}
      <Link to="/about/data" className="no-underline hover:underline">
        What we do and don’t have
      </Link>
    </span>
  )
}
