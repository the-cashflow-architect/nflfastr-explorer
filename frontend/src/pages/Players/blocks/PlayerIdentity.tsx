import { Award } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CollegeLink, DraftClassLink } from '../../../components/ui/EntityLink'
import { height, num, plural } from '../../../design/format'
import type { PlayerHub } from '../../../api/endpoints'

/**
 * Who this player is, in two lines under the page title.
 *
 * The honors line is the one block here with a real trap in it. `draft_picks`
 * carries Pro Bowls, All-Pros and a weighted career AV for **drafted players
 * only**, and its plain career-AV column is empty in every row — so the label
 * and the caveat both come from the payload (`av_label`, `source_note`) rather
 * than from a sentence written here that would quietly go stale. An undrafted
 * player has no honors row at all, and the block is removed rather than shown
 * with zeroes.
 */

type Identity = PlayerHub['identity']

/** The single pipe-separated metadata line the page header allows. */
export function IdentityMeta({ identity }: { identity: Identity }) {
  const parts: React.ReactNode[] = []

  const position = [identity.position, identity.jersey_number ? `#${identity.jersey_number}` : null]
    .filter(Boolean)
    .join(' ')
  if (position) parts.push(<span key="pos">{position}</span>)

  if (identity.team) {
    parts.push(
      identity.team_href ? (
        <Link key="team" to={identity.team_href}>
          {identity.team}
        </Link>
      ) : (
        <span key="team">{identity.team}</span>
      ),
    )
  }

  parts.push(<span key="status">{identity.status_label}</span>)

  const size = [
    identity.height ? height(identity.height) : null,
    identity.weight ? `${num(identity.weight, 0)} lb` : null,
  ]
    .filter(Boolean)
    .join(', ')
  if (size) parts.push(<span key="size">{size}</span>)

  // Age is frequently absent in the player file; a missing birth date prints
  // nothing rather than a guess from the rookie season.
  if (identity.age) parts.push(<span key="age">{`Age ${num(identity.age, 0)}`}</span>)

  if (identity.rookie_season && identity.last_season) {
    parts.push(
      <span key="span">{`${identity.rookie_season}–${identity.last_season}`}</span>,
    )
  }
  if (identity.years_of_experience) {
    parts.push(<span key="exp">{plural(Math.round(identity.years_of_experience), 'season')}</span>)
  }

  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 ? <span className="px-1.5 text-ink-3">·</span> : null}
          {part}
        </span>
      ))}
    </>
  )
}

export function PlayerHeadshot({
  url,
  name,
  size = 40,
}: {
  url?: string | null
  name?: string | null
  size?: number
}) {
  const [broken, setBroken] = useState(false)
  if (!url || broken) {
    // No headshot is a gap, not a reason to draw a silhouette that implies one.
    return (
      <span
        aria-hidden
        className="flex h-full w-full items-center justify-center rounded-full border border-line text-[11px] text-ink-3"
      >
        {(name ?? '?').slice(0, 1)}
      </span>
    )
  }
  return (
    <img
      src={url}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setBroken(true)}
      className="h-full w-full rounded-full object-cover"
    />
  )
}

export function PlayerIdentity({ hub }: { hub: PlayerHub }) {
  const { identity, draft, honors } = hub
  return (
    <div className="mt-3 space-y-1 text-[12px] leading-5 text-ink-2">
      <p>
        {draft ? (
          <>
            <span className="text-ink-3">Draft </span>
            <DraftClassLink year={draft.season} />
            {draft.round ? <span>{` · Round ${draft.round}`}</span> : null}
            {draft.pick ? <span>{`, pick ${draft.pick}`}</span> : null}
            {draft.team ? (
              <>
                <span> · </span>
                {draft.team_href ? <Link to={draft.team_href}>{draft.team}</Link> : <span>{draft.team}</span>}
              </>
            ) : null}
          </>
        ) : (
          <span className="text-ink-3">No draft row on file for this player.</span>
        )}
        {identity.college ? (
          <>
            <span className="px-1.5 text-ink-3">|</span>
            <span className="text-ink-3">College </span>
            <CollegeLink college={identity.college} />
            {identity.college_conference ? (
              <span className="text-ink-3">{` · ${identity.college_conference}`}</span>
            ) : null}
          </>
        ) : null}
      </p>
      {honors ? <HonorsLine honors={honors} /> : null}
    </div>
  )
}

function HonorsLine({ honors }: { honors: NonNullable<PlayerHub['honors']> }) {
  const items: string[] = []
  if (honors.pro_bowls) items.push(`Pro Bowl ${num(honors.pro_bowls, 0)}×`)
  if (honors.all_pros) items.push(`All-Pro ${num(honors.all_pros, 0)}×`)
  if (honors.seasons_started) items.push(`${num(honors.seasons_started, 0)} seasons as a starter`)
  const av = honors.weighted_career_av ?? honors.draft_av ?? null

  if (!honors.hof && !items.length && av === null) return null

  const line = items.join(' · ')

  return (
    <>
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
        {honors.hof ? (
          <span className="inline-flex items-center gap-1 rounded border border-line-strong px-1.5 py-0.5 text-[11px] font-medium text-ink">
            <Award className="h-4 w-4" aria-hidden />
            Hall of Fame
          </span>
        ) : null}
        {line ? <span>{line}</span> : null}
        {av !== null ? (
          <span>
            {`${line ? '· ' : ''}${num(av, 0)} `}
            <span className="text-ink-3">{honors.av_label}</span>
          </span>
        ) : null}
      </p>
      <p className="text-[11px] leading-4 text-ink-3">{honors.source_note}</p>
    </>
  )
}
