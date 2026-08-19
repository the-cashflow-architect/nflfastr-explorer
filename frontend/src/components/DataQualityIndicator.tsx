import { Info, BarChart3, ShieldCheck } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { fetchDataQuality } from '../api'
import type { FilterCondition } from '../types'

interface DataQualityProps {
  datasetId: string
  filters: FilterCondition[]
  totalRows: number | undefined
}

export function DataQualityIndicator({ datasetId, filters, totalRows }: DataQualityProps) {
  const { data: qualityData } = useQuery({
    queryKey: ['data-quality', datasetId, filters],
    queryFn: () => fetchDataQuality(datasetId, { filters }),
    enabled: !!datasetId && filters.length >= 0,
    staleTime: 30_000,
  })

  if (!qualityData || !totalRows) return null

  const sampleSizePct = (qualityData.filtered_rows / qualityData.total_rows) * 100
  const lowSample = qualityData.filtered_rows < 30

  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm">
      <div className="flex items-center gap-4">
        <div className="inline-flex items-center gap-2">
          <ShieldCheck className={`h-4 w-4 ${lowSample ? 'text-red-400' : 'text-emerald-400'}`} />
          <span className={lowSample ? 'text-red-400' : 'text-emerald-400'}>
            {qualityData.filtered_rows.toLocaleString()} rows
          </span>
        </div>
        <div className="inline-flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-slate-500" />
          <span className="text-slate-400">
            {sampleSizePct.toFixed(1)}% of dataset
          </span>
        </div>
        {lowSample && (
          <div className="inline-flex items-center gap-1.5">
            <Info className="h-4 w-4 text-amber-400" />
            <span className="text-amber-400">Small sample size - results may not be significant</span>
          </div>
        )}
        {qualityData.columns.some((c) => c.null_pct > 50) && (
          <div className="inline-flex items-center gap-1.5">
            <Info className="h-4 w-4 text-amber-400" />
            <span className="text-amber-400">
              Some columns have &gt;50% null values
            </span>
          </div>
        )}
      </div>
      {qualityData.columns.filter((c) => c.null_pct > 20).length > 0 && (
        <div className="text-[11px] text-slate-500">
          High null rate:{' '}
          {qualityData.columns
            .filter((c) => c.null_pct > 20)
            .map((c) => c.label)
            .join(', ')}
        </div>
      )}
    </div>
  )
}