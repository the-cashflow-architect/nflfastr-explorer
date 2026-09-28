import { SplashScreen } from '@capacitor/splash-screen'
import { StatusBar, Style } from '@capacitor/status-bar'
import { isNative } from './offline'

/**
 * The two pieces of device chrome the web build has no say over.
 *
 * Both are no-ops in a browser, so callers never ask which platform they are on.
 */

/**
 * Take the launch screen down.
 *
 * Capacitor's default drops the splash after half a second whether or not
 * anything is drawn, and the visitor sees a blank frame; so this takes it down
 * on the first frame instead, whatever that frame holds. An error message on
 * screen is recoverable; a logo that never leaves is not, and it also swallows
 * every touch. capacitor.config.json keeps a four-second self-hide as the
 * backstop for a launch where this never runs, or runs a moment before the
 * splash is up (iOS ignores a hide that arrives that early).
 */
export function revealApp(): void {
  if (!isNative) return
  requestAnimationFrame(() => {
    SplashScreen.hide().catch(() => {
      /* the four-second self-hide in capacitor.config.json takes it down */
    })
  })
  syncStatusBar()
}

const darkQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null

function isDark(): boolean {
  const chosen = document.documentElement.getAttribute('data-theme')
  if (chosen === 'light') return false
  if (chosen === 'dark') return true
  return darkQuery?.matches ?? false
}

/**
 * Keep the clock and battery legible over the page.
 *
 * The site can be light or dark independently of the phone's own setting, so
 * iOS's default (follow the phone) would put white text on a white header for
 * anyone who picked the light theme on a phone set to dark.
 */
export function syncStatusBar(): void {
  if (!isNative) return
  // Style.Dark is "for dark backgrounds": light text.
  StatusBar.setStyle({ style: isDark() ? Style.Dark : Style.Light }).catch(() => {
    /* a device that refuses it is still perfectly usable */
  })
}

// Someone on "follow the system" whose phone switches at sunset.
darkQuery?.addEventListener('change', syncStatusBar)

/**
 * Where the website lives. Inside the app the page's own address is
 * capacitor://localhost/…, which opens nothing for anyone it is sent to.
 */
const PUBLIC_SITE = 'https://nflfastr-explorer.onrender.com'

/** A link to this view that works for whoever receives it. */
export function shareableUrl(): string {
  if (!isNative) return window.location.href
  const { pathname, search, hash } = window.location
  return `${PUBLIC_SITE}${pathname}${search}${hash}`
}

/**
 * Whether a file can be handed to the visitor.
 *
 * The browser pattern — a blob URL clicked through a hidden <a download> — does
 * nothing in the iOS web view: Capacitor passes the blob URL to the system,
 * nothing opens it, and the navigation is cancelled without a word. A button
 * that silently does nothing (or, in the Finder, reports "Exported N rows"
 * when nothing was saved) is worse than no button, so export is offered only
 * where it works. The website still has it.
 */
export const canDownload = !isNative
