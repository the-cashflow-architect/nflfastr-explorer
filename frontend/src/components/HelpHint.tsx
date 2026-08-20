import { Info } from 'lucide-react'
import { Tooltip } from './Tooltip'

/** Plain-text version of StatTooltip, for anything that isn't a stat column. */
export function HelpHint({ text, title }: { text: string; title?: string }) {
  return (
    <Tooltip
      trigger={
        <Info className="h-3.5 w-3.5 text-slate-500 transition-colors hover:text-blue-400" />
      }
    >
      {title ? <span className="mb-1 block text-sm font-semibold text-white">{title}</span> : null}
      <span className="block leading-relaxed text-slate-300">{text}</span>
    </Tooltip>
  )
}
