import { Link, useSearchParams } from 'react-router-dom'
import { useTeamIndex, type TeamIndex } from '../../api/endpoints'
import { PageHeader, Section } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { ordinal, plural, record as formatRecord, winPct } from '../../design/format'
import { Mark } from '../../components/ui/Mark'

type Card = TeamIndex['conferences'][number]['divisions'][number]['teams'][number]

/**
 * The menu: one season's clubs in that season's real divisions.
 *
 * The division panels come from the payload and are never assumed — 2001 is six
 * divisions and thirty-one clubs, and a page that hard-codes eight panels is
 * wrong on three of the twenty-seven seasons we cover.
 */
export function TeamIndexPage() {
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('season'))
  const query = useTeamIndex({ season: Number.isFinite(requested) && requested > 0 ? requested : null })
  const data = query.data

  const chooseSeason = (season: number) => {
    const next = new URLSearchParams(params)
    next.set('season', String(season))
    // A filter change rewrites the current entry; only navigation pushes.
    setParams(next, { replace: true })
  }

  const meta = data
    ? [
        data.structure_note,
        data.season_completed ? `${data.season} final` : `${data.season} in progress`,
        `Seasons ${data.window.first_season}–${data.window.last_season}`,
      ].join(' · ')
    : undefined

  return (
    <>
      <PageHeader
        title="Teams"
        meta={meta}
        subnav={
          data ? (
            <label className="flex items-center gap-2 text-[12px] text-ink-2">
              Season
              <select
                value={data.season}
                onChange={(event) => chooseSeason(Number(event.target.value))}
                className="motion-state rounded border border-line bg-raised px-2 py-1 text-[12px] text-ink hover:border-line-strong"
              >
                {seasonOptions(data.window.first_season, data.window.last_season).map((season) => (
                  <option key={season} value={season}>
                    {season}
                  </option>
                ))}
              </select>
            </label>
          ) : undefined
        }
      />

      <div className="mt-5">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? (
            <>
              {data.note ? <p className="mb-4 text-[11px] leading-4 text-ink-3">{data.note}</p> : null}
              {data.conferences.map((conference) => (
                <Section
                  key={conference.conference}
                  title={conference.conference}
                  note={`${plural(conference.divisions.length, 'division')} · ${plural(
                    conference.divisions.reduce((total, division) => total + division.teams.length, 0),
                    'club',
                  )}`}
                >
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-x-4 gap-y-5">
                    {conference.divisions.map((division) => (
                      <div key={division.label}>
                        <h3 className="mb-1.5 text-[11px] uppercase leading-4 tracking-[0.04em] text-ink-3">
                          {division.label}
                        </h3>
                        <ul className="space-y-1.5">
                          {division.teams.map((card) => (
                            <TeamCard key={card.abbr} card={card} season={data.season} />
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </Section>
              ))}
            </>
          ) : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function seasonOptions(first: number, last: number): number[] {
  const out: number[] = []
  for (let season = last; season >= first; season -= 1) out.push(season)
  return out
}

/**
 * Two destinations, one card: the card is the club's season, the name inside it
 * is the franchise. The season link is a stretched overlay rather than a wrapper
 * because an anchor cannot legally contain another anchor.
 */
function TeamCard({ card, season }: { card: Card; season: number }) {
  const name = card.name ?? card.abbr
  const games = card.record ? (card.record.w ?? 0) + (card.record.l ?? 0) + (card.record.t ?? 0) : 0
  const line = card.record
    ? games > 0
      ? [formatRecord(card.record.w ?? 0, card.record.l ?? 0, card.record.t ?? 0), winPct(card.record.pct), card.division_finish ? ordinal(card.division_finish) : null]
          .filter(Boolean)
          .join(' · ')
      : 'No games played yet'
    : 'No standings row for this season'

  return (
    <li className="motion-state relative flex items-stretch overflow-hidden rounded-md border border-line bg-raised hover:border-line-strong">
      {/* The one place team colour appears on this page. No colour in the source
          means no stripe, not a grey one. */}
      {card.colors.primary ? (
        <span aria-hidden className="w-[3px] shrink-0" style={{ background: card.colors.primary }} />
      ) : (
        <span aria-hidden className="w-[3px] shrink-0" />
      )}
      <Link to={card.href} aria-label={`${season} ${name} season`} className="absolute inset-0 z-0" />
      <div className="flex min-w-0 items-center gap-2 px-2.5 py-2">
        <Mark src={card.logo} label={card.abbr ?? name} size={28} />
        <div className="min-w-0">
          <Link to={card.franchise_href} className="relative z-10 block truncate text-[13px] font-medium">
            {name}
          </Link>
          <p className="truncate text-[11px] leading-4 text-ink-3">{line}</p>
          {card.playoff_result ? (
            <p className="truncate text-[11px] leading-4 text-ink-3">{card.playoff_result}</p>
          ) : null}
        </div>
      </div>
    </li>
  )
}
