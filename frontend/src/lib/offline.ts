import { Capacitor } from '@capacitor/core'

/**
 * What the app knows when the network does not answer.
 *
 * The API sleeps on its hosting plan and takes about a minute to wake. In a
 * browser tab that reads as a slow site; in an installed app it reads as a
 * broken one, because an app is expected to open. So the last answer for every
 * page is kept on disk and shown immediately while the real one is fetched.
 *
 * This is a cache, not a record: if iOS clears it the app simply asks the
 * server again, and nothing a visitor made is lost. That is why it lives in
 * localStorage rather than the durable store the other apps use for user data.
 *
 * WHAT IT MUST NEVER DO
 * Show a stale number as though it were live. A reference site is only worth
 * anything if the figure on screen is the figure it claims to be, so anything
 * served from this cache while the network is unreachable has to say so and
 * say when. `cachedAt` is what the banner reads.
 */
export const isNative = Capacitor.isNativePlatform()

/** Bumped when the cached shape changes, so old entries are dropped not mangled. */
export const CACHE_KEY = 'gridiron.query-cache.v1'

/**
 * How long a saved answer may still be shown. Football data changes weekly at
 * most, so a day-old table is a useful thing to look at on a plane; a
 * month-old one is a lie waiting to happen.
 */
export const CACHE_MAX_AGE = 24 * 60 * 60 * 1000

/** When the cache was last written, or null if there is nothing saved. */
export function cachedAt(): Date | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const stamp = JSON.parse(raw)?.timestamp
    return typeof stamp === 'number' ? new Date(stamp) : null
  } catch {
    return null
  }
}
