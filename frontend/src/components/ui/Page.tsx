import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getCollapsed, setCollapsed } from '../../design/theme'

/**
 * The four repeated patterns. Every page in the product is built from these, so
 * that six people building six pages produce one product rather than six.
 *
 * The constraints are deliberate and worth keeping: a page header has no hero
 * image and exactly one accent action; a tile row has at most four tiles and no
 * colour; a tile without an honest context line does not ship; a collapsed
 * section states its count, because that count is the whisper that there is more
 * underneath.
 */

export function PageHeader({
  title,
  mark,
  meta,
  action,
  prev,
  next,
  subnav,
}: {
  title: React.ReactNode
  /** A 40px logo or headshot, when the page is about a thing with a face. */
  mark?: React.ReactNode
  /** One line of pipe-separated facts. Not a paragraph. */
  meta?: React.ReactNode
  /** The single accent-coloured action on the page. */
  action?: React.ReactNode
  prev?: { to: string; label: string }
  next?: { to: string; label: string }
  subnav?: React.ReactNode
}) {
  return (
    <header className="border-b border-line pb-4">
      <div className="flex items-start gap-3">
        {mark ? <div className="mt-0.5 h-10 w-10 shrink-0">{mark}</div> : null}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {prev ? <SiblingArrow to={prev.to} label={prev.label} direction="prev" /> : null}
            <h1 className="min-w-0 text-[24px] font-semibold leading-8 tracking-[-0.01em]">{title}</h1>
            {next ? <SiblingArrow to={next.to} label={next.label} direction="next" /> : null}
          </div>
          {meta ? <p className="mt-1 text-[12px] leading-4 text-ink-3">{meta}</p> : null}
        </div>
        {action ? <div className="shrink-0 pt-0.5">{action}</div> : null}
      </div>
      {subnav ? <div className="mt-3">{subnav}</div> : null}
    </header>
  )
}

function SiblingArrow({
  to,
  label,
  direction,
}: {
  to: string
  label: string
  direction: 'prev' | 'next'
}) {
  const Icon = direction === 'prev' ? ChevronLeft : ChevronRight
  return (
    <Link
      to={to}
      title={label}
      aria-label={label}
      className="motion-state rounded border border-line p-1 text-ink-3 no-underline hover:border-line-strong hover:text-ink"
    >
      <Icon className="h-4 w-4" />
    </Link>
  )
}

/** The one primary action per page. There is never a second. */
export function PrimaryAction({
  to,
  onClick,
  children,
}: {
  to?: string
  onClick?: () => void
  children: React.ReactNode
}) {
  const className =
    'motion-state inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-on-accent no-underline hover:bg-accent-hover'
  if (to) {
    return (
      <Link to={to} className={className}>
        {children}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {children}
    </button>
  )
}

export function Section({
  title,
  note,
  controls,
  children,
  /** A section that ships closed states its content count in the header. */
  collapsible,
  count,
  pageKey,
  sectionKey,
  defaultCollapsed = false,
}: {
  title: string
  note?: React.ReactNode
  controls?: React.ReactNode
  children: React.ReactNode
  collapsible?: boolean
  count?: string
  pageKey?: string
  sectionKey?: string
  defaultCollapsed?: boolean
}) {
  const storageKey = pageKey && sectionKey ? { pageKey, sectionKey } : null
  const [collapsed, setLocalCollapsed] = useState(() =>
    storageKey ? getCollapsed(storageKey.pageKey, storageKey.sectionKey, defaultCollapsed) : defaultCollapsed,
  )

  const toggle = () => {
    const next = !collapsed
    setLocalCollapsed(next)
    if (storageKey) setCollapsed(storageKey.pageKey, storageKey.sectionKey, next)
  }

  const heading = (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 className="text-[15px] font-semibold leading-5">{title}</h2>
      {count && collapsed ? <span className="text-[11px] text-ink-3">{count}</span> : null}
      {note ? <span className="text-[11px] text-ink-3">{note}</span> : null}
    </div>
  )

  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        {collapsible ? (
          <button
            type="button"
            onClick={toggle}
            aria-expanded={!collapsed}
            className="motion-state flex items-center gap-1.5 text-left hover:text-accent"
          >
            <ChevronRight
              className={`h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200 ${collapsed ? '' : 'rotate-90'}`}
            />
            {heading}
          </button>
        ) : (
          heading
        )}
        {controls && !collapsed ? <div className="shrink-0">{controls}</div> : null}
      </div>
      {collapsible && collapsed ? null : children}
    </section>
  )
}

/**
 * At most four tiles, no colour, and every tile carries a context line — a rank,
 * a cohort size, or the era its number covers. A big number with nothing to
 * compare it to is decoration.
 */
export function TileRow({ children }: { children: React.ReactNode }) {
  return <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">{children}</div>
}

export function Tile({
  label,
  value,
  context,
}: {
  label: string
  value: React.ReactNode
  /** Required by design: a tile with nothing honest to say here does not ship. */
  context: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2.5">
      <p className="text-[11px] uppercase leading-4 tracking-[0.04em] text-ink-3">{label}</p>
      <p className="mt-0.5 text-[28px] font-medium leading-8">{value}</p>
      <p className="text-[11px] leading-4 text-ink-3">{context}</p>
    </div>
  )
}

/** Small inline context: "3rd of 32", "n = 214". Never coloured. */
export function Chip({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className="ml-1.5 text-[11px] text-ink-3">
      {children}
    </span>
  )
}

/** A horizontal segmented control — the season picker, the scope toggle. */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="flex flex-wrap gap-px overflow-hidden rounded-md border border-line">
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={String(option.value)}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={`motion-state px-2.5 py-1 text-[12px] ${
              active ? 'bg-sunken font-medium text-ink' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
