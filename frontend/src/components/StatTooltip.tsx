import { Info } from 'lucide-react'
import type { ColumnMeta } from '../types'
import { Tooltip } from './Tooltip'

interface StatTooltipProps {
  column: ColumnMeta
}

export function StatTooltip({ column }: StatTooltipProps) {
  return (
    <Tooltip
      trigger={
        <Info className="h-3.5 w-3.5 text-slate-500 transition-colors hover:text-blue-400" />
      }
    >
      <span className="mb-1 block text-sm font-semibold text-white light:text-slate-900">{column.label}</span>
      <span className="block leading-relaxed text-slate-300 light:text-slate-600">{column.description}</span>
      {column.formula ? (
        <span className="mt-2 block rounded-md bg-slate-800/80 light:bg-slate-100 px-2 py-1 font-mono text-[11px] text-emerald-300">
          {column.formula}
        </span>
      ) : null}
      <span className="mt-2 block text-[10px] uppercase tracking-wide text-slate-500">
        {column.dtype} · {column.category}
      </span>
    </Tooltip>
  )
}
