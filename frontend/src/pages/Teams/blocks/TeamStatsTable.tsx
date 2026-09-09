import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import { Chip } from '../../../components/ui/Page'
import { ComputedByUs } from '../../../components/ui/Honesty'
import type { TeamSeason } from '../../../api/endpoints'
import { decimalsFor, num } from '../../../design/format'

type TeamStats = NonNullable<TeamSeason['team_stats']>
type StatRow = TeamStats['rows'][number]

/**
 * Offence produced beside defence allowed, with the rank each figure holds in
 * its season.
 *
 * The allowed side is the honest part: nothing in the team file is "yards
 * allowed", so every allowed figure here is a self-join over the opponents this
 * club actually played. Each row that the payload flags carries the marker and
 * the method rather than passing itself off as a published stat.
 */
export function TeamStatsTable({
  stats,
  abbr,
  season,
}: {
  stats: TeamStats
  abbr: string
  season: number
}) {
  const columns: Column<StatRow>[] = [
    {
      id: 'stat',
      header: 'Stat',
      width: '12rem',
      sortValue: (row) => row.label,
      render: (row) => row.label,
    },
    {
      id: 'offense',
      header: 'Offense',
      align: 'right',
      // Rows are different stats, so ordering by raw value would be nonsense;
      // ordering by rank answers the question the column is actually asked.
      sortValue: (row) => row.offense_rank,
      help: 'What this club produced, with its rank in the league that season. Sorts by rank.',
      // The chip is fixed-width so the numbers above and below each other still
      // line up: a rank that pushes its value left breaks the column.
      render: (row) => (
        <span className="inline-flex items-baseline justify-end whitespace-nowrap">
          {value(row.offense, row.stat)}
          <span className="w-[3.75rem] text-left">
            {row.offense_rank ? <Chip title={`Rank ${row.offense_rank} of ${row.of}`}>{row.offense_rank} of {row.of}</Chip> : null}
          </span>
        </span>
      ),
    },
    {
      id: 'allowed',
      header: 'Allowed',
      align: 'right',
      sortValue: (row) => row.allowed_rank,
      help: 'What this club allowed, summed from its opponents’ own weekly rows. Sorts by rank.',
      render: (row) => (
        <span className="inline-flex items-baseline justify-end whitespace-nowrap">
          {value(row.allowed, row.stat)}
          {row.allowed_computed_by_us ? (
            <ComputedByUs formula={`${row.label} allowed — ${row.allowed_source}`} anchor="team-allowed" />
          ) : null}
          <span className="w-[3.75rem] text-left">
            {row.allowed_rank ? <Chip title={`Rank ${row.allowed_rank} of ${row.of}`}>{row.allowed_rank} of {row.of}</Chip> : null}
          </span>
        </span>
      ),
    },
    {
      id: 'offense_source',
      header: 'Offense source',
      optional: true,
      render: (row) => <span className="text-[11px] text-ink-3">{row.offense_source}</span>,
    },
    {
      id: 'allowed_source',
      header: 'Allowed source',
      optional: true,
      render: (row) => <span className="text-[11px] text-ink-3">{row.allowed_source}</span>,
    },
  ]

  return (
    <DataTable
      rows={stats.rows}
      columns={columns}
      rowKey={(row) => row.stat}
      emptyMessage="No team stat rows were published for this club in this season."
      caption={
        <>
          Ranks are 1 of {stats.league_teams} for the season. {stats.method}
          {stats.allowed_coverage ? ` ${stats.allowed_coverage.note}` : null}
          <ComputedByUs formula={stats.method} anchor="team-allowed" />
        </>
      }
      // The column picker promises that hiding tidies the view without dropping
      // data, so the export writes every column rather than the visible ones.
      onExport={(_visible, sorted) =>
        downloadCsv(`${abbr}-${season}-team-stats.csv`, columns, sorted, (row, column) => CSV[column.id]?.(row) ?? '')
      }
    />
  )
}

/**
 * Decimals come from the shared formatter. Team stat ids the formatter does not
 * recognise fall back to one decimal, which prints "11.0" interceptions — so a
 * whole number on a default-precision stat is written whole. EPA and rate ids
 * are recognised and are unaffected.
 */
function value(input: number | null | undefined, statId: string): string {
  if (input === null || input === undefined) return '—'
  const decimals = decimalsFor(statId)
  return num(input, decimals === 1 && Number.isInteger(input) ? 0 : decimals)
}

const CSV: Record<string, (row: StatRow) => string | number | null | undefined> = {
  stat: (row) => row.label,
  offense: (row) => (row.offense_rank ? `${row.offense} (${row.offense_rank} of ${row.of})` : row.offense),
  allowed: (row) => (row.allowed_rank ? `${row.allowed} (${row.allowed_rank} of ${row.of})` : row.allowed),
  offense_source: (row) => row.offense_source,
  allowed_source: (row) => row.allowed_source,
}
