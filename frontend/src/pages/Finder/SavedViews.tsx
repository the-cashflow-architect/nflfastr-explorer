import { Bookmark, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Section } from '../../components/ui/Page'

/**
 * Named queries, kept in this browser.
 *
 * They are deliberately not an account feature, and the block says so in the
 * one place a visitor might otherwise assume otherwise — a saved view that
 * silently vanishes on another device is the kind of small lie this product
 * does not tell.
 *
 * The whole query lives in the URL, so a "view" is just its query string.
 * That means a saved view survives every change to this page's internals, and
 * a visitor can share one by copying the link instead.
 */

const KEY = 'gridiron.finder.views'
const MAX = 20

export interface SavedView {
  name: string
  /** The Finder's full query string, without the leading "?". */
  search: string
  savedAt: string
}

function read(): SavedView[] {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? (JSON.parse(raw) as SavedView[]) : []
    return Array.isArray(parsed) ? parsed.slice(0, MAX) : []
  } catch {
    // A private window throws on access rather than returning null.
    return []
  }
}

function write(views: SavedView[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(views.slice(0, MAX)))
  } catch {
    /* A view we cannot remember still ran; the URL is the real record. */
  }
}

export function SavedViews({
  search,
  canSave,
  onLoad,
}: {
  /** The current query string, saved verbatim. */
  search: string
  /** Saving is offered only once there is a query worth naming. */
  canSave: boolean
  onLoad: (search: string) => void
}) {
  const [views, setViews] = useState<SavedView[]>(read)
  const [name, setName] = useState('')

  // Nothing saved and nothing to save: the block is not on the page at all.
  if (!canSave && views.length === 0) return null

  const save = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    const next = [
      { name: trimmed, search, savedAt: new Date().toISOString() },
      ...views.filter((view) => view.name !== trimmed),
    ].slice(0, MAX)
    setViews(next)
    write(next)
    setName('')
  }

  const remove = (target: SavedView) => {
    const next = views.filter((view) => view !== target)
    setViews(next)
    write(next)
  }

  return (
    <Section
      title="Saved views"
      note="Stored in this browser only — not in an account, and gone if you clear site data."
      collapsible
      count={`${views.length} saved`}
      pageKey="finder"
      sectionKey="saved-views"
    >
      {views.length ? (
        <ul className="mb-2 flex flex-wrap gap-1.5">
          {views.map((view) => (
            <li key={view.name} className="flex items-center gap-1 rounded-md border border-line px-2 py-1">
              <button
                type="button"
                onClick={() => onLoad(view.search)}
                className="motion-state text-[12px] hover:text-accent"
              >
                {view.name}
              </button>
              <button
                type="button"
                onClick={() => remove(view)}
                aria-label={`Delete ${view.name}`}
                title={`Delete ${view.name}`}
                className="motion-state rounded p-0.5 text-ink-3 hover:text-ink"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-2 text-[12px] text-ink-3">Nothing saved yet. Name the query below to keep it.</p>
      )}

      {canSave ? (
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') save()
            }}
            placeholder="Name this query"
            aria-label="Name this query"
            className="rounded-md border border-line bg-raised px-2 py-1 text-[12px] outline-none focus:border-line-strong"
          />
          <button
            type="button"
            onClick={save}
            disabled={!name.trim()}
            className="motion-state inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-[12px] hover:border-line-strong disabled:opacity-40"
          >
            <Bookmark className="h-4 w-4" aria-hidden />
            Save view
          </button>
        </div>
      ) : null}
    </Section>
  )
}
