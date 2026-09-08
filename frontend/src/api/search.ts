import { api } from './client'

/**
 * The search contract, in one file, so the client and server shapes are
 * reconciled in a single place rather than at eight call sites.
 */

export interface SearchHit {
  kind: 'player' | 'team' | 'team_season' | 'game' | 'season' | 'draft' | 'page'
  id: string
  title: string
  /** One line of disambiguating context: position and years, a final score. */
  subtitle?: string | null
  image?: string | null
  /** The route this hit navigates to. Built server-side so it cannot drift. */
  href: string
}

export interface SearchResponse {
  query: string
  groups: { kind: string; label: string; hits: SearchHit[] }[]
}

export function search(q: string, limit = 8): Promise<SearchResponse> {
  return api<SearchResponse>('/api/search', { q, limit })
}
