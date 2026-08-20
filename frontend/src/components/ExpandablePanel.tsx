import { Maximize2, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface ExpandablePanelProps {
  title: string
  children: ReactNode
  className?: string
}

/**
 * Wraps a panel (table, chart, filters, ...) with a maximize button that
 * opens the same content full-viewport, so a user can focus on one thing
 * without navigating away or losing scroll position in the rest of the page.
 */
export function ExpandablePanel({ title, children, className }: ExpandablePanelProps) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!expanded) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  return (
    <div className={`group relative ${className ?? ''}`}>
      <button
        type="button"
        onClick={() => setExpanded(true)}
        aria-label={`Expand ${title}`}
        title="Expand"
        className="absolute right-2 top-2 z-10 rounded-lg border border-white/10 bg-slate-900/70 p-1.5 text-slate-400 opacity-0 backdrop-blur transition-all duration-150 hover:bg-slate-800 hover:text-white group-hover:opacity-100 focus-visible:opacity-100"
      >
        <Maximize2 className="h-3.5 w-3.5" />
      </button>
      {children}
      {expanded
        ? createPortal(
            <div className="fixed inset-0 z-[90] flex flex-col bg-slate-950/90 backdrop-blur-sm">
              <div className="flex items-center justify-between border-b border-white/10 bg-slate-900/80 px-5 py-3">
                <h3 className="text-sm font-semibold text-white">{title}</h3>
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  aria-label="Close"
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-white/5 hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-5">{children}</div>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}
