import { AlertTriangle } from 'lucide-react'

export function ErrorBanner({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Something went wrong loading this data.'
  return (
    <div className="flex items-start gap-2 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}
