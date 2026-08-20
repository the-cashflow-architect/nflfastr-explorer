import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchFilterOptions } from '../api'
import { activeFiltersToConditions } from '../lib/filters'
import type { ActiveFilter, FilterDef } from '../types'
import { HelpHint } from './HelpHint'

interface TimeFilterProps {
  datasetId: string
  seasonDef: FilterDef | null
  weekDef: FilterDef | null
  activeFilters: ActiveFilter[]
  onChange: (next: ActiveFilter[]) => void
}

/**
 * Season and week are the one filter almost every visit starts with, so
 * they get their own always-visible row instead of living behind "+ Add
 * filter" like everything else. Week options are scoped to whichever
 * season(s) are picked — an in-progress season only offers the weeks it
 * actually has — and both support picking one value, many, or a
 * shift-click range in one motion.
 */
export function TimeFilter({ datasetId, seasonDef, weekDef, activeFilters, onChange }: TimeFilterProps) {
  const seasonActive = seasonDef ? activeFilters.find((f) => f.def.id === seasonDef.id) : undefined
  const weekActive = weekDef ? activeFilters.find((f) => f.def.id === weekDef.id) : undefined
  const selectedSeasons = (seasonActive?.value as unknown[]) ?? []
  const selectedWeeks = (weekActive?.value as unknown[]) ?? []

  const { data: seasonOptions } = useQuery({
    queryKey: ['filter-options', datasetId, seasonDef?.field, 'time-season'],
    queryFn: () => fetchFilterOptions(datasetId, { field: seasonDef!.field, filters: [], limit: 50 }),
    enabled: !!seasonDef,
  })

  const seasonConditions = seasonActive ? activeFiltersToConditions([seasonActive]) : []

  const { data: weekOptions } = useQuery({
    queryKey: ['filter-options', datasetId, weekDef?.field, seasonConditions],
    queryFn: () => fetchFilterOptions(datasetId, { field: weekDef!.field, filters: seasonConditions, limit: 50 }),
    enabled: !!weekDef,
  })

  const [lastSeasonClicked, setLastSeasonClicked] = useState<unknown>(null)
  const [lastWeekClicked, setLastWeekClicked] = useState<unknown>(null)

  if (!seasonDef) return null

  const setSeasons = (next: unknown[]) => {
    const without = activeFilters.filter((f) => f.def.id !== seasonDef.id && f.def.id !== weekDef?.id)
    if (next.length === 0) {
      onChange(without)
      return
    }
    onChange([...without, { def: seasonDef, value: next }])
  }

  const setWeeks = (next: unknown[]) => {
    if (!weekDef) return
    const without = activeFilters.filter((f) => f.def.id !== weekDef.id)
    if (next.length === 0) {
      onChange(without)
      return
    }
    onChange([...without, { def: weekDef, value: next }])
  }

  // Plain click toggles one value; shift-click selects the contiguous range
  // between the last click and this one — the fast way to grab "weeks 5-9"
  // without ten individual clicks. Works the same for seasons and weeks.
  const makeToggle = (
    options: unknown[],
    selected: unknown[],
    setValue: (next: unknown[]) => void,
    lastClicked: unknown,
    setLastClicked: (v: unknown) => void,
  ) => {
    return (value: unknown, shiftKey: boolean) => {
      if (shiftKey && lastClicked != null) {
        const from = options.findIndex((o) => String(o) === String(lastClicked))
        const to = options.findIndex((o) => String(o) === String(value))
        if (from !== -1 && to !== -1) {
          const [lo, hi] = from <= to ? [from, to] : [to, from]
          setValue(options.slice(lo, hi + 1))
          setLastClicked(value)
          return
        }
      }
      const set = new Set(selected.map(String))
      const key = String(value)
      if (set.has(key)) set.delete(key)
      else set.add(key)
      setValue(options.filter((o) => set.has(String(o))))
      setLastClicked(value)
    }
  }

  const sortedSeasons = [...(seasonOptions?.options ?? [])].sort((a, b) => Number(b) - Number(a))
  const sortedWeeks = [...(weekOptions?.options ?? [])].sort((a, b) => Number(a) - Number(b))

  const toggleSeason = makeToggle(sortedSeasons, selectedSeasons, setSeasons, lastSeasonClicked, setLastSeasonClicked)
  const toggleWeek = makeToggle(sortedWeeks, selectedWeeks, setWeeks, lastWeekClicked, setLastWeekClicked)

  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-2 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900/40 light:bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500">Season</span>
        {sortedSeasons.map((s) => {
          const active = selectedSeasons.some((v) => String(v) === String(s))
          return (
            <button
              key={String(s)}
              type="button"
              onClick={(e) => toggleSeason(s, e.shiftKey)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-all ${
                active
                  ? 'bg-blue-500/20 text-blue-100 light:text-blue-700 ring-1 ring-blue-400/40'
                  : 'bg-slate-800/80 light:bg-slate-100 text-slate-300 light:text-slate-600 ring-1 ring-white/5 light:ring-slate-200 hover:bg-slate-700/80'
              }`}
            >
              {String(s)}
            </button>
          )
        })}
        {selectedSeasons.length > 0 ? (
          <button type="button" onClick={() => setSeasons([])} className="text-[11px] text-slate-500 hover:text-slate-300">
            All seasons
          </button>
        ) : null}
        <HelpHint text="Click to pick one or many seasons — shift-click to grab a range. Leave empty to include every season." />
      </div>

      {weekDef ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-slate-400 light:text-slate-500">Week</span>
          {sortedWeeks.map((w) => {
            const active = selectedWeeks.some((v) => String(v) === String(w))
            return (
              <button
                key={String(w)}
                type="button"
                onClick={(e) => toggleWeek(w, e.shiftKey)}
                className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-medium transition-all ${
                  active
                    ? 'bg-blue-500/20 text-blue-100 light:text-blue-700 ring-1 ring-blue-400/40'
                    : 'bg-slate-800/80 light:bg-slate-100 text-slate-300 light:text-slate-600 ring-1 ring-white/5 light:ring-slate-200 hover:bg-slate-700/80'
                }`}
              >
                {String(w)}
              </button>
            )
          })}
          {sortedWeeks.length > 0 ? (
            <button type="button" onClick={() => setWeeks([])} className="text-[11px] text-slate-500 hover:text-slate-300">
              All weeks
            </button>
          ) : null}
          <HelpHint text="Click to pick one or many weeks, shift-click to grab a range (e.g. weeks 5-9). Leave empty for the full season. Only weeks that actually have data for the selected season(s) are shown." />
        </div>
      ) : null}
    </div>
  )
}
