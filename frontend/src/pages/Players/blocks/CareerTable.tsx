import { Link } from 'react-router-dom'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import { SeasonLink, TeamLink } from '../../../components/ui/EntityLink'
import { num, percent } from '../../../design/format'
import type { PlayerHub } from '../../../api/endpoints'

/**
 * The season-by-season table, for the regular season and — in the same shape —
 * for the postseason.
 *
 * Two things here are not cosmetic. A multi-team season arrives as one row per
 * team *plus* a combined row the payload marks `is_combined`; both are shown,
 * because a reader wants the Denver half and the season total, and inventing
 * either from the other is how a reference site starts disagreeing with itself.
 * And a league-leading cell is bold with a tooltip rather than coloured: hue
 * would be a second encoding of a fact the number already carries, and the
 * design system spends colour only on wins and losses.
 */

type CareerBlock = NonNullable<PlayerHub['career_regular']>
type StatColumn = CareerBlock['columns'][number]

interface View {
  key: string
  season: number | null
  games: number | null
  stats: Record<string, number | null>
  led: string[]
  combined: boolean
  teamLabel: string | null
  teamHref: string | null
  teams: string[] | null
  total: boolean
}

/**
 * A stat's decimals are a property of the stat, so the unit the payload ships
 * decides them — never the component doing the rendering. `null` is a gap and
 * prints as an em dash; it is never quietly turned into a zero.
 */
export function StatValue({
  value,
  unit,
  id,
}: {
  value?: number | null
  unit?: string | null
  id?: string
}) {
  if (value === null || value === undefined) return <span className="text-ink-3">—</span>
  // A "per" stat keeps a decimal even when its unit is a counting one: 6.8 yards
  // per attempt rounded to 7 is a different claim.
  const per = !!id && /_per_|_pct$|_rate$|percentage/.test(id)
  if (unit === 'percent') return <>{percent(value, 1)}</>
  if (unit === 'epa') return <>{num(value, 3)}</>
  return <>{num(value, per ? 1 : 0)}</>
}

export function CareerTable({
  block,
  seasonScope,
  csvName,
}: {
  block: CareerBlock
  /** Regular or postseason, for the export filename and the empty sentence. */
  seasonScope: string
  csvName: string
}) {
  const rows: View[] = block.rows.map((row, index) => ({
    key: `${row.season}-${row.team_label ?? row.team ?? 'combined'}-${index}`,
    season: row.season,
    games: row.games ?? null,
    stats: row.stats ?? {},
    led: row.led_league ?? [],
    combined: row.is_combined,
    teamLabel: row.team_label ?? row.team ?? null,
    teamHref: row.team_href ?? null,
    teams: row.teams ?? null,
    total: false,
  }))

  const total: View = {
    key: 'career-total',
    season: null,
    games: block.total.games ?? null,
    stats: block.total.stats ?? {},
    led: [],
    combined: false,
    teamLabel: `${block.total.seasons} seasons`,
    teamHref: null,
    teams: null,
    total: true,
  }

  const columns: Column<View>[] = [
    {
      id: 'season',
      header: 'Season',
      width: '5.5rem',
      sortValue: (row) => row.season,
      render: (row) =>
        row.total ? (
          <span>{`${block.total.first_season}–${block.total.last_season}`}</span>
        ) : (
          <SeasonLink season={row.season} />
        ),
    },
    {
      id: 'team',
      header: 'Team',
      width: '8rem',
      sortValue: (row) => row.teamLabel,
      render: (row) => <TeamCell row={row} />,
    },
    {
      id: 'games',
      header: 'G',
      help: 'Games with a row in the season stats file.',
      align: 'right',
      sortValue: (row) => row.games,
      render: (row) => <StatValue value={row.games} unit="count" id="games" />,
    },
    ...block.columns.map((column) => statColumn(column)),
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      footRow={total}
      stickyFirstColumn
      emptyMessage={`No ${seasonScope} season on file for this player.`}
      caption={<Notes block={block} />}
      onExport={(visible, sorted) =>
        downloadCsv(`${csvName}.csv`, visible, [...sorted, total], (row, column) =>
          column.id === 'season'
            ? (row.total ? `${block.total.first_season}-${block.total.last_season}` : row.season)
            : column.id === 'team'
              ? (row.teamLabel ?? '')
              : column.id === 'games'
                ? row.games
                : row.stats[column.id],
        )
      }
    />
  )
}

function TeamCell({ row }: { row: View }) {
  if (row.total) return <span className="text-ink-3">{row.teamLabel}</span>
  if (row.combined) {
    return (
      <span title="Both halves of a season split between teams, summed by the source file.">
        {row.teamLabel ?? 'Combined'}
        {row.teams?.length ? (
          <span className="ml-1.5 text-[11px] text-ink-3">
            {row.teams.map((team, index) => (
              <span key={team}>
                {index > 0 ? ', ' : ''}
                <TeamLink abbr={team} season={row.season ?? undefined} />
              </span>
            ))}
          </span>
        ) : null}
      </span>
    )
  }
  if (row.teamHref && row.teamLabel) {
    return <Link to={row.teamHref}>{row.teamLabel}</Link>
  }
  return <TeamLink abbr={row.teamLabel} season={row.season ?? undefined} />
}

function statColumn(column: StatColumn): Column<View> {
  return {
    id: column.id,
    header: column.label,
    help: column.first_season
      ? `${column.label} — not charted before ${column.first_season}; earlier seasons are empty, not zero.`
      : undefined,
    align: 'right',
    sortValue: (row) => row.stats[column.id] ?? null,
    render: (row) => {
      const value = <StatValue value={row.stats[column.id]} unit={column.unit} id={column.id} />
      if (!row.led.includes(column.id)) return value
      return (
        <span className="font-semibold" title={`Led the NFL in ${row.season}`}>
          {value}
        </span>
      )
    },
  }
}

function Notes({ block }: { block: CareerBlock }) {
  // A games-played-only table has no cell that could have led anything.
  const lines = [block.note, block.columns.length ? block.leader_note : null].filter(Boolean)
  if (!lines.length) return null
  return (
    <>
      {lines.map((line) => (
        <span key={line} className="block">
          {line}
        </span>
      ))}
    </>
  )
}
