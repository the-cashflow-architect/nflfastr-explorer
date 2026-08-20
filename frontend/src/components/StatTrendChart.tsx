import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, LineChart, Area, AreaChart } from 'recharts'
import { useMemo } from 'react'
import type { ColumnMeta } from '../types'

interface StatTrendChartProps {
  data: Record<string, unknown>[]
  xField: string
  yField: string
  columnMeta: ColumnMeta
  playerName?: string
}

export function StatTrendChart({ data, xField, yField, columnMeta, playerName }: StatTrendChartProps) {
  const chartData = useMemo(() => {
    return data
      .map((row) => ({
        x: row[xField],
        y: row[yField],
        ...row,
      }))
      .filter((d) => d.x != null && d.y != null)
      .sort((a, b) => Number(a.x) - Number(b.x))
  }, [data, xField, yField])

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        No data available for trend chart
      </div>
    )
  }

  const isNumericX = chartData.every((d) => typeof d.x === 'number')
  const xDomain = isNumericX ? ['auto', 'auto'] : chartData.map((d) => String(d.x))

  return (
    <div className="rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white p-4 transition-all duration-200">
      <div className="mb-3">
        <h4 className="font-semibold text-white light:text-slate-900 flex items-center gap-2">
          {columnMeta.label} Trend
          {playerName && <span className="text-slate-400 light:text-slate-500 text-sm">— {playerName}</span>}
        </h4>
        <p className="text-xs text-slate-500">{columnMeta.description}</p>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="x"
              type={isNumericX ? 'number' : 'category'}
              domain={xDomain}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              label={{ value: columnMeta.id.includes('week') ? 'Week' : 'Season', position: 'bottom', offset: 20, fill: '#94a3b8', fontSize: 11 }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              label={{ value: columnMeta.label, angle: -90, position: 'insideLeft', offset: 10, fill: '#94a3b8', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
              itemStyle={{ color: '#60a5fa' }}
              formatter={(value) => [typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? ''), columnMeta.label]}
              labelFormatter={(label) => String(label)}
            />
            <Area
              type="monotone"
              dataKey="y"
              stroke="#3b82f6"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorArea)"
              dot={{ fill: '#3b82f6', strokeWidth: 2, r: 4, stroke: '#0f172a' }}
              activeDot={{ r: 6, fill: '#60a5fa' }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

interface MultiStatTrendProps {
  data: Record<string, unknown>[]
  xField: string
  yFields: string[]
  columnsMeta: ColumnMeta[]
  playerName?: string
}

export function MultiStatTrend({ data, xField, yFields, columnsMeta, playerName }: MultiStatTrendProps) {
  const chartData = useMemo(() => {
    return data
      .map((row) => ({
        x: row[xField],
        ...Object.fromEntries(yFields.map((f) => [f, row[f]])),
      }))
      .filter((d) => d.x != null && yFields.some((f) => (d as Record<string, unknown>)[f] != null))
      .sort((a, b) => Number(a.x) - Number(b.x))
  }, [data, xField, yFields])

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        No data available for trend chart
      </div>
    )
  }

  const isNumericX = chartData.every((d) => typeof d.x === 'number')
  const xDomain = isNumericX ? ['auto', 'auto'] : chartData.map((d) => String(d.x))
  const colors = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#ec4899']

  return (
    <div className="rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white p-4 transition-all duration-200">
      <div className="mb-3">
        <h4 className="font-semibold text-white light:text-slate-900 flex items-center gap-2">
          Stat Trends
          {playerName && <span className="text-slate-400 light:text-slate-500 text-sm">— {playerName}</span>}
        </h4>
        <div className="flex flex-wrap gap-3 mt-2">
          {yFields.map((field, idx) => {
            const meta = columnsMeta.find((c) => c.id === field)
            return (
              <span key={field} className="inline-flex items-center gap-1.5 text-xs">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: colors[idx % colors.length] }} />
                {meta?.label ?? field}
              </span>
            )
          })}
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="x"
              type={isNumericX ? 'number' : 'category'}
              domain={xDomain}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
              label={{ value: xField.includes('week') ? 'Week' : 'Season', position: 'bottom', offset: 20, fill: '#94a3b8', fontSize: 11 }}
            />
            <YAxis
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={{ stroke: '#334155' }}
              tickLine={{ stroke: '#334155' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
              labelFormatter={(label) => String(label)}
            />
            {yFields.map((field, idx) => (
                <Line
                  key={field}
                  type="monotone"
                  dataKey={field}
                  stroke={colors[idx % colors.length]}
                  strokeWidth={2}
                  dot={{ fill: colors[idx % colors.length], strokeWidth: 2, r: 4, stroke: '#0f172a' }}
                  activeDot={{ r: 6 }}
                />
              ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}