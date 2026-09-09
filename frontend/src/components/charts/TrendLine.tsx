import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { chartColors } from './primitives'

/**
 * One metric at a time, over seasons or weeks.
 *
 * A rate axis starts at the data minimum, because a completion percentage
 * plotted from zero is a flat line that says nothing; a counting axis starts at
 * zero, because there the distance from zero is the fact. Era boundaries are
 * drawn as labelled rules rather than left to be discovered — a passing chart
 * that goes flat before 2006 is a charting gap, not a career.
 */
export function TrendLine({
  data,
  xKey,
  yKey,
  yLabel,
  zeroBased = false,
  eraBoundaries = [],
  height = 180,
  formatValue,
}: {
  data: Record<string, number | string | null>[]
  xKey: string
  yKey: string
  yLabel: string
  zeroBased?: boolean
  eraBoundaries?: { at: number; label: string }[]
  height?: number
  formatValue?: (value: number) => string
}) {
  const colors = chartColors()
  const points = data.filter((d) => d[yKey] !== null && d[yKey] !== undefined)

  if (points.length < 2) {
    return <p className="py-4 text-[12px] text-ink-3">Not enough seasons with this stat to draw a trend.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -20 }}>
        <CartesianGrid stroke="none" />
        <XAxis
          dataKey={xKey}
          tick={{ fill: colors.ink3, fontSize: 10 }}
          axisLine={{ stroke: colors.line }}
          tickLine={false}
        />
        <YAxis
          domain={zeroBased ? [0, 'auto'] : ['auto', 'auto']}
          tick={{ fill: colors.ink3, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={46}
        />
        {eraBoundaries.map((era) => (
          <ReferenceLine
            key={era.at}
            x={era.at}
            stroke={colors.line}
            strokeWidth={1}
            label={{ value: era.label, position: 'insideTopLeft', fill: colors.ink3, fontSize: 9 }}
          />
        ))}
        <Line
          type="monotone"
          dataKey={yKey}
          name={yLabel}
          stroke={colors.ink}
          strokeWidth={1.5}
          dot={points.length < 15 ? { r: 2, fill: colors.ink } : false}
          isAnimationActive={false}
          connectNulls={false}
        />
        <Tooltip
          cursor={{ stroke: colors.line }}
          contentStyle={{
            background: colors.raised,
            border: `1px solid ${colors.line}`,
            borderRadius: 6,
            fontSize: 12,
            color: colors.ink,
          }}
          formatter={((value: unknown) => [
            formatValue ? formatValue(Number(value)) : String(value),
            yLabel,
          ]) as never}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
