import { ChevronRight, Home } from 'lucide-react'
import type { ReactNode } from 'react'

export interface Crumb {
  label: string
  onClick?: () => void
}

export function Breadcrumb({ trail }: { trail: Crumb[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-sm text-slate-400" aria-label="Breadcrumb">
      {trail.map((crumb, idx): ReactNode => {
        const isLast = idx === trail.length - 1
        return (
          <span key={idx} className="flex items-center gap-1.5">
            {idx === 0 ? <Home className="h-3.5 w-3.5" /> : null}
            {crumb.onClick && !isLast ? (
              <button
                type="button"
                onClick={crumb.onClick}
                className="transition-colors hover:text-white hover:underline underline-offset-2"
              >
                {crumb.label}
              </button>
            ) : (
              <span className={isLast ? 'font-medium text-white' : ''}>{crumb.label}</span>
            )}
            {!isLast ? <ChevronRight className="h-3.5 w-3.5 text-slate-600" /> : null}
          </span>
        )
      })}
    </nav>
  )
}
