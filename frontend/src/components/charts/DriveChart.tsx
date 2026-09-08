import { chartColors } from './primitives'

/**
 * Every drive of a game as a bar on the field, in order.
 *
 * The x-axis is field position, not time, because that is the question a drive
 * chart answers: where did each possession start, how far did it get, and what
 * did it end in. Reading that off a table of yard lines is work; reading it off
 * a field is instant.
 *
 * Result is carried by the end cap — a small mark using the two semantic
 * colours, scoring against not — rather than by colouring whole bars, which
 * would turn twenty drives into a stripe pattern and lose the field entirely.
 */

export interface Drive {
  drive: number
  posteam: string
  plays: number | null
  result: string | null
  scored: boolean | null
  start_yardline_100: number | null
  end_yardline_100: number | null
  time_of_possession: string | null
}

export function DriveChart({
  drives,
  homeTeam,
  awayTeam,
  selected,
  onSelect,
}: {
  drives: Drive[]
  homeTeam: string
  awayTeam: string
  selected?: number | null
  onSelect?: (drive: number | null) => void
}) {
  const colors = chartColors()
  const usable = drives.filter((d) => d.start_yardline_100 != null && d.end_yardline_100 != null)

  if (!usable.length) {
    return <p className="py-4 text-[13px] text-ink-3">No drive data for this game.</p>
  }

  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px] text-ink-3">
        <span>Own goal line</span>
        <span>Midfield</span>
        <span>Opponent goal line</span>
      </div>
      <ol className="space-y-px">
        {usable.map((drive) => {
          // yardline_100 counts down toward the opponent's goal, so the bar runs
          // left-to-right as the offence advances.
          const start = 100 - (drive.start_yardline_100 as number)
          const end = 100 - (drive.end_yardline_100 as number)
          const left = Math.min(start, end)
          const width = Math.max(1, Math.abs(end - start))
          const isSelected = selected === drive.drive
          return (
            <li key={drive.drive}>
              <button
                type="button"
                onClick={() => onSelect?.(isSelected ? null : drive.drive)}
                aria-pressed={isSelected}
                title={`${drive.posteam} · ${drive.plays ?? '—'} plays · ${drive.result ?? 'unknown'}`}
                className={`motion-state grid w-full grid-cols-[3.5rem_1fr_5.5rem] items-center gap-2 rounded px-1 py-0.5 text-left hover:bg-row-hover ${
                  isSelected ? 'bg-row-hover' : ''
                }`}
              >
                <span className="text-[11px] text-ink-2">{drive.posteam}</span>
                <span className="relative block h-3 rounded-sm bg-track">
                  {/* Midfield, so the eye can judge field position without a ruler. */}
                  <span className="absolute inset-y-[-2px] left-1/2 w-px bg-line" aria-hidden />
                  <span
                    className="absolute inset-y-0 rounded-sm"
                    style={{ left: `${left}%`, width: `${width}%`, background: colors.ink3 }}
                  />
                  <span
                    className="absolute inset-y-[-1px] w-[3px] rounded-sm"
                    style={{
                      left: `calc(${end}% - 1px)`,
                      background: drive.scored ? colors.positive : colors.negative,
                    }}
                  />
                </span>
                <span className="truncate text-right text-[11px] text-ink-3">{drive.result ?? '—'}</span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="mt-1.5 text-[11px] text-ink-3">
        Bars run in the direction each offence was attacking. {homeTeam} and {awayTeam} drives are
        interleaved in game order.
      </p>
    </div>
  )
}
