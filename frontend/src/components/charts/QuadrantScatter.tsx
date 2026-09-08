import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { chartColors } from './primitives'

/**
 * Thirty-two teams on offence-versus-defence axes, with league-average
 * crosshairs and the quadrants named.
 *
 * Team logos are the marks: they are the one place a team's own colours belong,
 * because here the colour *is* the label and there is no risk of it being read
 * as a value. Defensive EPA is inverted so that up-and-right is good in both
 * dimensions — otherwise every reader has to remember which axis is backwards.
 */

export interface QuadrantPoint {
  team: string
  logo: string
  offense: number
  defense: number
}

export function QuadrantScatter({
  points,
  height = 380,
  onSelect,
}: {
  points: QuadrantPoint[]
  height?: number
  onSelect?: (team: string) => void
}) {
  const colors = chartColors()
  if (!points.length) {
    return <p className="py-6 text-[13px] text-ink-3">No team ratings for this season yet.</p>
  }

  const avgOffense = points.reduce((sum, p) => sum + p.offense, 0) / points.length
  const avgDefense = points.reduce((sum, p) => sum + p.defense, 0) / points.length
  const data = points.map((p) => ({ ...p, y: -p.defense }))

  return (
    <figure className="m-0">
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 16, right: 16, bottom: 8, left: -12 }}>
          <CartesianGrid stroke="none" />
          <XAxis
            type="number"
            dataKey="offense"
            name="Offence EPA/play"
            tick={{ fill: colors.ink3, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            label={{ value: 'Offence EPA / play →', position: 'insideBottom', offset: -4, fill: colors.ink3, fontSize: 10 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Defence EPA/play allowed"
            tick={{ fill: colors.ink3, fontSize: 10 }}
            tickFormatter={(v: number) => (-v).toFixed(2)}
            axisLine={false}
            tickLine={false}
            width={48}
            label={{ value: 'Better defence ↑', angle: -90, position: 'insideLeft', fill: colors.ink3, fontSize: 10 }}
          />
          <ZAxis range={[400, 400]} />
          <ReferenceLine x={avgOffense} stroke={colors.line} />
          <ReferenceLine y={-avgDefense} stroke={colors.line} />
          <Scatter
            data={data}
            isAnimationActive={false}
            onClick={(point) => onSelect?.((point as unknown as QuadrantPoint).team)}
            shape={(props: unknown) => {
              const { cx, cy, payload } = props as { cx: number; cy: number; payload: QuadrantPoint }
              return (
                <image
                  href={payload.logo}
                  x={cx - 11}
                  y={cy - 11}
                  width={22}
                  height={22}
                  style={{ cursor: onSelect ? 'pointer' : 'default' }}
                />
              )
            }}
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
            formatter={((value: unknown, name: unknown) => [
              String(name).includes('Defence') ? (-Number(value)).toFixed(3) : Number(value).toFixed(3),
              String(name),
            ]) as never}
            labelFormatter={() => ''}
          />
        </ScatterChart>
      </ResponsiveContainer>
      <figcaption className="mt-1 text-[11px] text-ink-3">
        Up and to the right is good on both axes. Crosshairs are the league average.
      </figcaption>
    </figure>
  )
}
