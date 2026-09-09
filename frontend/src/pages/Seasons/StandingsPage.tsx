import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useSeasonIndex, useStandings } from '../../api/endpoints'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { StandingsTable } from './blocks/StandingsTable'

type View = 'division' | 'conference'

/**
 * The full standings: every column the spec asks for, seeding in conference
 * view, and the tiebreak basis as page text rather than something a visitor
 * has to hover to find.
 */
export function StandingsPage() {
  const { season: seasonParam = '' } = useParams()
  const seasonNumber = Number(seasonParam)
  const season = Number.isFinite(seasonNumber) && seasonNumber > 0 ? seasonNumber : undefined
  const seasonIndex = useSeasonIndex()

  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'conference' ? 'conference' : 'division'
  const setView = (next: View) => {
    const nextParams = new URLSearchParams(params)
    if (next === 'division') nextParams.delete('view')
    else nextParams.set('view', next)
    // A view toggle re-sorts the same page in place — it replaces the
    // current history entry rather than pushing a new one.
    setParams(nextParams, { replace: true })
  }

  const query = useStandings(season, { view })
  const data = query.data

  useCrumbLabel(season ? `/seasons/${season}/standings` : '', season ? `${season} standings` : undefined)

  const seasons = seasonIndex.data?.seasons.map((s) => s.season) ?? []
  const idx = season !== undefined ? seasons.indexOf(season) : -1
  const prevSeason = idx >= 0 && idx < seasons.length - 1 ? seasons[idx + 1] : undefined
  const nextSeason = idx > 0 ? seasons[idx - 1] : undefined

  return (
    <>
      <PageHeader
        title={`${season ?? seasonParam} Standings`}
        meta={
          season ? (
            <Link to={`/seasons/${season}`} className="no-underline hover:text-accent hover:underline">
              {season} season hub
            </Link>
          ) : undefined
        }
        prev={prevSeason ? { to: `/seasons/${prevSeason}/standings`, label: `${prevSeason} standings` } : undefined}
        next={nextSeason ? { to: `/seasons/${nextSeason}/standings`, label: `${nextSeason} standings` } : undefined}
        subnav={
          <Segmented
            ariaLabel="Division or conference view"
            value={view}
            onChange={setView}
            options={[
              { value: 'division', label: 'Division' },
              { value: 'conference', label: 'Conference' },
            ]}
          />
        }
      />

      <div className="mt-5">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? (
            <>
              {data.projected ? (
                <p className="mb-3 text-[12px] leading-4 text-ink-3">
                  This season is in progress. Seeds are projected from the standings rules below, not read off a
                  finished bracket, and are marked <span className="font-medium text-ink">proj.</span> below.
                </p>
              ) : null}

              <StandingsTable groups={data.groups} variant="full" formulas={data.formulas} />

              <div className="mt-5 space-y-2 border-t border-line pt-3 text-[11px] leading-4 text-ink-3">
                <p>
                  {data.note}
                  {data.formulas.playoff_seed ? <ComputedByUs formula={data.formulas.playoff_seed} anchor="playoff-seed" /> : null}
                </p>
                <TiebreakRules rules={data.tiebreak_rules_implemented} />
                <p>
                  SRS, SOS and Pythagorean wins are calculated by Gridiron, not sourced, and are hidden by default —
                  show them from the column picker on each table.
                  {data.formulas.srs ? <ComputedByUs formula={data.formulas.srs} anchor="srs" /> : null}
                </p>
              </div>
            </>
          ) : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function TiebreakRules({ rules }: { rules: Record<string, string[]> }) {
  const entries = Object.entries(rules).filter(([, steps]) => steps.length)
  if (!entries.length) return null
  return (
    <ul className="space-y-0.5">
      {entries.map(([kind, steps]) => (
        <li key={kind}>
          <span className="capitalize text-ink-2">{kind.replace(/_/g, ' ')} ties</span>: {steps.join(' → ')}
        </li>
      ))}
    </ul>
  )
}
