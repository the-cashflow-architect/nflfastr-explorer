import { chartColors, downsample } from './primitives'

/**
 * 40x14, one line, one dot at the end. No axes, no grid, no tooltip.
 *
 * Drawn by hand rather than by Recharts because at this size a charting library
 * costs more in wrapper markup than the whole graphic, and a schedule table
 * renders seventeen of them.
 */
export function Sparkline({
  values,
  width = 40,
  height = 14,
  title,
}: {
  values: (number | null)[]
  width?: number
  height?: number
  title?: string
}) {
  const points = downsample(values.filter((v): v is number => v !== null), 40)
  if (points.length < 2) return <span className="text-ink-3">—</span>

  const colors = chartColors()
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const x = (i: number) => (i / (points.length - 1)) * (width - 2) + 1
  const y = (v: number) => height - 1 - ((v - min) / span) * (height - 2)
  const path = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const lastX = x(points.length - 1)
  const lastY = y(points[points.length - 1])

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title ?? 'Trend'}>
      {title ? <title>{title}</title> : null}
      <path d={path} fill="none" stroke={colors.ink2} strokeWidth={1} />
      <circle cx={lastX} cy={lastY} r={1.5} fill={colors.ink} />
    </svg>
  )
}
