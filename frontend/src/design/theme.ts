/**
 * Theme and table density: the two per-visitor preferences, in one place.
 *
 * Both are applied to the document element as attributes and read by CSS, so no
 * component subscribes to them or re-renders when they change. The initial value
 * is written before first paint by a script in index.html; this module only
 * handles changes made after the app has mounted.
 */

export type ThemeChoice = 'system' | 'light' | 'dark'
export type Density = 'comfortable' | 'compact' | 'dense'

const THEME_KEY = 'gridiron.theme'
const DENSITY_KEY = 'gridiron.density'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    // Private windows and blocked site data throw rather than return null.
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* A preference that cannot be remembered still applies for this visit. */
  }
}

export function getTheme(): ThemeChoice {
  const stored = read(THEME_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

export function setTheme(choice: ThemeChoice): void {
  write(THEME_KEY, choice)
  applyTheme(choice)
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement
  // No attribute means "follow the system", which is what the CSS expects.
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
}

export function getDensity(): Density {
  const stored = read(DENSITY_KEY)
  return stored === 'comfortable' || stored === 'dense' ? stored : 'compact'
}

export function setDensity(density: Density): void {
  write(DENSITY_KEY, density)
  document.documentElement.setAttribute('data-density', density)
}

/** Per-page collapsible state, so a section a visitor opened stays open. */
export function getCollapsed(pageKey: string, sectionKey: string, fallback: boolean): boolean {
  const stored = read(`gridiron.collapsed.${pageKey}.${sectionKey}`)
  if (stored === '0') return false
  if (stored === '1') return true
  return fallback
}

export function setCollapsed(pageKey: string, sectionKey: string, collapsed: boolean): void {
  write(`gridiron.collapsed.${pageKey}.${sectionKey}`, collapsed ? '1' : '0')
}
