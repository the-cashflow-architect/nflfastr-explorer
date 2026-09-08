import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/**
 * What the site actually holds, straight from the server's load log.
 *
 * Every coverage year rendered anywhere in the product comes from here. A year
 * typed into a component is the one thing guaranteed to drift from reality the
 * first time the data window moves, which is exactly the lie this endpoint
 * exists to prevent.
 */

export interface DatasetCoverage {
  id: string
  name: string
  description: string
  /** What is loaded, not what was hoped for. */
  first_season: number | null
  last_season: number | null
  row_count: number | null
  loaded_at: string | null
  coverage_note: string
}

export interface Coverage {
  datasets: DatasetCoverage[]
  windows: Record<string, number>
  not_available: { what: string; why: string }[]
  latest_completed_season: number | null
  disk_bytes?: number
}

export function useCoverage() {
  return useQuery({
    queryKey: ['coverage'],
    queryFn: () => api<Coverage>('/api/coverage'),
    staleTime: 60 * 60 * 1000,
  })
}

/** A named window (`stats_first_season`, `charting_first_season`, …). */
export function useWindow(name: string): number | undefined {
  const { data } = useCoverage()
  return data?.windows?.[name]
}
