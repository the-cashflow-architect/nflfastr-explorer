import { useCallback, useEffect, useState } from 'react'
import type { FilterCondition, SortSpec } from '../types'

interface UrlState {
  datasetId: string
  filters: FilterCondition[]
  sort: SortSpec[]
  columns: string[]
  page: number
  viewMode: 'explore' | 'compare'
  exploreView: 'table' | 'chart'
}

export function useUrlState() {
  const [urlState, setUrlState] = useState<UrlState | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)

  // Encode state to base64 URL-safe string
  const encodeState = useCallback((state: UrlState): string => {
    const json = JSON.stringify(state)
    return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
  }, [])

  // Decode state from base64 URL-safe string
  const decodeState = useCallback((encoded: string): UrlState | null => {
    try {
      const padded = encoded.replace(/-/g, '+').replace(/_/g, '/')
      const json = atob(padded + '==='.slice((padded.length + 3) % 4))
      return JSON.parse(json)
    } catch {
      return null
    }
  }, [])

  // Update URL with current state
  const updateUrl = useCallback((state: UrlState, replace = false) => {
    const encoded = encodeState(state)
    const url = `${window.location.pathname}?state=${encoded}`
    if (replace) {
      window.history.replaceState(null, '', url)
    } else {
      window.history.pushState(null, '', url)
    }
  }, [encodeState])

  // Initialize from URL on mount
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

  // Listen for popstate (back/forward buttons)
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
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [decodeState])

  // Generate shareable link
  const getShareableUrl = useCallback((state: UrlState): string => {
    const encoded = encodeState(state)
    return `${window.location.origin}${window.location.pathname}?state=${encoded}`
  }, [encodeState])

  return {
    urlState,
    isRestoring,
    updateUrl,
    getShareableUrl,
    setUrlState,
  }
}