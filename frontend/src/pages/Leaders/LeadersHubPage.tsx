import { Link } from 'react-router-dom'
import { useLeadersIndex, type LeadersIndex } from '../../api/endpoints'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { PageHeader, Section } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'

/**
 * The menu for every leaderboard the product serves. Nothing here ranks
 * anybody — it is a table of contents, one entry per stat, each carrying the
 * window it actually covers rather than the page's blanket modern-era claim.
 * CPOE and Next Gen Stats boards start later than 1999, and a visitor who only
 * reads the top-of-page era badge would otherwise assume they do not.
 */

export function LeadersHubPage() {
  const query = useLeadersIndex()
  const data = query.data

  return (
    <>
      <PageHeader
        title="Leaders"
        meta={data ? data.note : 'Ranked boards across every stat the season and weekly player files carry.'}
      />

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <Hub data={data} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function Hub({ data }: { data: LeadersIndex }) {
  // Passing yards is the one board every visitor recognises, so it is the
  // demonstration link for the three quick entry points below — not a claim
  // that it is special, just a door into scopes this menu does not switch.
  const flagship = data.categories.find((category) => category.id === 'passing')?.href

  return (
    <>
      <EraBadge from={data.era.from} to={data.era.to ?? undefined} note={data.era.note} className="mb-4" />

      {flagship ? (
        <div className="mb-6 flex flex-wrap gap-x-4 gap-y-1 rounded-md border border-line bg-raised px-3 py-2.5 text-[12px]">
          <span className="text-ink-3">Quick links:</span>
          <Link to={`${flagship}?active_only=true`}>Active-player leaders</Link>
          <Link to={`${flagship}?scope=season`}>Single-season records</Link>
          <Link to={`${flagship}?scope=game`}>Single-game records</Link>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.categories.map((category) => (
          <div key={category.id} className="rounded-lg border border-line bg-raised p-3">
            <Link to={category.href} className="text-[14px] font-semibold no-underline">
              {category.label}
            </Link>
            <p className="mb-2 text-[11px] leading-4 text-ink-3">{category.description}</p>
            <ul className="space-y-1.5 border-t border-line pt-2">
              {category.stats.map((stat) => (
                <li key={stat.id} className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate text-[13px]">
                    <Link to={stat.href}>{stat.label}</Link>
                    {stat.computed_by_us ? (
                      <ComputedByUs formula={stat.formula ?? stat.definition} label="how this stat is calculated" />
                    ) : null}
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-3">
                    {stat.era.from}–{stat.era.to ?? 'present'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {data.unavailable?.length ? (
        <Section title="Not available on this deployment" note={`${data.unavailable.length} board${data.unavailable.length === 1 ? '' : 's'}`}>
          <ul className="space-y-1 text-[12px] text-ink-3">
            {data.unavailable.map((board) => (
              <li key={`${board.category}-${board.stat}`}>
                {board.label} — {board.reason}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  )
}
