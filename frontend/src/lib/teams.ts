/**
 * Team identity on the client.
 *
 * Codes here are always the *current* franchise code — the backend canonicalises
 * every source to it at load time, so `LA` covers the St. Louis Rams too. The
 * historical name is a display concern and comes from `labelInSeason`.
 */

export interface TeamMeta {
  abbr: string
  name: string
  nick: string
  conference: 'AFC' | 'NFC'
  division: string
  color: string
  logo: string
}

/** Names a franchise went by while it played under an older code. */
const HISTORICAL_NAMES: Record<string, { until: number; name: string }> = {
  LA: { until: 2015, name: 'St. Louis Rams' },
  LAC: { until: 2016, name: 'San Diego Chargers' },
  LV: { until: 2019, name: 'Oakland Raiders' },
}

/**
 * What this franchise was called in a given season.
 *
 * Printing "2013 Los Angeles Rams" is the kind of wrong a reference site does
 * not get to be, even though 2013 rows are keyed LA.
 */
export function labelInSeason(abbr: string, season: number, currentName: string): string {
  const historical = HISTORICAL_NAMES[abbr]
  return historical && season <= historical.until ? historical.name : currentName
}

/** Whether a team existed in a season, so we never link to an empty page. */
export function existedIn(abbr: string, season: number): boolean {
  if (abbr === 'HOU') return season >= 2002
  return season >= 1999
}
