import { Link } from 'react-router-dom'
import { Sparkline } from '../../../components/charts/Sparkline'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import type { TeamSeason } from '../../../api/endpoints'
import { gameDate, num, rate, stat } from '../../../design/format'

type ScheduleRow = NonNullable<TeamSeason['schedule']>[number]

/** Postseason rounds arrive as source codes; a week number alone would hide them. */
const ROUND: Record<string, string> = {
  WC: 'Wild card',
  DIV: 'Divisional',
  CON: 'Conference',
  SB: 'Super Bowl',
}

export function ScheduleTable({
  rows,
  abbr,
  season,
}: {
  rows: ScheduleRow[]
  abbr: string
  season: number
}) {
  const columns: Column<ScheduleRow>[] = [
    {
      id: 'week',
      header: 'Wk',
      width: '4.5rem',
      sortValue: (row) => row.week,
      render: (row) => (
        <span className="whitespace-nowrap">
          <Link to={row.game_href}>{row.week ?? '—'}</Link>
          {row.game_type !== 'REG' ? (
            <span className="ml-1 text-[11px] text-ink-3" title={ROUND[row.game_type] ?? row.game_type}>
              {row.game_type}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      id: 'day',
      header: 'Day',
      sortValue: (row) => row.gameday,
      render: (row) => <span className="text-ink-2">{row.weekday?.slice(0, 3) ?? '—'}</span>,
    },
    {
      id: 'date',
      header: 'Date',
      sortValue: (row) => row.gameday,
      render: (row) => gameDate(row.gameday, { year: false }),
    },
    {
      id: 'opponent',
      header: 'Opponent',
      sortValue: (row) => row.opponent,
      render: (row) => (
        <span className="whitespace-nowrap">
          <span className="mr-1 text-ink-3">{row.home_away === 'home' ? 'vs' : '@'}</span>
          {/* The server's href already resolves a historical code to the club that owns it. */}
          <Link to={row.opponent_href}>{row.opponent_code_in_season}</Link>
        </span>
      ),
    },
    {
      id: 'result',
      header: 'Res',
      sortValue: (row) => row.result,
      render: (row) =>
        row.result === 'W' ? (
          <span className="font-medium text-positive">W</span>
        ) : row.result === 'L' ? (
          <span className="font-medium text-negative">L</span>
        ) : (
          <span className="text-ink-2">{row.result ?? '—'}</span>
        ),
    },
    {
      id: 'score',
      header: 'Score',
      align: 'right',
      sortValue: (row) =>
        row.points_for !== null && row.points_for !== undefined && row.points_against !== null && row.points_against !== undefined
          ? row.points_for - row.points_against
          : null,
      help: 'Final score, this club first.',
      render: (row) =>
        row.points_for === null || row.points_for === undefined ? (
          <span className="text-ink-3">—</span>
        ) : (
          `${num(row.points_for)}–${num(row.points_against)}`
        ),
    },
    {
      id: 'record',
      header: 'Rec',
      align: 'right',
      sortValue: (row) => row.week,
      help: 'Regular-season record through this game. Postseason games do not carry one.',
      render: (row) => row.running_record ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'yards',
      header: 'Yds',
      align: 'right',
      sortValue: (row) => row.yards,
      help: "This club's total yards in the game.",
      render: (row) => num(row.yards),
    },
    {
      id: 'turnovers',
      header: 'TO',
      align: 'right',
      sortValue: (row) => row.turnovers,
      help: 'Turnovers committed by this club.',
      render: (row) => num(row.turnovers),
    },
    {
      id: 'epa',
      header: 'EPA/play',
      align: 'right',
      sortValue: (row) => row.epa_per_play,
      help: 'Expected points added per offensive play, SUM(EPA) / SUM(plays) for the game.',
      render: (row) => stat(row.epa_per_play, 'epa_per_play'),
    },
    {
      id: 'plays',
      header: 'Plays',
      align: 'right',
      optional: true,
      sortValue: (row) => row.plays,
      render: (row) => num(row.plays),
    },
    {
      id: 'first_downs',
      header: '1st D',
      align: 'right',
      optional: true,
      sortValue: (row) => row.first_downs,
      render: (row) => num(row.first_downs),
    },
    {
      id: 'success_rate',
      header: 'Succ%',
      align: 'right',
      optional: true,
      sortValue: (row) => row.success_rate,
      help: 'Share of plays with positive expected-points added.',
      render: (row) => rate(row.success_rate),
    },
    {
      id: 'wp',
      header: 'Win prob.',
      width: '4rem',
      help: 'Win probability through the game, from the play-by-play. Click for the full game.',
      render: (row) => {
        const points = row.wp_sparkline ?? []
        if (!points.length) return <span className="text-ink-3">—</span>
        return (
          <Link
            to={row.game_href}
            aria-label={`Win probability chart for ${row.opponent_code_in_season}`}
            className="inline-block no-underline"
          >
            <Sparkline
              values={points.map((point) => point[1])}
              title={`Win probability, ${row.wp_sparkline_side ?? ''} — ${row.wp_sparkline_points ?? points.length} points`}
            />
          </Link>
        )
      },
    },
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.game_id}
      initialSort={{ id: 'week', desc: false }}
      emptyMessage="No games are on file for this club in this season."
      caption="Every row is a game — the sparkline is that game's win probability, and the whole row links to it."
      // Hidden columns stay in the export: the picker tidies the view, it does
      // not drop data.
      onExport={(_visible, sorted) =>
        downloadCsv(`${abbr}-${season}-schedule.csv`, columns, sorted, (row, column) => CSV[column.id]?.(row) ?? '')
      }
    />
  )
}

/** Exports carry the raw value, not the rendered markup. */
const CSV: Record<string, (row: ScheduleRow) => string | number | null | undefined> = {
  week: (row) => row.week,
  day: (row) => row.weekday,
  date: (row) => row.gameday,
  opponent: (row) => `${row.home_away === 'home' ? 'vs ' : '@ '}${row.opponent_code_in_season}`,
  result: (row) => row.result,
  score: (row) =>
    row.points_for === null || row.points_for === undefined ? '' : `${row.points_for}-${row.points_against}`,
  record: (row) => row.running_record,
  yards: (row) => row.yards,
  turnovers: (row) => row.turnovers,
  epa: (row) => row.epa_per_play,
  plays: (row) => row.plays,
  first_downs: (row) => row.first_downs,
  success_rate: (row) => row.success_rate,
  wp: (row) => row.game_id,
}
