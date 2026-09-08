import { Link } from 'react-router-dom'

/**
 * The two components that keep the product honest about what it knows.
 *
 * They exist so that coverage copy is never written by hand on a page. A block
 * whose data starts later than the page implies says so, in the same words, in
 * the same place, every time — and because the windows come from the coverage
 * payload rather than from constants in the component, they cannot drift from
 * what was actually loaded.
 */

export function EraBadge({
  from,
  to,
  note,
  className = '',
}: {
  from: number
  to?: number
  note?: string
  className?: string
}) {
  return (
    <p className={`text-[11px] leading-[14px] text-ink-3 ${className}`}>
      {to ? `${from}–${to}` : `${from} onward`}
      {note ? ` · ${note}` : null}
    </p>
  )
}

/**
 * Marks a number we calculated rather than read from a source, linking to the
 * formula. Anything derived — SRS, Pythagorean wins, percentiles, the
 * snap-share start proxy, fantasy points — carries this or it is passing itself
 * off as official.
 */
export function ComputedByUs({
  formula,
  anchor,
  label = 'how this is calculated',
}: {
  formula: string
  anchor?: string
  label?: string
}) {
  return (
    <Link
      to={`/about/data${anchor ? `#${anchor}` : ''}`}
      title={`${formula} — ${label}`}
      aria-label={`${label}: ${formula}`}
      className="ml-1 align-super text-[9px] text-ink-3 no-underline hover:text-accent"
    >
      ƒ
    </Link>
  )
}

/**
 * The empty state. Always a sentence saying *why* there is nothing, because
 * "no data" and "this player retired before we have data" are different facts
 * and only one of them means the site is working correctly.
 */
export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-1 py-6 text-[13px] text-ink-3">{children}</p>
}
