import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { search, type SearchHit } from '../../api/search'
import { Mark } from '../ui/Mark'

/**
 * One search for the whole product: a header button on desktop, and a palette on
 * Cmd/Ctrl+K or "/" everywhere.
 *
 * The rule that earns its keep is the failure case. If the endpoint is
 * unreachable, the palette says so. It never shows "no results", because a
 * visitor cannot tell an outage from a spelling mistake, and on a reference site
 * that difference decides whether they trust the next number they see.
 */

const RECENT_KEY = 'gridiron.recent-searches'
const MAX_RECENT = 5

function readRecent(): SearchHit[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? (JSON.parse(raw) as SearchHit[]).slice(0, MAX_RECENT) : []
  } catch {
    return []
  }
}

function rememberRecent(hit: SearchHit): void {
  try {
    const existing = readRecent().filter((h) => h.href !== hit.href)
    localStorage.setItem(RECENT_KEY, JSON.stringify([hit, ...existing].slice(0, MAX_RECENT)))
  } catch {
    /* A search we cannot remember still worked. */
  }
}

export function SearchLauncher() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable
      if ((event.key === 'k' && (event.metaKey || event.ctrlKey)) || (event.key === '/' && !typing)) {
        event.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="motion-state flex items-center gap-2 rounded-md border border-line px-2 py-1 text-[12px] text-ink-3 hover:border-line-strong hover:text-ink"
      >
        <Search className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded border border-line px-1 text-[10px] sm:inline">⌘K</kbd>
      </button>
      {open ? <SearchPalette onClose={() => setOpen(false)} /> : null}
    </>
  )
}

export function SearchPalette({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const restoreFocus = useRef<Element | null>(null)

  useEffect(() => {
    restoreFocus.current = document.activeElement
    inputRef.current?.focus()
    return () => {
      // Escape must put focus back exactly where it was, or keyboard users lose
      // their place every time they glance at search.
      ;(restoreFocus.current as HTMLElement | null)?.focus?.()
    }
  }, [])

  const { data, error, isFetching } = useQuery({
    queryKey: ['search', query],
    queryFn: () => search(query),
    enabled: query.trim().length >= 2,
    staleTime: 30_000,
  })

  const recent = query ? [] : readRecent()
  const hits: SearchHit[] = query.trim().length >= 2 ? (data?.groups.flatMap((g) => g.hits) ?? []) : recent

  const go = useCallback(
    (hit: SearchHit) => {
      rememberRecent(hit)
      navigate(hit.href)
      onClose()
    },
    [navigate, onClose],
  )

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-line bg-raised shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-line px-3">
          <Search className="h-4 w-4 shrink-0 text-ink-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') onClose()
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActive((i) => Math.min(i + 1, hits.length - 1))
              }
              if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((i) => Math.max(i - 1, 0))
              }
              if (event.key === 'Enter' && hits[active]) go(hits[active])
            }}
            placeholder="Find any player, team, or game"
            className="w-full bg-transparent py-3 text-[15px] outline-none placeholder:text-ink-3"
          />
        </div>

        <div className="max-h-[50vh] overflow-y-auto py-1">
          {error ? (
            <p className="px-3 py-4 text-[13px] text-negative">
              {error instanceof ApiError && error.status === 0
                ? 'Search is unreachable right now — this is not “no results”.'
                : 'Search failed. Try again in a moment.'}
            </p>
          ) : query.trim().length >= 2 && !hits.length && !isFetching ? (
            <p className="px-3 py-4 text-[13px] text-ink-3">
              Nothing matches “{query}”. Players are searchable from 1999 onward.
            </p>
          ) : null}

          {!query && recent.length ? (
            <p className="px-3 pb-1 pt-2 text-[11px] uppercase tracking-wide text-ink-3">
              Recent · this browser only
            </p>
          ) : null}

          {(query.trim().length >= 2 ? (data?.groups ?? []) : [{ kind: 'recent', label: '', hits: recent }])
            .filter((group) => group.hits.length)
            .map((group) => (
              <div key={group.kind}>
                {group.label ? (
                  <p className="px-3 pb-1 pt-2 text-[11px] uppercase tracking-wide text-ink-3">{group.label}</p>
                ) : null}
                {group.hits.map((hit) => {
                  const index = hits.indexOf(hit)
                  return (
                    <button
                      key={`${hit.kind}-${hit.id}`}
                      type="button"
                      onMouseEnter={() => setActive(index)}
                      onClick={() => go(hit)}
                      className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left ${
                        index === active ? 'bg-row-hover' : ''
                      }`}
                    >
                      <Mark src={hit.image} label={hit.title} size={24} rounded />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px]">{hit.title}</span>
                        {hit.subtitle ? (
                          <span className="block truncate text-[11px] text-ink-3">{hit.subtitle}</span>
                        ) : null}
                      </span>
                    </button>
                  )
                })}
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}
