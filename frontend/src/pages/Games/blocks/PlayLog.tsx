import { ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useGamePlays, type Game, type GamePlays } from '../../../api/endpoints'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import { TeamLink } from '../../../components/ui/EntityLink'
import { Segmented } from '../../../components/ui/Page'
import { QueryBoundary } from '../../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../../components/ui/useAnchorScroll'
import { num, ordinal, stat } from '../../../design/format'

type PlayRow = NonNullable<GamePlays['rows']>[number]
type FilterOptions = NonNullable<GamePlays['filter_options']>

/** A game is a few hundred plays; one page holds all of them, so nothing is paged away. */
const PAGE_SIZE = 500

/** The query parameters this block owns, all of them readable and shareable. */
const FILTER_KEYS = ['team', 'quarter', 'down', 'play_type', 'min_epa', 'drive'] as const

/**
 * The play log: every play of the game, filtered, virtualised, and deep-linkable
 * one row at a time.
 *
 * It ships closed behind its count because it is the largest thing on the site —
 * and it is not fetched until it is opened, which is the whole reason the game
 * payload does not carry it.
 *
 * The disclosure is controlled from the page rather than remembered per visitor
 * like `Section`'s: the drive chart and the win-probability chart both open this
 * block, and a control that cannot be opened by the thing that filters it would
 * be a dead end.
 */
export function PlayLog({
  gameId,
  info,
  season,
  open,
  onOpenChange,
}: {
  gameId: string
  info: NonNullable<Game['play_log']>
  season: number
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const wrapper = useRef<HTMLDivElement>(null)

  const filters = {
    team: params.get('team') ?? undefined,
    quarter: numberParam(params.get('quarter')),
    down: numberParam(params.get('down')),
    play_type: params.get('play_type') ?? undefined,
    min_abs_epa: numberParam(params.get('min_epa')),
    drive: numberParam(params.get('drive')),
  }
  const active = FILTER_KEYS.filter((key) => params.get(key))

  const query = useGamePlays(gameId, { ...filters, page_size: PAGE_SIZE }, open)
  const data = query.data
  const rows = useMemo(() => data?.rows ?? [], [data])

  // The options describe the whole game, not the filtered set, so they are kept
  // across a refetch: a filter bar that blinks out while the next page loads
  // makes the controls feel broken.
  const [options, setOptions] = useState<FilterOptions | null>(null)
  useEffect(() => {
    if (data?.filter_options) setOptions(data.filter_options)
  }, [data])

  useAnchorScroll(rows.length > 0)

  useEffect(() => {
    const anchor = location.hash.slice(1)
    if (!anchor.startsWith('play-') || rows.length === 0) return
    const index = rows.findIndex((row) => row.anchor === anchor)
    if (index < 0) return
    const found = document.getElementById(anchor)
    if (found) {
      found.scrollIntoView({ block: 'center' })
      return
    }
    // Past a hundred rows the table windows what it renders, so the row we were
    // sent to may not exist yet. Put its own scroller where the row will be —
    // the row height is the same token the table uses — and finish the job on
    // the next frame, once it has rendered.
    const scroller = wrapper.current?.querySelector('table')?.parentElement
    if (!scroller) return
    const rowHeight =
      Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--row-h')) || 30
    scroller.scrollTop = Math.max(0, index * rowHeight - scroller.clientHeight / 2)
    const frame = requestAnimationFrame(() => {
      document.getElementById(anchor)?.scrollIntoView({ block: 'center' })
    })
    return () => cancelAnimationFrame(frame)
  }, [location.hash, rows])

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value === null || value === '') next.delete(key)
    else next.set(key, value)
    // A filter is a view of this page, not a new place: it replaces.
    setParams(next, { replace: true })
  }

  const clearFilters = () => {
    const next = new URLSearchParams(params)
    for (const key of FILTER_KEYS) next.delete(key)
    setParams(next, { replace: true })
  }

  const columns = useMemo(
    () => playColumns(season, data?.coverage.air_yards_charted ?? false),
    [season, data?.coverage.air_yards_charted],
  )

  return (
    <section className="mb-6" ref={wrapper}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          className="motion-state flex items-center gap-1.5 text-left hover:text-accent"
        >
          <ChevronRight
            className={`h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
          />
          <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-[15px] font-semibold leading-5">Play-by-play log</span>
            {!open ? (
              <span className="text-[11px] text-ink-3">
                {info.total_plays ? `All ${info.total_plays} plays` : 'Every play of this game'}
                {active.length ? ` · ${active.length} filter${active.length > 1 ? 's' : ''} set` : ''}
              </span>
            ) : null}
          </span>
        </button>
      </div>

      {open ? (
        <>
          {options ? (
            <Filters
              options={options}
              params={params}
              onChange={setFilter}
              onClear={active.length ? clearFilters : undefined}
            />
          ) : null}

          <QueryBoundary isLoading={query.isPending} error={query.error} onRetry={() => void query.refetch()}>
            {data ? (
              <>
                <DataTable
                  rows={rows}
                  columns={columns}
                  rowKey={(row, index) => String(row.play_id ?? index)}
                  rowId={(row) => row.anchor}
                  emptyMessage="No play in this game matches these filters. Widen them and every play comes back."
                  onExport={(visible, sorted) =>
                    downloadCsv(`${gameId}-plays.csv`, visible, sorted, (row, column) => playCell(row, column.id))
                  }
                />
                <p className="mt-1.5 text-[11px] leading-4 text-ink-3">
                  {data.total !== null && data.total !== undefined && data.total > rows.length
                    ? `Showing the first ${rows.length} of ${data.total} matching plays. `
                    : ''}
                  Every row has its own address: this page followed by #play- and the play id.
                </p>
                {data.coverage_note ? (
                  <p className="mt-1 text-[11px] leading-4 text-ink-3">{data.coverage_note}</p>
                ) : null}
                {data.note ? <p className="mt-1 text-[11px] leading-4 text-ink-3">{data.note}</p> : null}
              </>
            ) : null}
          </QueryBoundary>
        </>
      ) : null}
    </section>
  )
}

function Filters({
  options,
  params,
  onChange,
  onClear,
}: {
  options: FilterOptions
  params: URLSearchParams
  onChange: (key: string, value: string | null) => void
  onClear?: () => void
}) {
  const minEpa = params.get('min_epa') ?? '0'
  const drive = params.get('drive')

  return (
    <div className="mb-3 flex flex-wrap items-end gap-x-5 gap-y-3">
      {options.teams.length > 1 ? (
        <Field label="Offence">
          <Segmented
            ariaLabel="Filter by club on offence"
            value={params.get('team') ?? ''}
            onChange={(value) => onChange('team', value)}
            options={[{ value: '', label: 'Both' }, ...options.teams.map((team) => ({ value: team, label: team }))]}
          />
        </Field>
      ) : null}

      {options.quarters.length > 1 ? (
        <Field label="Quarter">
          <Segmented
            ariaLabel="Filter by quarter"
            value={params.get('quarter') ?? ''}
            onChange={(value) => onChange('quarter', value)}
            options={[
              { value: '', label: 'All' },
              ...options.quarters.map((quarter) => ({
                value: String(quarter),
                label: quarter > 4 ? 'OT' : `Q${quarter}`,
              })),
            ]}
          />
        </Field>
      ) : null}

      {options.downs.length > 1 ? (
        <Field label="Down">
          <Segmented
            ariaLabel="Filter by down"
            value={params.get('down') ?? ''}
            onChange={(value) => onChange('down', value)}
            options={[
              { value: '', label: 'All' },
              ...options.downs.map((down) => ({ value: String(down), label: ordinal(down) })),
            ]}
          />
        </Field>
      ) : null}

      {options.play_types.length > 1 ? (
        <Field label="Play type">
          <select
            aria-label="Filter by play type"
            value={params.get('play_type') ?? ''}
            onChange={(event) => onChange('play_type', event.target.value)}
            className="motion-state rounded-md border border-line bg-raised px-2 py-1 text-[12px] text-ink hover:border-line-strong"
          >
            <option value="">Every type</option>
            {options.play_types.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </Field>
      ) : null}

      <Field label={`Minimum |EPA| ${minEpa === '0' ? '· any' : `· ${minEpa}`}`}>
        <input
          type="range"
          min={0}
          max={3}
          step={0.25}
          value={minEpa}
          aria-label="Minimum absolute EPA"
          onChange={(event) => onChange('min_epa', event.target.value === '0' ? null : event.target.value)}
          // The range track would otherwise take the browser's own accent, and
          // this page spends its one accent on the win-probability marker.
          style={{ accentColor: 'var(--c-text-secondary)' }}
          className="h-6 w-40"
        />
      </Field>

      {drive ? (
        <Field label="Drive">
          <span className="text-[12px] leading-6">
            {drive}
            <button
              type="button"
              onClick={() => onChange('drive', null)}
              className="motion-state ml-2 text-[11px] underline hover:text-accent"
            >
              clear
            </button>
          </span>
        </Field>
      ) : null}

      {onClear ? (
        <button type="button" onClick={onClear} className="motion-state pb-1 text-[12px] underline hover:text-accent">
          Clear all filters
        </button>
      ) : null}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase leading-4 tracking-[0.04em] text-ink-3">{label}</p>
      {children}
    </div>
  )
}

function playColumns(season: number, airYardsCharted: boolean): Column<PlayRow>[] {
  const columns: Column<PlayRow>[] = [
    { id: 'quarter', header: 'Q', width: '3rem', sortValue: (row) => -(row.seconds_remaining ?? 0), render: (row) => row.period_label },
    { id: 'clock', header: 'Clock', width: '4.5rem', sortValue: (row) => -(row.seconds_remaining ?? 0), render: (row) => row.clock ?? '—' },
    {
      id: 'posteam',
      header: 'Off',
      width: '4.5rem',
      sortValue: (row) => row.posteam,
      render: (row) => <TeamLink abbr={row.posteam} season={season} />,
    },
    {
      id: 'down',
      header: 'Dn & dist',
      width: '6rem',
      sortValue: (row) => row.down,
      render: (row) =>
        row.down === null || row.down === undefined ? (
          <span className="text-ink-3">—</span>
        ) : (
          `${ordinal(row.down)} & ${row.ydstogo ?? 0}`
        ),
    },
    {
      id: 'yardline',
      header: 'Ball on',
      width: '5.5rem',
      sortValue: (row) => row.yardline_100,
      render: (row) => ballOn(row),
    },
    { id: 'description', header: 'Play', render: (row) => <span className="text-ink-2">{row.description ?? '—'}</span> },
    {
      id: 'play_type',
      header: 'Type',
      width: '6rem',
      optional: true,
      sortValue: (row) => row.play_type,
      render: (row) => <span className="text-ink-2">{row.play_type?.replace(/_/g, ' ') ?? '—'}</span>,
    },
    { id: 'yards_gained', header: 'Yds', align: 'right', width: '4rem', sortValue: (row) => row.yards_gained, render: (row) => num(row.yards_gained, 0) },
    {
      id: 'epa',
      header: 'EPA',
      help: 'Expected points added by this play, from nflfastR’s open model.',
      align: 'right',
      width: '5rem',
      sortValue: (row) => row.epa,
      render: (row) => stat(row.epa, 'epa'),
    },
    {
      id: 'wpa',
      header: 'WPA',
      help: 'Win probability added by this play, from nflfastR’s open model.',
      align: 'right',
      width: '5rem',
      sortValue: (row) => row.wpa,
      render: (row) => stat(row.wpa, 'wpa'),
    },
    {
      id: 'success',
      header: 'Succ',
      help: 'A successful play gained positive expected points.',
      width: '4rem',
      sortValue: (row) => (row.success === null || row.success === undefined ? null : row.success ? 1 : 0),
      render: (row) =>
        row.success === null || row.success === undefined ? (
          <span className="text-ink-3">—</span>
        ) : row.success ? (
          'Y'
        ) : (
          <span className="text-ink-3">N</span>
        ),
    },
  ]
  // Air yards were not charted before 2006. The column is absent for those
  // games rather than a stack of dashes implying we looked.
  if (airYardsCharted) {
    columns.push({
      id: 'air_yards',
      header: 'Air yds',
      align: 'right',
      width: '5rem',
      optional: true,
      sortValue: (row) => row.air_yards,
      render: (row) => num(row.air_yards, 0),
    })
  }
  return columns
}

/** Field position the way a broadcast reads it: the club whose side of the field it is. */
function ballOn(row: PlayRow): React.ReactNode {
  const yards = row.yardline_100
  if (yards === null || yards === undefined) return <span className="text-ink-3">—</span>
  if (yards === 50) return '50'
  return yards > 50 ? `${row.posteam ?? 'Own'} ${100 - yards}` : `${row.defteam ?? 'Opp'} ${yards}`
}

function playCell(row: PlayRow, id: string): string | number | null | undefined {
  switch (id) {
    case 'quarter':
      return row.period_label
    case 'clock':
      return row.clock
    case 'posteam':
      return row.posteam
    case 'down':
      return row.down
    case 'yardline':
      return row.yardline_100
    case 'description':
      return row.description
    case 'play_type':
      return row.play_type
    case 'yards_gained':
      return row.yards_gained
    case 'epa':
      return row.epa
    case 'wpa':
      return row.wpa
    case 'success':
      return row.success === null || row.success === undefined ? '' : row.success ? 'Y' : 'N'
    case 'air_yards':
      return row.air_yards
    default:
      return null
  }
}

function numberParam(value: string | null): number | undefined {
  if (!value) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}
