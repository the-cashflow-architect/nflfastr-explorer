import { Download } from 'lucide-react'
import { useState } from 'react'
import { exportDataset } from '../api'
import type { FilterCondition, SortSpec } from '../types'

interface ExportButtonProps {
  datasetId: string
  filters: FilterCondition[]
  sort: SortSpec[]
  columns: string[]
  totalRows: number
}

export function ExportButton({ datasetId, filters, sort, columns, totalRows }: ExportButtonProps) {
  const [exporting, setExporting] = useState(false)
  const [format, setFormat] = useState<'csv' | 'json'>('csv')
  const [notice, setNotice] = useState<string | null>(null)

  const handleExport = async () => {
    setExporting(true)
    setNotice(null)
    try {
      const result = await exportDataset(datasetId, { filters, sort, columns, format })
      const url = URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${datasetId}_export.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      if (result.truncated && result.rows != null && result.matchingRows != null) {
        setNotice(
          `Exported the first ${result.rows.toLocaleString()} of ${result.matchingRows.toLocaleString()} matching rows. Add filters to narrow the export.`,
        )
      }
    } catch (err) {
      console.error('Export failed:', err)
      setNotice('Export failed. Check the console for details.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex items-center gap-1">
      <div className="flex items-center gap-0.5 rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white p-1">
        <button
          type="button"
          onClick={() => setFormat('csv')}
          className={`rounded-md px-2.5 py-1 text-xs transition-all duration-200 ${
            format === 'csv'
              ? 'bg-blue-500/20 text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40'
              : 'text-slate-400 light:text-slate-500 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          CSV
        </button>
        <button
          type="button"
          onClick={() => setFormat('json')}
          className={`rounded-md px-2.5 py-1 text-xs transition-all duration-200 ${
            format === 'json'
              ? 'bg-blue-500/20 text-blue-200 light:text-blue-700 ring-1 ring-blue-400/40'
              : 'text-slate-400 light:text-slate-500 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          JSON
        </button>
      </div>
      <button
        type="button"
        onClick={handleExport}
        disabled={exporting || totalRows === 0}
        className="inline-flex items-center gap-2 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white px-3 py-2 text-sm text-slate-200 light:text-slate-700 transition-all duration-200 hover:bg-slate-800/80 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Download className="h-4 w-4" />
        Export ({totalRows.toLocaleString()})
      </button>
      {notice && (
        <p className="max-w-xs text-[11px] leading-snug text-amber-300/90" role="status">
          {notice}
        </p>
      )}
    </div>
  )
}
