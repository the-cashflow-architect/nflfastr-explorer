import type { StatTab } from '../lib/statViews'
import { STAT_TAB_LABELS } from '../lib/statViews'
import { HelpHint } from './HelpHint'

const TAB_HINTS: Record<StatTab, string> = {
  basic: 'The core box-score numbers for this position — yards, touchdowns, the counting stats.',
  advanced: 'Efficiency metrics like EPA and CPOE that judge how much a play was worth, not just its raw total.',
  fantasy: 'Fantasy scoring. Kept separate so it never mixes into the real stats above.',
  custom: 'Pick any combination of fields yourself.',
}

interface StatTabsProps {
  active: StatTab
  onChange: (tab: StatTab) => void
  advancedDisabled?: boolean
  advancedDisabledReason?: string
}

export function StatTabs({ active, onChange, advancedDisabled, advancedDisabledReason }: StatTabsProps) {
  const order: StatTab[] = ['basic', 'advanced', 'fantasy', 'custom']

  return (
    <div className="flex items-center gap-1 rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white p-1">
      {order.map((tab, idx) => {
        const disabled = tab === 'advanced' && advancedDisabled
        const isLast = idx === order.length - 1
        return (
          <div key={tab} className="flex items-center">
            {tab === 'fantasy' ? <div className="mx-1 h-4 w-px bg-white/10" /> : null}
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(tab)}
              title={disabled ? advancedDisabledReason : TAB_HINTS[tab]}
              className={`rounded-md px-3 py-1.5 text-sm transition-all duration-150 ${
                disabled
                  ? 'cursor-not-allowed text-slate-600'
                  : active === tab
                    ? 'bg-blue-500/20 text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40'
                    : tab === 'fantasy'
                      ? 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                      : 'text-slate-300 light:text-slate-600 hover:text-white hover:bg-white/5'
              }`}
            >
              {STAT_TAB_LABELS[tab]}
            </button>
            {!isLast ? null : <HelpHint text={TAB_HINTS[active]} title={STAT_TAB_LABELS[active]} />}
          </div>
        )
      })}
    </div>
  )
}
