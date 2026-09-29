import { Capacitor } from '@capacitor/core'
import type { Query } from '@tanstack/react-query'

/**
 * What the app knows when the server is slow or out of reach.
 *
 * The API sleeps on its hosting plan and takes about 43 seconds to wake. In a
 * browser tab that reads as a slow site; in an installed app it reads as a
 * broken one. So the last answer for every reference page is kept on disk and
 * shown at once while the real one is fetched.
 *
 * This is a cache, not a record: if iOS clears it the app simply asks again,
 * and nothing a visitor made is lost. That is why it lives in localStorage
 * rather than the durable store the other apps use for user data.
 *
 * WHAT IT MUST NEVER DO
 * Show an old number as though it were current. Anything on screen that came
 * from disk rather than from this session's request says so, with its date —
 * the FreshnessBanner reads it from the query cache itself. That rule is what
 * makes it safe to keep answers for a month rather than a day.
 */
export const isNative = Capacitor.isNativePlatform()

/** Bumped when the cached shape changes, so old entries are dropped not mangled. */
export const CACHE_KEY = 'gridiron.query-cache.v1'

/**
 * How long a saved answer may still be shown, clearly dated.
 *
 * A day was too short: someone who opens the app weekly would find the whole
 * snapshot discarded every time and wait out the cold start regardless. The
 * age is always on screen while it matters, so a three-week-old table is an
 * honest thing to show for the forty seconds until the fresh one lands.
 *
 * WHY NOT A MONTH
 * This is also every query's gcTime, which React Query hands to setTimeout, and
 * setTimeout's delay is a 32-bit signed integer: anything past 2^31 - 1 ms
 * (24.8 days) overflows and fires after about a millisecond. A 30-day value
 * garbage-collected every restored answer the instant it was hydrated, so the
 * cache restored nothing at all — caught by scripts/review-seed.mjs. The guard
 * below keeps it from coming back.
 */
export const CACHE_MAX_AGE = 21 * 24 * 60 * 60 * 1000

const TIMER_CEILING = 2 ** 31 - 1
if (CACHE_MAX_AGE > TIMER_CEILING) {
  throw new Error(`CACHE_MAX_AGE (${CACHE_MAX_AGE} ms) exceeds setTimeout's ${TIMER_CEILING} ms ceiling`)
}

/**
 * The moment this session began. A query whose data is older than this came
 * from disk (or the bundled seed), not from a request made since launch.
 */
export const SESSION_STARTED_AT = Date.now()

/**
 * Which answers are worth keeping.
 *
 * Reference pages, yes. Not the ad-hoc queries: every prefix typed into search,
 * every Finder filter combination and result page. Those are large, never
 * revisited, and would push the pages people do come back to out of a storage
 * budget of a few megabytes.
 *
 * Anything with data is kept, whatever became of its last refresh. This once
 * kept only status 'success' — but a refresh that fails with data on screen
 * flips a query to 'error' and keeps the data, so one run of failed requests
 * wrote a snapshot with nothing in it, the bundled seed included (seedIfEmpty
 * never refills a key that exists), and the next launch had nothing to show.
 * That is the subway case this cache exists for. A query with only an error
 * and no data is still never kept.
 */
const EPHEMERAL = new Set(['search', 'filter-options', 'finder'])

export function shouldPersist(query: Query): boolean {
  return query.state.data !== undefined && !EPHEMERAL.has(String(query.queryKey[0]))
}

/**
 * First launch, on a device: start from the snapshot bundled at build time.
 *
 * With an empty cache the first screen would be a 43-second wait — which is
 * exactly the screen an App Review reviewer sees on a fresh install. The
 * snapshot is the real home page as it stood when the app was built, dated as
 * such by the FreshnessBanner until the live answer replaces it.
 *
 * Only on a device, and only into an empty cache: it must never overwrite
 * anything fresher.
 */
export async function seedIfEmpty(): Promise<void> {
  if (!isNative) return
  try {
    if (localStorage.getItem(CACHE_KEY)) return
    const response = await fetch('/seed-cache.json', { cache: 'no-store' })
    if (!response.ok) return
    const seed = await response.text()
    // Parse before storing: a truncated file must not become the cache.
    const parsed = JSON.parse(seed)
    if (!parsed?.clientState?.queries?.length || typeof parsed.timestamp !== 'number') return
    // Stamped as written to this device, not as built. The persister throws
    // away a snapshot older than CACHE_MAX_AGE, so a build-time stamp meant any
    // install more than three weeks after `npm run ios` opened on the cold
    // start again. Each figure keeps its own dataUpdatedAt, which is the date
    // the FreshnessBanner shows, so nothing passes for newer than it is.
    parsed.timestamp = Date.now()
    localStorage.setItem(CACHE_KEY, JSON.stringify(parsed))
  } catch {
    // No seed is a slower first screen, never a broken one.
  }
}
