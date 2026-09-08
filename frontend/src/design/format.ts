/**
 * Every number the product prints goes through here.
 *
 * Decimals are a property of the stat, not of the component that happens to be
 * rendering it. Yards are whole numbers; EPA per play carries three; rates carry
 * one. Deciding that per component is how the same statistic ends up with two
 * different precisions on two pages, which reads as carelessness on a reference
 * site even when the underlying number is right.
 */

/** Stats whose display precision differs from the default of one decimal. */
const DECIMALS: Record<string, number> = {
  // Counting stats are whole.
  yards: 0, attempts: 0, completions: 0, receptions: 0, targets: 0, carries: 0,
  touchdowns: 0, games: 0, plays: 0, snaps: 0, points: 0, rank: 0,
  // Per-play values are small and need the resolution.
  epa_per_play: 3, cpoe: 1, wpa: 3,
  // Rates.
  success_rate: 1, completion_pct: 1, snap_pct: 1, win_pct: 3,
}

const DEFAULT_DECIMALS = 1

export function decimalsFor(stat: string): number {
  if (stat in DECIMALS) return DECIMALS[stat]
  if (/_(yards|tds|attempts|completions|receptions|targets|carries|games|plays|snaps)$/.test(stat)) return 0
  if (/(_pct|_rate|_share|percentage)$/.test(stat)) return 1
  if (/_epa$|^epa$|_wpa$|^wpa$/.test(stat)) return 3
  return DEFAULT_DECIMALS
}

/** A number for display, or an em dash when there is genuinely nothing to show. */
export function num(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function stat(value: number | null | undefined, statId: string): string {
  return num(value, decimalsFor(statId))
}

/** Signed, for values where the sign is the point (EPA, point differential). */
export function signed(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const body = num(Math.abs(value), decimals)
  return value < 0 ? `−${body}` : `+${body}`
}

export function percent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${num(value, decimals)}%`
}

/** A rate stored as 0–1 rendered as a percentage. */
export function rate(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return percent(value * 100, decimals)
}

/** Win percentage, which football writes as .625 rather than 62.5%. */
export function winPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(3).replace(/^0/, '')
}

export function record(w: number, l: number, t = 0): string {
  return t > 0 ? `${w}-${l}-${t}` : `${w}-${l}`
}

/** 1st, 2nd, 3rd — used for ranks, which are always shown with their cohort. */
export function ordinal(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  const rem100 = n % 100
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`
  switch (n % 10) {
    case 1: return `${n}st`
    case 2: return `${n}nd`
    case 3: return `${n}rd`
    default: return `${n}th`
  }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Dates are parsed as plain calendar dates, never shifted into the viewer's zone. */
export function gameDate(iso: string | null | undefined, opts?: { year?: boolean }): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return '—'
  const base = `${MONTHS[m - 1]} ${d}`
  return opts?.year === false ? base : `${base}, ${y}`
}

/** Age in whole years at a given date, which is how a game log reports it. */
export function ageAt(birthIso: string | null | undefined, onIso: string | null | undefined): number | null {
  if (!birthIso || !onIso) return null
  const birth = new Date(`${birthIso.slice(0, 10)}T00:00:00Z`)
  const on = new Date(`${onIso.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(birth.getTime()) || Number.isNaN(on.getTime())) return null
  let age = on.getUTCFullYear() - birth.getUTCFullYear()
  const monthDiff = on.getUTCMonth() - birth.getUTCMonth()
  if (monthDiff < 0 || (monthDiff === 0 && on.getUTCDate() < birth.getUTCDate())) age -= 1
  return age >= 0 ? age : null
}

/** Inches to feet and inches, the only way a roster ever prints height. */
export function height(inches: number | null | undefined): string {
  if (!inches) return '—'
  return `${Math.floor(inches / 12)}-${inches % 12}`
}

export function clock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Plural without the "(s)" that gives away a template. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`
}

/** A URL-safe name for the optional slug segment of a player URL. */
export function slugify(name: string | null | undefined): string {
  if (!name) return ''
  return name
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}
