import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { chartColors } from './primitives'

/**
 * The hero of a game page: home win probability from kickoff to final whistle.
 *
 * Two decisions carry it. The 50% line is drawn solid, because every reading of
 * this chart is "who was ahead, and by how much" and that question is answered
 * relative to the midline. And the single biggest swing gets the page's one
 * accent mark — the moment the game turned is the thing a reader came for, and
 * pointing at it is worth more than colouring everything.
 */

export interface WpPoint {
  play_id: number
  /** Seconds remaining in the game; the x-axis runs down from 3600. */
  seconds_remaining: number
  /** 0–1. */
  home_wp: number
  home_score: number
  away_score: number
  desc?: string | null
}

export function WinProbabilityChart({
  points,
  homeTeam,
  awayTeam,
  height = 220,
  onSelectPlay,
}: {
  points: WpPoint[]
  homeTeam: string
  awayTeam: string
  height?: number
  onSelectPlay?: (playId: number) => void
}) {
  const colors = chartColors()

  const data = useMemo(
    () => points.map((p) => ({ ...p, elapsed: 3600 - p.seconds_remaining, wp: p.home_wp * 100 })),
    [points],
  )

  const biggestSwing = useMemo(() => {
    let best: { index: number; delta: number } | null = null
    for (let i = 1; i < data.length; i += 1) {
      const delta = Math.abs(data[i].wp - data[i - 1].wp)
      if (!best || delta > best.delta) best = { index: i, delta }
    }
    return best && best.delta > 5 ? data[best.index] : null
  }, [data])

  if (data.length < 2) {
    return (
      <p className="py-6 text-[13px] text-ink-3">
        Win probability needs play-level data, which we hold from 1999 onward.
      </p>
    )
  }

  return (
    <figure className="m-0">
      <div className="flex items-baseline justify-between text-[11px] text-ink-3">
        <span>{homeTeam} win probability</span>
        {biggestSwing ? <span>Biggest swing marked</span> : null}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 8, bottom: 4, left: 4 }}
          onClick={(state: unknown) => {
            const payload = (state as { activePayload?: { payload?: { play_id?: number } }[] })
              ?.activePayload?.[0]?.payload
            if (payload?.play_id && onSelectPlay) onSelectPlay(payload.play_id)
          }}
        >
          <CartesianGrid stroke="none" />
          <XAxis
            dataKey="elapsed"
            type="number"
            domain={[0, 3600]}
            ticks={[0, 900, 1800, 2700, 3600]}
            tickFormatter={(v: number) => (v === 0 ? 'Kick' : v === 3600 ? 'Final' : `Q${v / 900 + 1}`)}
            tick={{ fill: colors.ink3, fontSize: 10 }}
            axisLine={{ stroke: colors.line }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 50, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: colors.ink3, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            // Wide enough for "100%" at 10px. A negative left margin used to pull
            // the axis under the plot and clip every label to its last glyph.
            width={40}
          />
          <ReferenceLine y={50} stroke={colors.line} strokeWidth={1} />
          <Area
            type="stepAfter"
            dataKey="wp"
            stroke={colors.ink}
            strokeWidth={1.5}
            fill={colors.ink}
            fillOpacity={0.12}
            isAnimationActive={false}
            dot={false}
          />
          {biggestSwing ? (
            <ReferenceDot
              x={biggestSwing.elapsed}
              y={biggestSwing.wp}
              r={3.5}
              fill={colors.accent}
              stroke="none"
            />
          ) : null}
          <Tooltip
            cursor={{ stroke: colors.line }}
            contentStyle={{
              background: colors.raised,
              border: `1px solid ${colors.line}`,
              borderRadius: 6,
              fontSize: 12,
              color: colors.ink,
            }}
            labelFormatter={(label) => `Q${Math.min(4, Math.floor(Number(label) / 900) + 1)}`}
            formatter={((value: unknown, _name: unknown, item: unknown) => {
              const p = (item as { payload?: WpPoint } | undefined)?.payload
              return [
                `${Number(value).toFixed(0)}% ${homeTeam} · ${p?.away_score ?? 0}-${p?.home_score ?? 0}`,
                p?.desc ?? '',
              ]
            }) as never}
          />
        </AreaChart>
      </ResponsiveContainer>
      <figcaption className="mt-1 text-[11px] text-ink-3">
        Above the line favours {homeTeam}; below favours {awayTeam}.
      </figcaption>
    </figure>
  )
}
