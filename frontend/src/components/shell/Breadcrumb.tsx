import { useContext, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BreadcrumbLabelContext, type CrumbLabels } from './breadcrumbContext'

/**
 * The trail is derived from the URL on every render, never from click history.
 *
 * That is the whole point: a cold-loaded deep link — the only kind anybody ever
 * shares — must render the correct trail immediately, and a trail built from
 * where you happened to click cannot. While a page's data is still loading, the
 * segment shows the label the URL itself implies (the team code, the season, the
 * slug in title case). An honest approximation beats a shimmer.
 */

export function BreadcrumbProvider({ children }: { children: React.ReactNode }) {
  const [labels, setLabels] = useState<CrumbLabels>({})
  const value = useMemo(
    () => ({
      labels,
      setLabel: (path: string, label: string) =>
        setLabels((current) => (current[path] === label ? current : { ...current, [path]: label })),
    }),
    [labels],
  )
  return <BreadcrumbLabelContext.Provider value={value}>{children}</BreadcrumbLabelContext.Provider>
}

interface Crumb {
  to: string
  label: string
}

const ROOTS: Record<string, string> = {
  players: 'Players',
  teams: 'Teams',
  seasons: 'Seasons',
  games: 'Games',
  leaders: 'Leaders',
  draft: 'Draft',
  finder: 'Finder',
  compare: 'Compare',
  glossary: 'Glossary',
  about: 'About',
}

const LEAVES: Record<string, string> = {
  gamelog: 'Game log',
  splits: 'Splits',
  advanced: 'Advanced',
  roster: 'Roster',
  standings: 'Standings',
  data: 'Data & methods',
}

function titleCase(segment: string): string {
  return segment
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function Breadcrumb() {
  const { pathname } = useLocation()
  const { labels } = useContext(BreadcrumbLabelContext)

  const crumbs = useMemo<Crumb[]>(() => {
    const segments = pathname.split('/').filter(Boolean)
    if (!segments.length) return []
    const out: Crumb[] = []
    let path = ''
    segments.forEach((segment, index) => {
      path += `/${segment}`
      // A player id is a routing detail, not a place. Its slug carries the name.
      if (index === 1 && segments[0] === 'players') return
      const known = index === 0 ? ROOTS[segment] : LEAVES[segment]
      out.push({ to: path, label: labels[path] ?? known ?? titleCase(segment) })
    })
    return out
  }, [pathname, labels])

  if (!crumbs.length) return null

  // Four segments is the ceiling; beyond that the middle elides rather than
  // wrapping the header onto a second line.
  const shown =
    crumbs.length <= 4 ? crumbs : [crumbs[0], { to: '', label: '…' }, ...crumbs.slice(-2)]

  return (
    <nav aria-label="Breadcrumb" className="mb-1 text-[11px] leading-4 text-ink-3">
      <ol className="flex flex-wrap items-center gap-1">
        <li>
          <Link to="/" className="no-underline hover:text-accent hover:underline">
            Gridiron
          </Link>
        </li>
        {shown.map((crumb, index) => (
          <li key={`${crumb.to}-${index}`} className="flex items-center gap-1">
            <span aria-hidden className="text-ink-3/60">
              /
            </span>
            {index === shown.length - 1 || !crumb.to ? (
              <span aria-current={crumb.to ? 'page' : undefined}>{crumb.label}</span>
            ) : (
              <Link to={crumb.to} className="no-underline hover:text-accent hover:underline">
                {crumb.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}
