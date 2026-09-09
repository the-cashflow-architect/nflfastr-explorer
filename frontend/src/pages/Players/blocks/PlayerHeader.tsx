import { Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PlayerSubNav } from '../../../components/ui/PlayerSubNav'
import { Segmented } from '../../../components/ui/Page'
import type { PlayerHub } from '../../../api/endpoints'
import { PlayerHeadshot } from './PlayerIdentity'

/**
 * The chrome the four player cockpits share: the sub-navigation, a neutral
 * Compare action beside it, and — on the sub-pages — a mini identity bar that
 * stays put while a twenty-season game log scrolls.
 *
 * The bar exists because the sub-pages are where a visitor loses the thread:
 * eighty rows down a splits table, nothing on screen says whose splits these
 * are. It is deliberately quiet — a 24px headshot and a line of text — and it
 * carries no accent, because the page's one accent belongs to its own action.
 */

/** Sub-nav plus Compare, for the hub's header. */
export function PlayerNavRow({
  gsisId,
  slug,
  available,
}: {
  gsisId: string
  slug?: string
  available?: PlayerHub['available_tabs']
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <PlayerSubNav gsisId={gsisId} slug={slug} available={available} />
      <CompareAction gsisId={gsisId} />
    </div>
  )
}

/**
 * Neutral by design: Compare is a second destination, not the page's primary
 * action, and two accent-coloured things on one screen means one of them is
 * wrong.
 */
export function CompareAction({ gsisId }: { gsisId: string }) {
  return (
    <Link
      to={`/compare?entities=${encodeURIComponent(gsisId)}`}
      className="motion-state mb-1 inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-[12px] no-underline hover:border-line-strong"
    >
      <Users className="h-4 w-4" aria-hidden />
      Compare
    </Link>
  )
}

export function PlayerMiniHeader({
  hub,
  gsisId,
  section,
}: {
  hub?: PlayerHub
  gsisId: string
  section: string
}) {
  const identity = hub?.identity
  const slug = identity?.slug ?? undefined
  const hubHref = `/players/${gsisId}${slug ? `/${slug}` : ''}`
  const facts = [identity?.position, identity?.team, identity?.status_label].filter(Boolean).join(' · ')

  return (
    // The app shell's own header is sticky: 44px on desktop, plus a second nav
    // row under 768px. These offsets park the bar directly beneath it.
    <div className="sticky top-[76px] z-30 -mx-4 mb-3 bg-page/95 px-4 pt-2 backdrop-blur sm:-mx-6 sm:px-6 md:top-[44px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="h-6 w-6 shrink-0">
          <PlayerHeadshot url={identity?.headshot_url} name={identity?.display_name} size={24} />
        </div>
        <Link to={hubHref} className="text-[13px] font-medium no-underline hover:underline">
          {identity?.display_name ?? 'Player'}
        </Link>
        {facts ? <span className="text-[11px] text-ink-3">{facts}</span> : null}
        <span className="text-[11px] text-ink-3">{section}</span>
        <div className="ml-auto">
          <CompareAction gsisId={gsisId} />
        </div>
      </div>
      <PlayerSubNav
        gsisId={gsisId}
        slug={slug}
        available={hub?.available_tabs}
      />
    </div>
  )
}

/**
 * The season control every sub-page opens with. A career of twenty-seven
 * seasons wraps to a second row rather than hiding behind a dropdown: the
 * seasons themselves are the navigation.
 */
export function SeasonPicker({
  seasons,
  value,
  onChange,
  allValue,
  allLabel,
  ariaLabel,
}: {
  seasons: number[]
  value: string
  onChange: (value: string) => void
  allValue: string
  allLabel: string
  ariaLabel: string
}) {
  const options = [
    { value: allValue, label: allLabel },
    ...seasons.map((season) => ({ value: String(season), label: String(season) })),
  ]
  return <Segmented options={options} value={value} onChange={onChange} ariaLabel={ariaLabel} />
}
