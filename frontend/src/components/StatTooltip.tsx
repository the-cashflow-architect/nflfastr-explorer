import { Info } from 'lucide-react'
import type { ColumnMeta } from '../types'

interface StatTooltipProps {
  column: ColumnMeta
}

export function StatTooltip({ column }: StatTooltipProps) {
  return (
    <span className="group relative inline-flex items-center">
      <Info className="ml-1 h-3.5 w-3.5 text-slate-500 transition-colors group-hover:text-blue-400" />
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-xl border border-white/10 bg-slate-900/95 p-3 text-left text-xs font-normal normal-case tracking-normal text-slate-200 opacity-0 shadow-2xl backdrop-blur-md transition-opacity group-hover:opacity-100"
      >
        <span className="mb-1 block text-sm font-semibold text-white">{column.label}</span>
        <span className="block leading-relaxed text-slate-300">{column.description}</span>
        {column.formula ? (
          <span className="mt-2 block rounded-md bg-slate-800/80 px-2 py-1 font-mono text-[11px] text-emerald-300">
            {column.formula}
          </span>
        ) : null}
        <span className="mt-2 block text-[10px] uppercase tracking-wide text-slate-500">
          {column.dtype} · {column.category}
        </span>
      </span>
    </span>
  )
}
