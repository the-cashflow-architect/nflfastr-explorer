import { Link } from 'react-router-dom'
import { slugify } from '../../design/format'

/**
 * Every reference to a player, team, game, season or draft class in the product
 * goes through here.
 *
 * The rule that matters is the negative one: **an entity with no id renders as
 * plain text, never as a link.** Play-by-play carries names without ids for some
 * rows, and a name that looks clickable and 404s is worse than a name that does
 * not. Enforcing it in one component rather than in forty tables is the only way
 * it stays true.
 */

interface PlayerLinkProps {
  id: string | null | undefined
  name: string | null | undefined
  className?: string
}

export function PlayerLink({ id, name, className }: PlayerLinkProps) {
  if (!name) return <span className="text-ink-3">—</span>
  if (!id) return <span className={className}>{name}</span>
  return (
    <Link to={`/players/${id}/${slugify(name)}`} className={className}>
      {name}
    </Link>
  )
}

interface TeamLinkProps {
  abbr: string | null | undefined
  /** Present in a season-scoped context, which links to that team-season. */
  season?: number
  children?: React.ReactNode
  className?: string
}

export function TeamLink({ abbr, season, children, className }: TeamLinkProps) {
  if (!abbr) return <span className="text-ink-3">—</span>
  const to = season ? `/teams/${abbr}/${season}` : `/teams/${abbr}`
  return (
    <Link to={to} className={className}>
      {children ?? abbr}
    </Link>
  )
}

export function GameLink({
  gameId,
  children,
  className,
}: {
  gameId: string | null | undefined
  children: React.ReactNode
  className?: string
}) {
  if (!gameId) return <span className={className}>{children}</span>
  return (
    <Link to={`/games/${gameId}`} className={className}>
      {children}
    </Link>
  )
}

export function SeasonLink({
  season,
  team,
  children,
  className,
}: {
  season: number | null | undefined
  /** A season inside a team context links to that team's season, not the league's. */
  team?: string
  children?: React.ReactNode
  className?: string
}) {
  if (season === null || season === undefined) return <span className="text-ink-3">—</span>
  const to = team ? `/teams/${team}/${season}` : `/seasons/${season}`
  return (
    <Link to={to} className={className}>
      {children ?? season}
    </Link>
  )
}

export function DraftClassLink({
  year,
  children,
  className,
}: {
  year: number | null | undefined
  children?: React.ReactNode
  className?: string
}) {
  if (!year) return <span className="text-ink-3">—</span>
  return (
    <Link to={`/draft/${year}`} className={className}>
      {children ?? year}
    </Link>
  )
}

/**
 * A college links to a real query rather than to a page we do not have. The
 * alternative — a dead-looking plain string, or a link to a stub — both fail the
 * same test: every reference in the product goes somewhere useful or is not a
 * reference.
 */
export function CollegeLink({ college, className }: { college: string | null | undefined; className?: string }) {
  if (!college) return <span className="text-ink-3">—</span>
  return (
    <Link to={`/finder?mode=player_season&college=${encodeURIComponent(college)}`} className={className}>
      {college}
    </Link>
  )
}
