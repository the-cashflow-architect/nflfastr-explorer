import type { FilterCondition } from '../types'
import type { ReactNode } from 'react'

interface Preset {
  id: string
  name: string
  icon: ReactNode
  description: string
  filters: FilterCondition[]
  datasets: string[]
}

interface PresetSelectorProps {
  datasetId: string
  onSelect: (filters: FilterCondition[]) => void
  presets: Preset[]
}

export function PresetSelector({ datasetId, onSelect, presets }: PresetSelectorProps) {
  const datasetPresets = presets.filter((p) => p.datasets.includes(datasetId))

  if (datasetPresets.length === 0) return null

  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/50 p-3 mb-4">
      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
        Quick Presets
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {datasetPresets.slice(0, 6).map((preset) => (
           <button
            key={preset.id}
            onClick={() => onSelect(preset.filters)}
            className="flex flex-col items-center gap-1.5 rounded-lg border border-white/10 bg-slate-950/40 p-2.5 text-center transition-all duration-200 hover:scale-105 hover:bg-white/5 hover:border-blue-400/30"
          >
            <span className="text-blue-400">{preset.icon}</span>
            <span className="text-sm font-medium text-slate-200">{preset.name}</span>
            <span className="text-[10px] text-slate-500 line-clamp-1">
              {preset.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}