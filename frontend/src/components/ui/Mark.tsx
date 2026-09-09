import { useState } from 'react'

/**
 * A team logo or a player headshot, with a fallback that is not a broken icon.
 *
 * Every image on this site is hotlinked from a third party — ESPN for logos,
 * the NFL's own CDN for headshots. Those URLs go stale, get blocked by a
 * network, or simply 404 for a fringe player, and a browser's broken-image
 * glyph in the middle of a team header reads as "this site is broken" far more
 * loudly than a missing picture warrants.
 *
 * So a failed load collapses to the thing the image was standing in for: the
 * team's abbreviation, or the player's initials. That is also what renders
 * while offline, and what a screen reader gets either way.
 */
export function Mark({
  src,
  /** The abbreviation or name the mark represents; also the fallback text. */
  label,
  size = 24,
  rounded,
  className = '',
}: {
  src?: string | null
  label: string
  size?: number
  /** Headshots are circles; logos are not. */
  rounded?: boolean
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const shape = rounded ? 'rounded-full' : 'rounded'
  const style = { width: size, height: size }

  if (!src || failed) {
    return (
      <span
        aria-hidden
        style={{ ...style, fontSize: Math.max(9, Math.round(size * 0.36)) }}
        className={`inline-flex shrink-0 items-center justify-center border border-line bg-sunken font-semibold uppercase leading-none tracking-tight text-ink-3 ${shape} ${className}`}
      >
        {initials(label)}
      </span>
    )
  }

  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
      style={style}
      className={`shrink-0 object-contain ${shape} ${className}`}
    />
  )
}

function initials(label: string): string {
  const trimmed = label.trim()
  if (!trimmed) return '?'
  // A team code is already the right thing to show; a person's name is not.
  if (trimmed.length <= 3) return trimmed
  const words = trimmed.split(/\s+/)
  if (words.length === 1) return words[0].slice(0, 2)
  return (words[0][0] + words[words.length - 1][0]).slice(0, 2)
}
