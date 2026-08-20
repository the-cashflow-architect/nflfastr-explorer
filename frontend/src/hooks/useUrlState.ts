import { useCallback, useEffect, useState } from 'react'
import type { FilterCondition, SortSpec } from '../types'
import type { StatTab } from '../lib/statViews'

export type Route = 'players' | 'teams' | 'plays'

export interface UrlState {
  route: Route
  playerGranularity: 'week' | 'season'
  position: string
  statTab: StatTab
  filters: FilterCondition[]
  sort: SortSpec[]
  columns: string[]
  page: number
  chartView: boolean
}

export function useUrlState() {
  const [urlState, setUrlState] = useState<UrlState | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)

  const encodeState = useCallback((state: UrlState): string => {
    const json = JSON.stringify(state)
    return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
  }, [])

  const decodeState = useCallback((encoded: string): UrlState | null => {
    try {
      const padded = encoded.replace(/-/g, '+').replace(/_/g, '/')
      const json = atob(padded + '==='.slice((padded.length + 3) % 4))
      const parsed = JSON.parse(json)
      if (!parsed || typeof parsed !== 'object' || !parsed.route) return null
      return parsed as UrlState
    } catch {
      return null
    }
  }, [])

  const updateUrl = useCallback((state: UrlState, replace = false) => {
    const encoded = encodeState(state)
    const url = `${window.location.pathname}?state=${encoded}`
    if (replace) {
      window.history.replaceState(null, '', url)
    } else {
      window.history.pushState(null, '', url)
    }
  }, [encodeState])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const encoded = params.get('state')
    if (encoded) {
      const decoded = decodeState(encoded)
      if (decoded) {
        setUrlState(decoded)
        setIsRestoring(true)
        setTimeout(() => setIsRestoring(false), 100)
      }
    }
  }, [decodeState])

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search)
      const encoded = params.get('state')
      if (encoded) {
        const decoded = decodeState(encoded)
        if (decoded) {
          setUrlState(decoded)
          setIsRestoring(true)
          setTimeout(() => setIsRestoring(false), 100)
        }
      } else {
        setUrlState(null)
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [decodeState])

  const getShareableUrl = useCallback((state: UrlState): string => {
    const encoded = encodeState(state)
    return `${window.location.origin}${window.location.pathname}?state=${encoded}`
  }, [encodeState])

  const clearUrl = useCallback(() => {
    window.history.pushState(null, '', window.location.pathname)
    setUrlState(null)
  }, [])

  return {
    urlState,
    isRestoring,
    updateUrl,
    getShareableUrl,
    setUrlState,
    clearUrl,
  }
}
