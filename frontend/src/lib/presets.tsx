import { Save, Target, Shield, Zap, Clock, BarChart3 } from 'lucide-react'
import type { FilterCondition } from '../types'

interface Preset {
  id: string
  name: string
  icon: React.ReactNode
  description: string
  filters: FilterCondition[]
  datasets: string[]
}

export const FILTER_PRESETS: Preset[] = [
  {
    id: 'red-zone',
    name: 'Red Zone',
    icon: <Target className="h-4 w-4" />,
    description: 'Plays inside the opponent 20-yard line',
    datasets: ['play_by_play'],
    filters: [
      { field: 'yardline_100', operator: 'lte', value: 20 },
    ],
  },
  {
    id: 'goal-line',
    name: 'Goal Line',
    icon: <Target className="h-4 w-4" />,
    description: 'Plays inside the opponent 6-yard line',
    datasets: ['play_by_play'],
    filters: [
      { field: 'yardline_100', operator: 'lte', value: 6 },
    ],
  },
  {
    id: 'third-down',
    name: '3rd Down',
    icon: <BarChart3 className="h-4 w-4" />,
    description: 'All third down plays',
    datasets: ['play_by_play'],
    filters: [
      { field: 'down', operator: 'eq', value: 3 },
    ],
  },
  {
    id: 'fourth-down',
    name: '4th Down',
    icon: <Shield className="h-4 w-4" />,
    description: 'All fourth down plays',
    datasets: ['play_by_play'],
    filters: [
      { field: 'down', operator: 'eq', value: 4 },
    ],
  },
  {
    id: 'close-games',
    name: 'Close Games',
    icon: <Clock className="h-4 w-4" />,
    description: 'Games decided by 1-10 points in the 4th quarter',
    datasets: ['play_by_play'],
    filters: [
      { field: 'qtr', operator: 'gte', value: 4 },
      { field: 'score_differential', operator: 'between', value: [-10, 10] },
    ],
  },
  {
    id: 'pass-heavy',
    name: 'Pass Heavy',
    icon: <Zap className="h-4 w-4" />,
    description: 'Passing plays only',
    datasets: ['play_by_play'],
    filters: [
      { field: 'pass', operator: 'in', value: [1] },
    ],
  },
  {
    id: 'rush-heavy',
    name: 'Run Heavy',
    icon: <Zap className="h-4 w-4" />,
    description: 'Rushing plays only',
    datasets: ['play_by_play'],
    filters: [
      { field: 'rush', operator: 'in', value: [1] },
    ],
  },
  {
    id: 'explosive-plays',
    name: 'Explosive Plays',
    icon: <Zap className="h-4 w-4" />,
    description: 'Pass plays with 20+ yards, runs with 10+ yards',
    datasets: ['play_by_play'],
    filters: [
      { field: 'play_type', operator: 'in', value: ['pass'] },
      { field: 'yards_gained', operator: 'gte', value: 20 },
    ],
  },
  {
    id: 'high-leverage',
    name: 'High Leverage',
    icon: <Clock className="h-4 w-4" />,
    description: 'Late-game situations with high win probability impact',
    datasets: ['play_by_play'],
    filters: [
      { field: 'qtr', operator: 'gte', value: 4 },
      { field: 'wpa', operator: 'gte', value: 0.1 },
    ],
  },
  {
    id: 'big-time',
    name: 'Big-Time Plays',
    icon: <Save className="h-4 w-4" />,
    description: 'Plays with 20+ EPA or 10+ WPA',
    datasets: ['play_by_play'],
    filters: [
      { field: 'epa', operator: 'gte', value: 20 },
    ],
  },
]

export function getPresetsForDataset(datasetId: string): Preset[] {
  return FILTER_PRESETS.filter((p) => p.datasets.includes(datasetId))
}

export function getPresetFilters(preset: Preset): FilterCondition[] {
  return preset.filters
}