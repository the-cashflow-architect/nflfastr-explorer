import { HelpCircle } from 'lucide-react'

/** A quiet explanation attached to a control, never the control's only label. */
export function HelpHint({ text }: { text: string }) {
  return (
    <span title={text} aria-label={text} className="inline-flex text-ink-3">
      <HelpCircle className="h-3.5 w-3.5" />
    </span>
  )
}
