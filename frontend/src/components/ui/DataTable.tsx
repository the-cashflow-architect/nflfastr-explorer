import { ArrowDown, ArrowUp, ChevronsUpDown, Columns3, Download, Link2, Rows3 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getDensity, setDensity, type Density } from '../../design/theme'
import { Empty } from './Honesty'

/**
 * The one table in the product.
 *
 * Design decisions worth not relitigating on each page:
 *
 * * **No zebra striping.** A 1px rule at 6% and a 4% hover tint carry the row
 *   boundary without turning the page into corduroy.
 * * **No colour for standing.** A value's quality is communicated by its rank,
 *   its percentile bar, or bold weight — never by hue. Only wins and losses get
 *   a semantic colour, and only because they are literally binary outcomes.
 * * **Numbers right, text left, always**, with tabular figures inherited from
 *   the body. A stats table whose columns do not align reads as amateur no
 *   matter how good the numbers are.
 * * **The first column stays put** when the table scrolls sideways. Losing track
 *   of whose row you are reading is the specific failure of a wide stat table.
 * * **Rows are windowed past a threshold** rather than paged, because a season
 *   leaderboard is a thing you scan, not a thing you paginate.
 */

export interface Column<Row> {
  id: string
  /** Short header text. Abbreviations get a glossary popover via `help`. */
  header: string
  /** Plain-language definition, shown on hover of an abbreviated header. */
  help?: string
  render: (row: Row) => React.ReactNode
  /** Sort key. Omit to make the column unsortable. */
  sortValue?: (row: Row) => number | string | null | undefined
  align?: 'left' | 'right'
  /** Hidden by default but available in the column picker and in exports. */
  optional?: boolean
  width?: string
  /** Renders in bold, for a career-total or league-total row. */
  emphasis?: boolean
}

export interface SortState {
  id: string
  desc: boolean
}

const VIRTUALIZE_ABOVE = 100
const OVERSCAN = 12

export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  initialSort,
  emptyMessage,
  stickyFirstColumn = true,
  toolbar,
  onExport,
  caption,
  footRow,
  rowId,
}: {
  rows: Row[]
  columns: Column<Row>[]
  rowKey: (row: Row, index: number) => string
  initialSort?: SortState
  /** One sentence saying *why* there is nothing here. Never "No data". */
  emptyMessage: React.ReactNode
  stickyFirstColumn?: boolean
  toolbar?: React.ReactNode
  onExport?: (visible: Column<Row>[], sorted: Row[]) => void
  caption?: React.ReactNode
  /** A totals row, rendered outside the sort. */
  footRow?: Row
  /** Gives each row a DOM id so it can be deep-linked. */
  rowId?: (row: Row) => string | undefined
}) {
  const [sort, setSort] = useState<SortState | undefined>(initialSort)
  const [hidden, setHidden] = useState<Set<string>>(
    () => new Set(columns.filter((c) => c.optional).map((c) => c.id)),
  )
  const [pickerOpen, setPickerOpen] = useState(false)
  const [density, setLocalDensity] = useState<Density>(getDensity)

  useEffect(() => {
    document.documentElement.setAttribute('data-density', density)
  }, [density])

  const visible = useMemo(() => columns.filter((c) => !hidden.has(c.id)), [columns, hidden])

  const sorted = useMemo(() => {
    if (!sort) return rows
    const column = columns.find((c) => c.id === sort.id)
    if (!column?.sortValue) return rows
    const read = column.sortValue
    // Copy before sorting: mutating the query cache's array makes React Query
    // hand the next consumer a differently-ordered list for no visible reason.
    return [...rows].sort((a, b) => {
      const av = read(a)
      const bv = read(b)
      // Missing values sink, in both directions. A blank is not a zero and
      // must not win a "lowest" sort.
      if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1
      if (bv === null || bv === undefined) return -1
      const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
      return sort.desc ? -cmp : cmp
    })
  }, [rows, sort, columns])

  const toggleSort = useCallback((column: Column<Row>) => {
    if (!column.sortValue) return
    setSort((current) =>
      current?.id === column.id ? { id: column.id, desc: !current.desc } : { id: column.id, desc: true },
    )
  }, [])

  const scroller = useRef<HTMLDivElement>(null)
  const [range, setRange] = useState({ start: 0, end: VIRTUALIZE_ABOVE })
  const virtualized = sorted.length > VIRTUALIZE_ABOVE
  const rowHeight = density === 'comfortable' ? 36 : density === 'dense' ? 24 : 30

  useEffect(() => {
    if (!virtualized) return
    const element = scroller.current
    if (!element) return
    const update = () => {
      const start = Math.max(0, Math.floor(element.scrollTop / rowHeight) - OVERSCAN)
      const visibleCount = Math.ceil(element.clientHeight / rowHeight) + OVERSCAN * 2
      setRange({ start, end: Math.min(sorted.length, start + visibleCount) })
    }
    update()
    element.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => {
      element.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [virtualized, rowHeight, sorted.length])

  const windowed = virtualized ? sorted.slice(range.start, range.end) : sorted
  const padTop = virtualized ? range.start * rowHeight : 0
  const padBottom = virtualized ? Math.max(0, (sorted.length - range.end) * rowHeight) : 0

  if (!rows.length) {
    return (
      <div>
        {toolbar ? <TableToolbar>{toolbar}</TableToolbar> : null}
        <Empty>{emptyMessage}</Empty>
      </div>
    )
  }

  return (
    <div>
      <TableToolbar>
        {toolbar}
        <div className="ml-auto flex items-center gap-1">
          <IconButton
            label="Choose columns"
            onClick={() => setPickerOpen((open) => !open)}
            active={pickerOpen}
          >
            <Columns3 className="h-4 w-4" />
          </IconButton>
          <IconButton
            label={`Row height: ${density}`}
            onClick={() => {
              const order: Density[] = ['comfortable', 'compact', 'dense']
              const next = order[(order.indexOf(density) + 1) % order.length]
              setLocalDensity(next)
              setDensity(next)
            }}
          >
            <Rows3 className="h-4 w-4" />
          </IconButton>
          {onExport ? (
            <IconButton label="Export as CSV" onClick={() => onExport(visible, sorted)}>
              <Download className="h-4 w-4" />
            </IconButton>
          ) : null}
          <IconButton
            label="Copy a link to this view"
            onClick={() => void navigator.clipboard?.writeText(window.location.href)}
          >
            <Link2 className="h-4 w-4" />
          </IconButton>
        </div>
      </TableToolbar>

      {pickerOpen ? (
        <ColumnPicker
          columns={columns}
          hidden={hidden}
          onToggle={(id) =>
            setHidden((current) => {
              const next = new Set(current)
              // Hiding is not deleting: a hidden column stays in the export.
              if (next.has(id)) next.delete(id)
              else next.add(id)
              return next
            })
          }
        />
      ) : null}

      <div
        ref={scroller}
        className={`overflow-x-auto ${virtualized ? 'max-h-[70vh] overflow-y-auto' : ''}`}
      >
        <table className="w-full border-collapse text-[13px]">
          {caption ? <caption className="pb-2 text-left text-[11px] text-ink-3">{caption}</caption> : null}
          <thead className="sticky top-0 z-20 bg-page">
            <tr>
              {visible.map((column, index) => (
                <th
                  key={column.id}
                  scope="col"
                  style={{ width: column.width }}
                  className={[
                    'border-b border-line-strong bg-page px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2',
                    column.align === 'right' ? 'text-right' : 'text-left',
                    stickyFirstColumn && index === 0 ? 'sticky left-0 z-30' : '',
                  ].join(' ')}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(column)}
                    title={column.help}
                    disabled={!column.sortValue}
                    className={`motion-state inline-flex items-center gap-1 ${
                      column.sortValue ? 'hover:text-ink' : 'cursor-default'
                    } ${column.align === 'right' ? 'flex-row-reverse' : ''}`}
                  >
                    <span className={column.help ? 'underline decoration-dotted underline-offset-2' : ''}>
                      {column.header}
                    </span>
                    {column.sortValue ? <SortCaret state={sort?.id === column.id ? sort : undefined} /> : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {padTop > 0 ? (
              <tr aria-hidden style={{ height: padTop }}>
                <td colSpan={visible.length} />
              </tr>
            ) : null}
            {windowed.map((row, index) => (
              <tr
                key={rowKey(row, range.start + index)}
                id={rowId?.(row)}
                className="motion-state border-b border-row-rule hover:bg-row-hover"
                style={{ height: 'var(--row-h)' }}
              >
                {visible.map((column, columnIndex) => (
                  <td
                    key={column.id}
                    className={[
                      'px-2',
                      column.align === 'right' ? 'text-right' : 'text-left',
                      column.emphasis ? 'font-semibold' : '',
                      stickyFirstColumn && columnIndex === 0
                        ? 'sticky left-0 z-10 bg-page'
                        : '',
                    ].join(' ')}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
            {padBottom > 0 ? (
              <tr aria-hidden style={{ height: padBottom }}>
                <td colSpan={visible.length} />
              </tr>
            ) : null}
          </tbody>
          {footRow ? (
            <tfoot>
              <tr className="border-t border-line-strong font-semibold">
                {visible.map((column, columnIndex) => (
                  <td
                    key={column.id}
                    className={[
                      'px-2 py-1.5',
                      column.align === 'right' ? 'text-right' : 'text-left',
                      stickyFirstColumn && columnIndex === 0 ? 'sticky left-0 z-10 bg-page' : '',
                    ].join(' ')}
                  >
                    {column.render(footRow)}
                  </td>
                ))}
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
      {virtualized ? (
        <p className="pt-1.5 text-[11px] text-ink-3">
          {sorted.length.toLocaleString()} rows · scroll to see the rest
        </p>
      ) : null}
    </div>
  )
}

function SortCaret({ state }: { state?: SortState }) {
  if (!state) return <ChevronsUpDown className="h-3 w-3 opacity-30" />
  return state.desc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />
}

function TableToolbar({ children }: { children?: React.ReactNode }) {
  if (!children) return null
  return <div className="mb-1.5 flex flex-wrap items-center gap-2">{children}</div>
}

function IconButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string
  onClick: () => void
  active?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`motion-state rounded border border-line p-1 text-ink-3 hover:border-line-strong hover:text-ink ${
        active ? 'border-line-strong text-ink' : ''
      }`}
    >
      {children}
    </button>
  )
}

function ColumnPicker<Row>({
  columns,
  hidden,
  onToggle,
}: {
  columns: Column<Row>[]
  hidden: Set<string>
  onToggle: (id: string) => void
}) {
  return (
    <div className="mb-2 rounded-md border border-line bg-raised p-2">
      <p className="mb-1.5 text-[11px] text-ink-3">
        Hidden columns stay in the export — hiding tidies the view, it does not drop the data.
      </p>
      <div className="flex flex-wrap gap-1">
        {columns.map((column) => {
          const shown = !hidden.has(column.id)
          return (
            <button
              key={column.id}
              type="button"
              onClick={() => onToggle(column.id)}
              aria-pressed={shown}
              className={`motion-state rounded border px-1.5 py-0.5 text-[11px] ${
                shown ? 'border-line-strong text-ink' : 'border-line text-ink-3'
              }`}
            >
              {column.header}
            </button>
          )
        })}
      </div>
    </div>
  )
}
