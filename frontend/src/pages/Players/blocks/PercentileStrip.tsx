import { PercentileBar } from '../../../components/charts/PercentileBar'
import { ComputedByUs, Empty } from '../../../components/ui/Honesty'
import { QueryBoundary } from '../../../components/ui/QueryBoundary'
import { num, percent } from '../../../design/format'
import { usePlayerPercentiles } from '../../../api/endpoints'

/**
 * Where this player sits among his position's peers, for one season or for his
 * whole career.
 *
 * The cohort is the block. A percentile with no cohort behind it is a number
 * somebody made up, so the qualification rule and the n are printed under the
 * bars every time, and a player who does not clear the qualifier is told that
 * plainly instead of being drawn at the bottom of every track.
 */

export function PercentileStrip({ gsisId, scope }: { gsisId: string; scope: string }) {
  const query = usePlayerPercentiles(gsisId, { season: scope })
  const data = query.data

  return (
    <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
      {data ? <Bars data={data} /> : null}
    </QueryBoundary>
  )
}

function Bars({ data }: { data: NonNullable<ReturnType<typeof usePlayerPercentiles>['data']> }) {
  const metrics = data.metrics ?? []
  const cohortLabel = `qualified ${data.cohort.position_group ?? data.position_group ?? 'players'}`

  if (!metrics.length) {
    return <Empty>{data.note ?? `Nothing is ranked here: ${data.cohort.qualification}`}</Empty>
  }

  return (
    <div>
      {/* Below the volume bar he still has real values; they are shown with no
          percentile beside them rather than dropped. */}
      {data.note ? <p className="mb-2 text-[12px] leading-4 text-ink-2">{data.note}</p> : null}
      {metrics.map((metric) => (
        <PercentileBar
          key={metric.id}
          label={metric.label}
          value={metricValue(metric.value, metric.unit)}
          percentile={metric.percentile ?? null}
          cohortSize={metric.n}
          cohortLabel={cohortLabel}
          help={help(metric)}
        />
      ))}
      <p className="mt-2 text-[11px] leading-4 text-ink-3">
        {data.cohort.qualification}
        {data.cohort.computed_by_us ? (
          <ComputedByUs
            formula="Percentile of this player's value within the qualified cohort for his position group"
            anchor="percentiles"
          />
        ) : null}
      </p>
      {data.source_window?.note ? (
        <p className="text-[11px] leading-4 text-ink-3">
          {data.source_window.first_season ? `${data.source_window.first_season} onward · ` : null}
          {data.source_window.note}
        </p>
      ) : null}
      {coverageNotes(metrics).map((note) => (
        <p key={note} className="text-[11px] leading-4 text-ink-3">
          {note}
        </p>
      ))}
    </div>
  )
}

type Metric = NonNullable<NonNullable<ReturnType<typeof usePlayerPercentiles>['data']>['metrics']>[number]

function metricValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return '—'
  if (unit === 'percent') return percent(value, 1)
  if (unit === 'epa') return num(value, 3)
  return num(value, 1)
}

function help(metric: Metric): string {
  return [
    metric.label,
    metric.higher_is_better ? null : 'Lower values are better for this metric.',
    metric.note,
    metric.coverage_note,
    metric.median === null || metric.median === undefined
      ? null
      : `Cohort median ${metricValue(metric.median, metric.unit)}.`,
  ]
    .filter(Boolean)
    .join(' — ')
}

/** One line per metric whose window is narrower than the rest of the strip. */
function coverageNotes(metrics: Metric[]): string[] {
  const seen = new Set<string>()
  for (const metric of metrics) {
    if (metric.coverage_note) seen.add(`${metric.label}: ${metric.coverage_note}`)
  }
  return [...seen]
}
