import { BarChart3, TrendingUp, Target, Shield } from 'lucide-react'
import { useMemo } from 'react'

interface QuickStatsProps {
  rows: Record<string, unknown>[]
  columns: string[]
}

interface StatConfig {
  id: string
  label: string
  icon: React.ReactNode
  format?: (val: number) => string
  color?: 'blue' | 'emerald' | 'amber' | 'red'
  isSum?: boolean
}

const STAT_CONFIGS: StatConfig[] = [
  { id: 'epa', label: 'Total EPA', icon: <TrendingUp className="h-4 w-4" />, isSum: true },
  { id: 'passing_yards', label: 'Passing Yards', icon: <BarChart3 className="h-4 w-4" />, isSum: true },
  { id: 'rushing_yards', label: 'Rushing Yards', icon: <BarChart3 className="h-4 w-4" />, isSum: true },
  { id: 'receiving_yards', label: 'Receiving Yards', icon: <BarChart3 className="h-4 w-4" />, isSum: true },
  { id: 'fantasy_points_ppr', label: 'Fantasy PPR', icon: <Target className="h-4 w-4" />, isSum: true },
  { id: 'cpoe', label: 'Avg CPOE', icon: <Shield className="h-4 w-4" />, isSum: false },
  { id: 'wpa', label: 'Total WPA', icon: <TrendingUp className="h-4 w-4" />, isSum: true },
]

const COLORS = {
  blue: 'text-blue-400',
  emerald: 'text-emerald-400',
  amber: 'text-amber-400',
  red: 'text-red-400',
}

function formatNumber(val: number): string {
  if (Number.isInteger(val)) return val.toLocaleString()
  return val.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export function QuickStats({ rows, columns }: QuickStatsProps) {
  const availableStats = useMemo(() => {
    return STAT_CONFIGS.filter((stat) => columns.includes(stat.id))
  }, [columns])

  if (availableStats.length === 0 || rows.length === 0) return null

  const computedStats = useMemo(() => {
    return availableStats.map((stat) => {
      const values = rows
        .map((row) => row[stat.id])
        .filter((v): v is number => typeof v === 'number' && !isNaN(v))

      if (values.length === 0) {
        return { ...stat, value: null as number | null }
      }

      const value = stat.isSum
        ? values.reduce((a, b) => a + b, 0)
        : values.reduce((a, b) => a + b, 0) / values.length

      return { ...stat, value }
    })
  }, [availableStats, rows])

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7">
      {computedStats.map((stat) => (
        <div
          key={stat.id}
          className="rounded-xl border border-white/10 bg-slate-900/40 p-3 text-center transition hover:bg-slate-900/60"
        >
          <div className={`mb-1 inline-flex items-center justify-center ${COLORS[stat.color ?? 'blue']}`}>
            {stat.icon}
          </div>
          <p className="text-2xl font-bold text-white">
            {stat.value != null ? formatNumber(stat.value) : '—'}
          </p>
          <p className="text-[11px] text-slate-500">{stat.label}</p>
        </div>
      ))}
    </div>
  )
}