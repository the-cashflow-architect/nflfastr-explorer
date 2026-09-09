import { NavLink } from 'react-router-dom'

/**
 * The same four destinations on all five player routes.
 *
 * Before this, the sub-pages had three different ways in and no way across:
 * splits were reachable only by prose on the game log, so the one thing this
 * product gives away that its competitor charges for was effectively hidden.
 * A persistent row fixes that structurally rather than by remembering to link.
 *
 * Neutral, not accent — the page's one accent belongs to its primary action.
 */
export function PlayerSubNav({
  gsisId,
  slug,
  /** Sub-pages that have no data for this player are not offered. */
  available,
}: {
  gsisId: string
  slug?: string
  available?: { splits?: boolean; advanced?: boolean; gamelog?: boolean }
}) {
  const base = `/players/${gsisId}`
  const items = [
    { to: slug ? `${base}/${slug}` : base, label: 'Overview', end: true, show: true },
    { to: `${base}/gamelog`, label: 'Game log', show: available?.gamelog !== false },
    { to: `${base}/splits`, label: 'Splits', show: available?.splits !== false },
    { to: `${base}/advanced`, label: 'Advanced', show: available?.advanced !== false },
  ].filter((item) => item.show)

  return (
    <nav aria-label="Player sections" className="flex flex-wrap gap-1 border-b border-line">
      {items.map((item) => (
        <NavLink
          key={item.label}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            [
              'motion-state relative px-2.5 py-1.5 text-[13px] no-underline',
              isActive ? 'text-ink' : 'text-ink-2 hover:text-ink',
            ].join(' ')
          }
        >
          {({ isActive }) => (
            <>
              {item.label}
              {isActive ? <span className="absolute inset-x-2.5 -bottom-px h-[2px] bg-accent" /> : null}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
