import { useCallback, useEffect, useState } from 'react'

interface SavedQuery {
  id: string
  name: string
  datasetId: string
  filters: unknown[]
  sort: unknown[]
  visibleColumns: string[]
  createdAt: number
}

const STORAGE_KEY = 'nflfastr_saved_queries'

export function useSavedQueries() {
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([])

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        setSavedQueries(JSON.parse(stored))
      }
    } catch (e) {
      console.error('Failed to load saved queries:', e)
    }
  }, [])

  const saveQuery = useCallback((
    name: string,
    datasetId: string,
    filters: unknown[],
    sort: unknown[],
    visibleColumns: string[],
  ) => {
    const newQuery: SavedQuery = {
      id: crypto.randomUUID(),
      name,
      datasetId,
      filters,
      sort,
      visibleColumns,
      createdAt: Date.now(),
    }
    const updated = [newQuery, ...savedQueries].slice(0, 20)
    setSavedQueries(updated)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    return newQuery
  }, [savedQueries])

  const deleteQuery = useCallback((id: string) => {
    const updated = savedQueries.filter((q) => q.id !== id)
    setSavedQueries(updated)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
  }, [savedQueries])

  const loadQuery = useCallback((id: string) => {
    return savedQueries.find((q) => q.id === id)
  }, [savedQueries])

  return { savedQueries, saveQuery, deleteQuery, loadQuery }
}