import { num } from '../../design/format'

/**
 * A neutral track, a fill, a median tick, the number outside the bar, and the
 * cohort size in the caption.
 *
 * No colour ramp: the whole point of a percentile is that the position on the
 * track already says how good it is, and a red-to-green gradient would add a
 * second, louder encoding of the same fact — plus a colour-blind failure mode
 * for free.
 *
 * The cohort size is not optional. A 90th percentile among twelve qualified
 * quarterbacks and among two hundred receivers are different claims, and a bar
 * that hides which one it is, misleads.
 */
export function PercentileBar({
  label,
  value,
  percentile,
  cohortSize,
  cohortLabel,
  help,
}: {
  label: string
  /** The raw stat, already formatted for display. */
  value: string
  /** 0–100. */
  percentile: number | null
  cohortSize: number | null
  cohortLabel?: string
  help?: string
}) {
  const known = percentile !== null && percentile !== undefined && !Number.isNaN(percentile)
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 py-1">
      <span className="truncate text-[12px] text-ink-2" title={help}>
        {label}
      </span>
      <div className="relative h-2 rounded-full bg-track">
        {known ? (
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-ink-2"
            style={{ width: `${Math.max(1, Math.min(100, percentile))}%` }}
          />
        ) : null}
        {/* The median tick is what turns a bar into a comparison. */}
        <div className="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong" aria-hidden />
      </div>
      <span className="whitespace-nowrap text-right text-[12px] tabular-nums">
        {value}
        {known ? <span className="ml-2 text-[11px] text-ink-3">{num(percentile, 0)}th</span> : null}
      </span>
      {cohortSize ? (
        <p className="col-span-3 -mt-0.5 text-[10px] text-ink-3">
          among {cohortSize.toLocaleString()} {cohortLabel ?? 'qualified players'}
        </p>
      ) : null}
    </div>
  )
}
