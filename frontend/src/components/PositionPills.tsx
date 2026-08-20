import { POSITION_PILLS } from '../lib/statViews'
import { HelpHint } from './HelpHint'

interface PositionPillsProps {
  active: string
  onChange: (id: string) => void
}

export function PositionPills({ active, onChange }: PositionPillsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {POSITION_PILLS.map((pill) => (
        <button
          key={pill.id}
          type="button"
          onClick={() => onChange(pill.id)}
          title={pill.hint}
          className={`rounded-full px-3 py-1.5 text-sm font-medium transition-all duration-150 ${
            active === pill.id
              ? 'bg-blue-500/20 text-blue-100 ring-1 ring-blue-400/40 shadow-sm shadow-blue-500/10'
              : 'bg-slate-900/50 text-slate-300 ring-1 ring-white/5 hover:bg-slate-800/80 hover:ring-white/10'
          }`}
        >
          {pill.label}
        </button>
      ))}
      <HelpHint
        title="Position"
        text="Narrows the table to this position group and switches Basic/Advanced to the stats that matter for it — the same idea as Pro Football Reference's separate Passing, Rushing, and Defense pages."
      />
    </div>
  )
}
