import { Save, FolderOpen, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import type { FilterCondition, SortSpec } from '../types'
import { useSavedQueries } from '../hooks/useSavedQueries'

interface SavedQuery {
  id: string
  name: string
  datasetId: string
  filters: FilterCondition[]
  sort: SortSpec[]
  visibleColumns: string[]
  createdAt: number
}

interface SavedQueriesPanelProps {
  datasetId: string
  sorting: SortSpec[]
  visibleColumns: string[]
  filterConditions: FilterCondition[]
}

export function SavedQueriesPanel({
  datasetId,
  sorting,
  visibleColumns,
  filterConditions,
}: SavedQueriesPanelProps) {
  const { savedQueries, saveQuery, deleteQuery } = useSavedQueries()
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveName, setSaveName] = useState('')
  const datasetQueries = savedQueries.filter((q) => q.datasetId === datasetId) as SavedQuery[]

  const handleSave = () => {
    if (!saveName.trim()) return
    saveQuery(saveName, datasetId, filterConditions, sorting, visibleColumns)
    setSaveName('')
    setShowSaveDialog(false)
  }

  const handleLoad = (query: SavedQuery) => {
    // This would need to be handled by the parent component
    // For now we'll dispatch a custom event
    window.dispatchEvent(new CustomEvent('load-saved-query', { detail: query }))
  }

  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/50 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <FolderOpen className="h-5 w-5" />
          Saved Queries
        </h3>
        <button
          onClick={() => setShowSaveDialog(true)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-200 ring-1 ring-blue-400/40 hover:bg-blue-500/30 transition"
        >
          <Save className="h-4 w-4" />
          Save Current
        </button>
      </div>

      {datasetQueries.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-4">
          No saved queries yet. Click "Save Current" to save your filter setup.
        </p>
      ) : (
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {datasetQueries.map((query) => (
            <div
              key={query.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2.5"
            >
              <div className="flex-1 min-w-0" onClick={() => handleLoad(query)}>
                <p className="text-sm font-medium text-white truncate">{query.name}</p>
                <p className="text-[11px] text-slate-500">
                  {query.filters.length} filters, {query.visibleColumns.length} columns ·{' '}
                  {new Date(query.createdAt).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  deleteQuery(query.id)
                }}
                className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-red-400 transition"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {showSaveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between mb-4">
              <h4 className="font-semibold text-white">Save Query</h4>
              <button
                onClick={() => setShowSaveDialog(false)}
                className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white transition"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Enter a name for this query"
              className="w-full rounded-lg border border-white/10 bg-slate-800/70 px-3 py-2 text-sm text-slate-100 outline-none focus:border-blue-500/40 focus:ring-2 focus:ring-blue-500/20 mb-4"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 transition hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500/20 px-3 py-2 text-sm font-medium text-blue-200 ring-1 ring-blue-400/40 hover:bg-blue-500/30 transition"
              >
                <Save className="h-4 w-4" />
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}