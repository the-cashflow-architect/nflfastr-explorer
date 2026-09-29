import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { onlineManager, useQueryClient } from '@tanstack/react-query'
import { Network } from '@capacitor/network'
import { RefreshCw, WifiOff } from 'lucide-react'
import { SESSION_STARTED_AT } from '../../lib/offline'

/**
 * Past this age a figure being refreshed is labelled, even if it arrived in
 * this session: an app left in the background for three days, or a tab left
 * open, holds figures that old, and the refresh can take a minute while the
 * server wakes. The same hour as the reference pages' staleTime, so a figure
 * young enough not to be refetched is never flagged.
 */
const AGED_AFTER = 60 * 60 * 1000

/**
 * How old are the figures on screen, when they are not from just now?
 *
 * Saved answers let a page show something at once instead of waiting 43
 * seconds for a sleeping server, or show anything at all with no signal. That
 * is only defensible if an old figure never sits on screen passing for a
 * current one — a reference site that is confidently wrong once is finished,
 * and "the number was simply old" is one of the ways to be wrong.
 *
 * So this reads the query cache itself rather than guessing. For every query a
 * page is actually rendering, it asks: did this data arrive in this session, or
 * from disk? If from disk, and it is being refreshed, has failed to refresh, or
 * cannot be refreshed because there is no connection, the bar says so and gives
 * the date of the oldest figure showing. When every figure on screen is from
 * this session, it disappears.
 *
 * It carries no accent colour. It is not an action and there is nothing here to
 * do; it is the app being honest about the numbers below it.
 */
type Freshness =
  | { kind: 'current' }
  | { kind: 'updating'; since: number }
  | { kind: 'failed'; since: number }
  /** `missing`: something on screen is waiting for a connection with nothing saved. */
  | { kind: 'offline'; since: number | null; missing: boolean }

export function FreshnessBanner() {
  const client = useQueryClient()
  const online = useConnection()

  const subscribe = useCallback((notify: () => void) => client.getQueryCache().subscribe(notify), [client])

  // A primitive snapshot: useSyncExternalStore compares with Object.is, so an
  // object built on every call would re-render forever.
  const summary = useSyncExternalStore(subscribe, () => {
    let oldestShown = Infinity // every figure on screen, for the offline case
    let oldestFlagged = Infinity // only the ones this notice is about
    let updating = false
    let failed = false
    let missing = false
    for (const query of client.getQueryCache().getAll()) {
      const { state } = query
      if (!query.getObserversCount()) continue
      // Held for a connection with nothing saved to show instead. Search is
      // left out: the palette says so itself, and it is not the page.
      if (state.data === undefined) {
        if (state.fetchStatus === 'paused' && query.queryKey[0] !== 'search') missing = true
        continue
      }
      oldestShown = Math.min(oldestShown, state.dataUpdatedAt)
      // From disk, or held so long this session that it might as well be.
      const notFresh = state.dataUpdatedAt < SESSION_STARTED_AT || Date.now() - state.dataUpdatedAt > AGED_AFTER
      // A refresh that failed while the old figures stayed up. Pages keep
      // showing data through a failure (see useReferenceQuery), so this is the
      // one place the failure is reported — whether the data came from disk or
      // from earlier in this session.
      const refreshFailed = state.fetchStatus === 'idle' && state.errorUpdatedAt > state.dataUpdatedAt
      if (refreshFailed) {
        failed = true
        oldestFlagged = Math.min(oldestFlagged, state.dataUpdatedAt)
      } else if (notFresh && state.fetchStatus !== 'idle') {
        updating = true
        oldestFlagged = Math.min(oldestFlagged, state.dataUpdatedAt)
      }
    }
    return `${oldestShown}|${oldestFlagged}|${updating}|${failed}|${missing}`
  })

  const freshness = read(summary, online)
  if (freshness.kind === 'current') return null
  return <Bar freshness={freshness} />
}

/**
 * The bar itself, which also makes room for itself.
 *
 * It is fixed over the bottom of the page, and without room made for it it
 * covered the footer — Privacy, Support and the nflverse credit could not be
 * tapped in exactly the states (offline, updating, a failed refresh) in which a
 * reviewer goes looking for the privacy policy. Its height is measured rather
 * than assumed: on a phone the sentence wraps to two or three lines.
 */
function Bar({ freshness }: { freshness: Exclude<Freshness, { kind: 'current' }> }) {
  const ref = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const bar = ref.current
    if (!bar) return
    const root = document.documentElement
    const measure = () => root.style.setProperty('--freshness-height', `${bar.offsetHeight}px`)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(bar)
    return () => {
      observer.disconnect()
      root.style.removeProperty('--freshness-height')
    }
  }, [])

  return (
    <div ref={ref} className="freshness-banner" role="status" aria-live="polite">
      {freshness.kind === 'offline' ? (
        <WifiOff size={14} aria-hidden="true" />
      ) : (
        <RefreshCw size={14} aria-hidden="true" className={freshness.kind === 'updating' ? 'is-spinning' : undefined} />
      )}
      <span>{sentence(freshness)}</span>
    </div>
  )
}

function read(summary: string, online: boolean): Freshness {
  const [shownRaw, flaggedRaw, updating, failed, missing] = summary.split('|')
  const finite = (raw: string) => (Number.isFinite(Number(raw)) ? Number(raw) : null)
  // A paused query is itself the sign of no connection, whatever the radio said last.
  if (!online || missing === 'true') return { kind: 'offline', since: finite(shownRaw), missing: missing === 'true' }
  const since = finite(flaggedRaw)
  if (since === null) return { kind: 'current' }
  // A failure outranks a refresh in progress: it is the one that will not
  // resolve itself while the visitor watches.
  if (failed === 'true') return { kind: 'failed', since }
  if (updating === 'true') return { kind: 'updating', since }
  // Saved, but still inside the app's own staleness window, so it is not being
  // refetched and is as current as a live answer would be.
  return { kind: 'current' }
}

function sentence(f: Exclude<Freshness, { kind: 'current' }>) {
  const saved = f.since === null ? null : <Stamp at={f.since} />
  switch (f.kind) {
    case 'offline':
      // "Showing figures saved …" over a page that shows none was the old
      // sentence here: the date came from the footer's coverage line.
      if (!saved) return <>No connection. Nothing on this page has been saved to this device.</>
      if (f.missing) return <>No connection. Part of this page has not been saved to this device; the rest was saved {saved}.</>
      return <>No connection. Showing figures saved {saved}.</>
    case 'updating':
      return <>Showing figures saved {saved} while the latest load.</>
    case 'failed':
      return <>Couldn&rsquo;t update. Showing figures saved {saved}.</>
  }
}

function Stamp({ at }: { at: number }) {
  const date = new Date(at)
  return (
    <time dateTime={date.toISOString()}>
      {date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
    </time>
  )
}

/**
 * Whether there is a connection, from the source that actually knows.
 *
 * On a device, Capacitor's Network plugin reports the radio; the browser's
 * navigator.onLine is only a hint. It is also handed to React Query, so fetches
 * pause when the signal goes and resume the moment it returns rather than
 * failing into error states in a tunnel.
 */
function useConnection(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  useEffect(() => {
    let live = true
    const settle = (connected: boolean) => {
      if (!live) return
      setOnline(connected)
      onlineManager.setOnline(connected)
    }
    Network.getStatus().then((s) => settle(s.connected)).catch(() => settle(navigator.onLine))
    const handle = Network.addListener('networkStatusChange', (s) => settle(s.connected))
    const up = () => settle(true)
    const down = () => settle(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      live = false
      handle.then((h) => h.remove()).catch(() => {})
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  return online
}
