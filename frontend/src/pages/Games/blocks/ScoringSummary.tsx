import { Link } from 'react-router-dom'
import type { Game } from '../../../api/endpoints'
import { DriveChart } from '../../../components/charts/DriveChart'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import { TeamLink } from '../../../components/ui/EntityLink'
import { num, plural } from '../../../design/format'

type ScoringPlay = NonNullable<Game['scoring']>[number]
type DriveRow = NonNullable<Game['drives']>[number]

/**
 * Every score in the game, in the order they happened.
 *
 * The rows carry `scoring-play-{id}` rather than the payload's own
 * `play-{id}` anchor: the play log below uses that anchor, and two elements
 * cannot share a DOM id. The scoring row is still linkable; it just does not
 * steal the log's fragment.
 */
export function ScoringSummary({ plays, data }: { plays: ScoringPlay[]; data: Game }) {
  const away = data.header.away
  const home = data.header.home

  const columns: Column<ScoringPlay>[] = [
    {
      id: 'quarter',
      header: 'Q',
      width: '3rem',
      sortValue: (row) => -(row.seconds_remaining ?? 0),
      render: (row) => row.period_label,
    },
    {
      id: 'clock',
      header: 'Clock',
      width: '4.5rem',
      sortValue: (row) => -(row.seconds_remaining ?? 0),
      render: (row) => row.clock ?? '—',
    },
    {
      id: 'team',
      header: 'Team',
      width: '4.5rem',
      sortValue: (row) => row.team,
      render: (row) => <TeamLink abbr={row.team} season={data.season} />,
    },
    {
      id: 'scorer',
      header: 'Scorer',
      width: '9rem',
      sortValue: (row) => row.scorer,
      render: (row) =>
        row.scorer_href && row.scorer ? (
          <Link to={row.scorer_href}>{row.scorer}</Link>
        ) : (
          (row.scorer ?? <span className="text-ink-3">—</span>)
        ),
    },
    {
      id: 'description',
      header: 'Play',
      render: (row) => <span className="text-ink-2">{row.description ?? '—'}</span>,
    },
    {
      id: 'score',
      header: `${away.abbr ?? 'Away'}–${home.abbr ?? 'Home'}`,
      align: 'right',
      width: '5.5rem',
      render: (row) => `${num(row.away_score, 0)}–${num(row.home_score, 0)}`,
    },
  ]

  return (
    <DataTable
      rows={plays}
      columns={columns}
      rowKey={(row, index) => String(row.play_id ?? index)}
      rowId={(row) => (row.play_id ? `scoring-play-${row.play_id}` : undefined)}
      emptyMessage="No points were scored in this game."
      caption="Running score after each scoring play, away first."
      onExport={(visible, sorted) =>
        downloadCsv(`${data.game_id}-scoring.csv`, visible, sorted, (row, column) => scoringCell(row, column.id))
      }
    />
  )
}

function scoringCell(row: ScoringPlay, id: string): string | number | null | undefined {
  switch (id) {
    case 'quarter':
      return row.period_label
    case 'clock':
      return row.clock
    case 'team':
      return row.team
    case 'scorer':
      return row.scorer
    case 'description':
      return row.description
    case 'score':
      return `${row.away_score ?? ''}-${row.home_score ?? ''}`
    default:
      return null
  }
}

/**
 * The drive chart, and the page's first filter into the play log.
 *
 * Clicking a drive writes `?drive=N` and opens the log below, which is how a
 * visitor who came for the score discovers there is play-level data at all
 * without being shown two hundred rows first.
 */
export function DriveBlock({
  drives,
  data,
  selected,
  onSelect,
}: {
  drives: DriveRow[]
  data: Game
  selected: number | null
  onSelect: (drive: number | null) => void
}) {
  const away = data.header.away.abbr ?? 'Away'
  const home = data.header.home.abbr ?? 'Home'

  // The chart's own shape names the offence `posteam`; the game payload calls it
  // `team`. A drive with no number cannot be selected, so it is not offered.
  const usable = drives.flatMap((drive) =>
    drive.drive === null || drive.drive === undefined
      ? []
      : [
          {
            drive: drive.drive,
            posteam: drive.team ?? '—',
            plays: drive.plays ?? null,
            result: drive.result ?? null,
            scored: drive.scored ?? null,
            start_yardline_100: drive.start_yardline_100 ?? null,
            end_yardline_100: drive.end_yardline_100 ?? null,
            time_of_possession: drive.time_of_possession ?? null,
          },
        ],
  )

  const current = drives.find((drive) => drive.drive === selected)

  return (
    <div>
      <DriveChart drives={usable} homeTeam={home} awayTeam={away} selected={selected} onSelect={onSelect} />
      <p className="mt-2 text-[12px] leading-5 text-ink-2">
        {current ? (
          <>
            {`Drive ${current.drive}: ${[
              current.team,
              current.plays === null || current.plays === undefined ? null : plural(current.plays, 'play'),
              current.net_yards === null || current.net_yards === undefined ? null : `${num(current.net_yards, 0)} yards`,
              current.time_of_possession,
              current.start_yard_line ? `from ${current.start_yard_line}` : null,
              current.result,
            ]
              .filter(Boolean)
              .join(' · ')}. `}
            <button type="button" onClick={() => onSelect(null)} className="motion-state underline hover:text-accent">
              Show every play again
            </button>
          </>
        ) : (
          'Select a drive to narrow the play log below to it.'
        )}
      </p>
    </div>
  )
}
