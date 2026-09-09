import type { Standings } from '../../../api/endpoints'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { TeamLink } from '../../../components/ui/EntityLink'
import { num, record as formatRecord, signed, winPct } from '../../../design/format'

/**
 * One block, two renderings, both driven by whatever the payload's own
 * `groups` say — never by an assumed division count. 2001 hands this six
 * division groups, 2024 hands it eight, and a conference-view payload hands
 * it two; bucketing by each group's own `conference` field and rendering
 * every group we are given is what makes all three payloads correct with the
 * same code.
 *
 * `variant="full"` is the dedicated standings page: every column the spec
 * lists, sortable, with SRS/SOS/Pythagorean wins present but hidden by
 * default in DataTable's own column picker — that picker *is* "behind the
 * column picker" here, not a bespoke toggle.
 *
 * `variant="compact"` is the season hub's embedded summary: a plain table,
 * no per-instance toolbar, because repeating a column-picker/export/density
 * row under eight four-team divisions would be more chrome than content.
 */

export type StandingsGroup = Standings['groups'][number]
export type StandingsTeamRow = StandingsGroup['teams'][number]

const CONFERENCES = ['AFC', 'NFC'] as const

export function StandingsTable({
  groups,
  variant = 'full',
  formulas,
}: {
  groups: StandingsGroup[]
  variant?: 'full' | 'compact'
  /** StandingsPayload.formulas — glossary text for the computed columns. */
  formulas?: Record<string, string>
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {CONFERENCES.map((conference) => {
        const confGroups = groups.filter((group) => group.conference === conference)
        if (!confGroups.length) return null
        return (
          <div key={conference}>
            {confGroups.map((group) => (
              <div key={group.label} className="mb-5 last:mb-0">
                <h3 className="mb-1.5 text-[13px] font-semibold text-ink">{group.label}</h3>
                {variant === 'full' ? (
                  <FullTable teams={group.teams} formulas={formulas} />
                ) : (
                  <CompactTable teams={group.teams} />
                )}
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function seedCell(row: StandingsTeamRow) {
  if (row.seed === null || row.seed === undefined) return <span className="text-ink-3">—</span>
  return (
    <div>
      <span>
        {row.seed}
        {row.projected ? <span className="ml-1 text-[10px] font-normal text-ink-3">proj.</span> : null}
      </span>
      {row.tiebreak_note ? <div className="text-[10px] font-normal leading-tight text-ink-3">{row.tiebreak_note}</div> : null}
    </div>
  )
}

function teamCell(row: StandingsTeamRow) {
  return (
    <TeamLink
      abbr={row.abbr}
      season={row.season}
      className={`no-underline hover:underline ${row.won_division ? 'font-semibold text-ink' : ''}`}
    >
      {row.code_in_season}
    </TeamLink>
  )
}

function FullTable({ teams, formulas }: { teams: StandingsTeamRow[]; formulas?: Record<string, string> }) {
  const columns: Column<StandingsTeamRow>[] = [
    { id: 'team', header: 'Team', sortValue: (r) => r.code_in_season, render: teamCell },
    {
      id: 'record',
      header: 'W-L-T',
      align: 'right',
      sortValue: (r) => r.pct ?? -1,
      render: (r) => formatRecord(r.w, r.l, r.t),
    },
    { id: 'pct', header: 'W-L%', align: 'right', sortValue: (r) => r.pct, render: (r) => winPct(r.pct) },
    { id: 'pf', header: 'PF', align: 'right', sortValue: (r) => r.pf, render: (r) => num(r.pf) },
    { id: 'pa', header: 'PA', align: 'right', sortValue: (r) => r.pa, render: (r) => num(r.pa) },
    { id: 'diff', header: 'Diff', align: 'right', sortValue: (r) => r.diff, render: (r) => signed(r.diff, 0) },
    { id: 'home', header: 'Home', align: 'right', sortValue: (r) => r.home_pct, render: (r) => r.home },
    { id: 'away', header: 'Away', align: 'right', sortValue: (r) => r.away_pct, render: (r) => r.away },
    { id: 'div', header: 'Div', align: 'right', sortValue: (r) => r.div_pct, render: (r) => r.div },
    { id: 'conf', header: 'Conf', align: 'right', sortValue: (r) => r.conf_pct, render: (r) => r.conf },
    {
      id: 'streak',
      header: 'Streak',
      align: 'right',
      sortValue: (r) => r.streak_length ?? 0,
      render: (r) => (
        <span className={r.streak_kind === 'W' ? 'text-positive' : r.streak_kind === 'L' ? 'text-negative' : 'text-ink-2'}>
          {r.streak ?? '—'}
        </span>
      ),
    },
    {
      id: 'seed',
      header: 'Seed',
      align: 'right',
      help: formulas?.playoff_seed,
      sortValue: (r) => r.seed ?? 99,
      render: seedCell,
    },
    {
      id: 'srs',
      header: 'SRS',
      align: 'right',
      optional: true,
      help: formulas?.srs,
      sortValue: (r) => r.srs,
      render: (r) => signed(r.srs, 1),
    },
    {
      id: 'sos',
      header: 'SOS',
      align: 'right',
      optional: true,
      help: formulas?.sos,
      sortValue: (r) => r.sos,
      render: (r) => signed(r.sos, 1),
    },
    {
      id: 'pyth',
      header: 'Pyth. W',
      align: 'right',
      optional: true,
      help: formulas?.pythagorean_wins,
      sortValue: (r) => r.pythagorean_wins,
      render: (r) => num(r.pythagorean_wins, 1),
    },
  ]

  return (
    <DataTable
      rows={teams}
      columns={columns}
      rowKey={(r) => r.abbr}
      emptyMessage="No teams recorded for this group."
    />
  )
}

function CompactTable({ teams }: { teams: StandingsTeamRow[] }) {
  if (!teams.length) return <p className="py-2 text-[12px] text-ink-3">No teams recorded for this group.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[26rem] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line-strong text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2">
            <th className="px-1.5 py-1 text-left">Team</th>
            <th className="px-1.5 py-1 text-right">W-L-T</th>
            <th className="px-1.5 py-1 text-right">PF</th>
            <th className="px-1.5 py-1 text-right">PA</th>
            <th className="px-1.5 py-1 text-right">Diff</th>
            <th className="px-1.5 py-1 text-right">Div</th>
            <th className="px-1.5 py-1 text-right">Conf</th>
            <th className="px-1.5 py-1 text-right">Seed</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((row) => (
            <tr key={row.abbr} className="motion-state border-b border-row-rule hover:bg-row-hover">
              <td className="px-1.5 py-1">{teamCell(row)}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{formatRecord(row.w, row.l, row.t)}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{num(row.pf)}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{num(row.pa)}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{signed(row.diff, 0)}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{row.div}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{row.conf}</td>
              <td className="px-1.5 py-1 text-right tabular-nums">{seedCell(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
