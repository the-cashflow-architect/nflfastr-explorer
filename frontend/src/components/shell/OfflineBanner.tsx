import { useEffect, useState } from 'react'
import { Network } from '@capacitor/network'
import { WifiOff } from 'lucide-react'
import { cachedAt } from '../../lib/offline'

/**
 * What the app says when it cannot reach the server.
 *
 * The saved answers let a page still show something with no network, which is
 * the whole point of keeping them — but a figure served from yesterday's cache
 * must never sit on screen pretending to be today's. A reference site that is
 * confidently wrong once is finished, and "the number was simply old" is one of
 * the ways to be wrong.
 *
 * So this is not a spinner, a toast or a retry prompt. It states two facts and
 * gets out of the way: there is no connection, and this is when the figures
 * below were last fetched. It uses no accent colour, because it is not an
 * action and nothing here is the primary thing to do.
 */
export function OfflineBanner() {
  const [offline, setOffline] = useState(false)
  const [saved, setSaved] = useState<Date | null>(null)

  useEffect(() => {
    let live = true

    const settle = (connected: boolean) => {
      if (!live) return
      setOffline(!connected)
      if (!connected) setSaved(cachedAt())
    }

    // Capacitor's Network plugin is the accurate one on a device; the browser's
    // navigator.onLine is the fallback and is only ever a hint.
    Network.getStatus()
      .then((s) => settle(s.connected))
      .catch(() => settle(navigator.onLine))

    const handle = Network.addListener('networkStatusChange', (s) => settle(s.connected))
    const onOnline = () => settle(true)
    const onOffline = () => settle(false)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    return () => {
      live = false
      handle.then((h) => h.remove()).catch(() => {})
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [])

  if (!offline) return null

  return (
    <div className="offline-banner" role="status">
      <WifiOff size={14} aria-hidden="true" />
      <span>
        No connection.{' '}
        {saved ? (
          <>
            Showing figures saved{' '}
            <time dateTime={saved.toISOString()}>
              {saved.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </time>
            .
          </>
        ) : (
          <>Nothing has been saved on this device yet.</>
        )}
      </span>
    </div>
  )
}
