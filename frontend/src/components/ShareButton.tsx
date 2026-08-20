import { Share2, Copy, Check, X } from 'lucide-react'
import { useState } from 'react'
import type { UrlState } from '../hooks/useUrlState'

interface ShareButtonProps {
  getShareableUrl: (state: UrlState) => string
  currentState: UrlState
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
            <div className="mb-4 flex items-center justify-between">
              <h4 className="font-semibold text-white">Share Link</h4>
              <button
                onClick={() => setShowDialog(false)}
                className="rounded p-1 text-slate-500 transition hover:bg-white/5 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="relative mb-4">
              <input
                type="text"
                readOnly
                value={getShareableUrl(currentState)}
                className="w-full rounded-lg border border-white/10 bg-slate-800/70 px-3 py-2 pr-20 text-sm text-slate-100 outline-none"
              />
              <button
                onClick={handleCopy}
                className={`absolute right-2 top-1/2 inline-flex -translate-y-1/2 items-center gap-1 rounded-lg px-2 py-1 text-xs transition ${
                  copied ? 'bg-emerald-500 text-white' : 'bg-blue-500/20 text-blue-200'
                }`}
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
              Includes your position, stat view, filters, sorting, and columns.
            </p>
          </div>
        </div>
      )}
    </>
  )
}
