import { useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { ApiError, NotSavedOfflineError } from '../../api/client'

/**
 * How long a wait can run before silence becomes dishonest.
 *
 * The API sleeps between visits and takes the better part of a minute to wake —
 * measured at 43 seconds from cold, against 0.7 warm. An unexplained "Loading…"
 * for that long does not read as a slow server; it reads as a broken product,
 * and the visitor closes it. The page cannot tell a waking server from a slow
 * answer, so the note says what may be happening rather than claiming it is.
 */
const WAKING_AFTER_MS = 4000

/**
 * How every page in the product handles waiting and failing.
 *
 * It exists to make one distinction impossible to blur: **an error is not an
 * empty state.** A page that renders "no results" when the server is unreachable
 * teaches a visitor to distrust every number on the site, because they cannot
 * tell a genuine zero from a broken connection. So a failure says what happened,
 * in a sentence, and offers the retry.
 *
 * The loading state is deliberately quiet — a line of text, not a skeleton
 * mimicking content that may not exist. A shimmering fake table implies data is
 * coming even when the honest answer is that this player has none.
 */
export function QueryBoundary({
  isLoading,
  error,
  isEmpty,
  emptyMessage,
  onRetry,
  children,
}: {
  isLoading: boolean
  error: unknown
  /** True when the request succeeded and genuinely returned nothing. */
  isEmpty?: boolean
  emptyMessage?: React.ReactNode
  onRetry?: () => void
  children: React.ReactNode
}) {
  if (error) {
    const api = error instanceof ApiError ? error : null
    // No connection and nothing saved says exactly that: nothing was fetched,
    // so "could not reach the server" would describe a request never made.
    const message = error instanceof NotSavedOfflineError
      ? error.message
      : api?.isNotFound
        ? 'We have no record of that.'
        : api?.isSeasonLoading
          ? (api.message ?? 'That season is still loading. Try again in a few seconds.')
          : api?.status === 0
            ? 'Could not reach the server. This is not “no results” — the data is there, we just could not fetch it.'
            : (api?.message ?? 'Something went wrong loading this.')
    return (
      <div className="flex items-start gap-2 rounded-md border border-line bg-raised px-3 py-3 text-[13px]">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-negative" />
        <div>
          <p>{message}</p>
          {onRetry ? (
            <button type="button" onClick={onRetry} className="motion-state mt-1 text-[12px] underline hover:text-accent">
              Try again
            </button>
          ) : null}
        </div>
      </div>
    )
  }

  if (isLoading) {
    return <Waiting />
  }

  if (isEmpty) {
    return <p className="px-1 py-6 text-[13px] text-ink-3">{emptyMessage ?? 'Nothing to show here.'}</p>
  }

  return <>{children}</>
}

/**
 * The loading line, which grows an explanation if the wait gets long.
 *
 * Deliberately not a progress bar or a spinner: there is nothing to measure and
 * nothing the visitor can do. It is one sentence that turns an apparent hang
 * into a known, finite wait.
 */
function Waiting() {
  const [waking, setWaking] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setWaking(true), WAKING_AFTER_MS)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="px-1 py-6 text-[13px] text-ink-3">
      <p>Loading…</p>
      {waking ? (
        <p className="mt-1 max-w-prose">Still loading. If the server was asleep, this can take up to a minute.</p>
      ) : null}
    </div>
  )
}
