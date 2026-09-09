import { EraBadge } from '../../components/ui/Honesty'
import { Segmented } from '../../components/ui/Page'

/**
 * The Finder's mode row: which dataset the query runs against.
 *
 * The list is never written down here. It is whatever `GET /api/datasets`
 * registers, so a mode that is not actually queryable cannot appear as a dead
 * option, and a mode the backend adds later shows up without a frontend change.
 */

export interface FinderMode {
  /** What appears in the URL. */
  slug: string
  datasetId: string
  name: string
  description: string
  source: string
}

export function ModeSelector({
  modes,
  value,
  onChange,
  seasons,
  rowCount,
}: {
  modes: FinderMode[]
  value: string
  onChange: (slug: string) => void
  /** The seasons this mode actually holds, read from the dataset itself. */
  seasons: number[] | undefined
  rowCount: number | null | undefined
}) {
  const active = modes.find((mode) => mode.slug === value)
  // Seasons come back from the dataset's own season field, so the window is
  // what is loaded rather than what was hoped for. No window is printed until
  // that answer arrives — a guessed year is worse than a missing line.
  const covered = seasons?.length ? { from: Math.min(...seasons), to: Math.max(...seasons) } : null

  return (
    <div className="mb-4">
      <Segmented
        ariaLabel="What to query"
        options={modes.map((mode) => ({ value: mode.slug, label: mode.name }))}
        value={value}
        onChange={onChange}
      />
      {active ? (
        <div className="mt-1.5">
          <p className="text-[12px] text-ink-2">{active.description}</p>
          {covered ? (
            <EraBadge
              from={covered.from}
              to={covered.to}
              note={
                rowCount != null
                  ? `${rowCount.toLocaleString()} rows loaded · ${active.source}`
                  : active.source
              }
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
