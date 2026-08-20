import { Filter, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

/**
 * The filter sidebar is `hidden` below the `lg` breakpoint, so on a phone or
 * a narrow window there was previously no way to reach filters at all. This
 * gives small screens a button that opens the same filters full-screen.
 */
export function MobileFilterButton({ onClick, activeCount }: { onClick: () => void; activeCount: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/80 lg:hidden"
    >
      <Filter className="h-4 w-4" />
      Filters{activeCount > 0 ? ` (${activeCount})` : ''}
    </button>
  )
}

export function MobileFilterDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[95] flex flex-col bg-slate-950/95 backdrop-blur-sm lg:hidden">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <h3 className="text-sm font-semibold text-white">Filters</h3>
        <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-white/5 hover:text-white">
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4">{children}</div>
    </div>,
    document.body,
  )
}
