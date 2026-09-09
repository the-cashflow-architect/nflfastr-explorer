import { Link } from 'react-router-dom'
import { useDraftIndex, type DraftIndex } from '../../api/endpoints'
import { PageHeader } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'

/**
 * Every draft class, newest first. The one page in the product that reaches
 * before 1999 — the coverage note says so plainly, because the rest of the
 * site's modern-era floor does not apply here and a visitor who has learned
 * that rule elsewhere needs to be told this page is the exception.
 */
export function DraftIndexPage() {
  const query = useDraftIndex()
  const data = query.data

  return (
    <>
      <PageHeader
        title="Draft"
        meta={data ? `${data.years.length} classes on file, ${data.first_season}–${data.years[0]?.year ?? ''}` : undefined}
      />

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <Index data={data} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function Index({ data }: { data: DraftIndex }) {
  return (
    <>
      <p className="mb-5 max-w-3xl text-[12px] leading-5 text-ink-3">{data.coverage_note}</p>

      <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        {data.years.map((year) => (
          <li key={year.year} className="motion-state rounded-md border border-line bg-raised px-3 py-2.5 hover:border-line-strong">
            <Link to={year.href} className="text-[14px] font-medium no-underline">
              {year.year}
            </Link>
            <p className="text-[11px] leading-4 text-ink-3">{year.picks} picks</p>
            {year.first_overall ? (
              <p className="mt-1 truncate text-[12px] leading-4">
                <span className="text-ink-3">1st: </span>
                <FirstOverallPlayer entry={year.first_overall} />
                {year.first_overall.team ? (
                  <span className="text-ink-3">
                    {' · '}
                    <FirstOverallTeam entry={year.first_overall} />
                  </span>
                ) : null}
              </p>
            ) : (
              <p className="mt-1 text-[12px] text-ink-3">No first-overall pick on file.</p>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

type FirstOverall = NonNullable<DraftIndex['years'][number]['first_overall']>

/** Server hrefs win over anything this page could build itself. */
function FirstOverallPlayer({ entry }: { entry: FirstOverall }) {
  if (!entry.player) return <span className="text-ink-3">—</span>
  if (!entry.gsis_id || !entry.player_href) return <span>{entry.player}</span>
  return <Link to={entry.player_href}>{entry.player}</Link>
}

function FirstOverallTeam({ entry }: { entry: FirstOverall }) {
  if (!entry.team) return null
  if (!entry.team_href) return <span>{entry.team}</span>
  return <Link to={entry.team_href}>{entry.team}</Link>
}
