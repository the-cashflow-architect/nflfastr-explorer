import { Share2, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import type { FilterCondition, SortSpec } from '../types'

interface ShareButtonProps {
  getShareableUrl: (state: {
    datasetId: string
    filters: FilterCondition[]
    sort: SortSpec[]
    columns: string[]
    page: number
    viewMode: 'explore' | 'compare' | 'team'
    exploreView: 'table' | 'chart'
  }) => string
  currentState: {
    datasetId: string
    filters: FilterCondition[]
    sort: SortSpec[]
    columns: string[]
    page: number
    viewMode: 'explore' | 'compare' | 'team'
    exploreView: 'table' | 'chart'
  }
}

export function ShareButton({ getShareableUrl, currentState }: ShareButtonProps) {
  const [copied, setCopied] = useState(false)
  const [showDialog, setShowDialog] = useState(false)

  const handleCopy = async () => {
    const url = getShareableUrl(currentState)
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setShowDialog(true)}
        className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 transition-all duration-200 hover:bg-slate-800/80 hover:shadow-lg"
      >
        <Share2 className="h-4 w-4" />
        Share
      </button>

      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-white">Share Link</h4>
              <button
                onClick={() => setShowDialog(false)}
                className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white transition"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="relative mb-4">
              <input
                type="text"
                readOnly
                value={getShareableUrl(currentState)}
                className="w-full rounded-lg border border-white/10 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 outline-none pr-10"
              />
              <button
                onClick={handleCopy}
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs transition"
                style={{
                  backgroundColor: copied ? '#22c55e' : 'rgba(59, 130, 246, 0.2)',
                  color: copied ? 'white' : '#93c5fd',
                }}
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    Copy
                  </>
                )}
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Link includes dataset, filters, sorting, columns, and view mode.
            </p>
          </div>
        </div>
      )}
    </>
  )
}