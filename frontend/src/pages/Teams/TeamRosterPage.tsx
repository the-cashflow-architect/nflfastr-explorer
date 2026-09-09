import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useTeamRoster, type TeamRoster } from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { CollegeLink, PlayerLink, TeamLink } from '../../components/ui/EntityLink'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { decimalsFor, height as formatHeight, num, plural, rate } from '../../design/format'
import { TeamHeader } from './blocks/TeamHeader'

type Row = TeamRoster['rows'][number]

const GROUP_LABEL: Record<string, string> = {
  offense: 'Offense',
  defense: 'Defense',
  special_teams: 'Special teams',
  unclassified: 'Unclassified',
  all: 'All',
}

/**
 * The roster, sorted the way a depth chart would be if we shipped one: by how
 * much of the season each player was actually on the field.
 *
 * The rule that matters here is what happens to a player whose snap record we
 * could not match. He is not ranked last — being unmatched is not the same as
 * never playing — so the snap order excludes him and lists him separately with
 * the reason.
 */
export function TeamRosterPage() {
  const { abbr = '', season = '' } = useParams()
  const parsed = Number(season)
  const query = useTeamRoster(abbr, Number.isFinite(parsed) && parsed > 0 ? parsed : undefined)
  const data = query.data
  useCrumbLabel(`/teams/${abbr}`, data?.team.name)

  return (
    <>
      {data ? null : <PageHeader title={`${season} ${abbr.toUpperCase()} roster`} meta="Team-season roster" />}
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {data ? <RosterBody data={data} /> : null}
      </QueryBoundary>
    </>
  )
}

function RosterBody({ data }: { data: TeamRoster }) {
  const [params, setParams] = useSearchParams()
  const snaps = data.coverage.snaps_available
  const groupParam = params.get('group')
  const group = groupParam && data.position_groups.includes(groupParam) ? groupParam : 'all'
  const sortParam = params.get('sort')
  const sort =
    sortParam === 'number' || sortParam === 'name' || (sortParam === 'snaps' && snaps) ? sortParam : snaps ? 'snaps' : 'number'

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const inGroup = useMemo(
    () => (group === 'all' ? data.rows : data.rows.filter((row) => row.position_group === group)),
    [data.rows, group],
  )
  // A player with no matched snap row is held out of the snap order rather than
  // sunk to the bottom of it, which would read as "played the fewest snaps".
  const ranked = useMemo(() => (sort === 'snaps' ? inGroup.filter((row) => !row.snap_note) : inGroup), [inGroup, sort])
  const unranked = useMemo(() => (sort === 'snaps' ? inGroup.filter((row) => row.snap_note) : []), [inGroup, sort])

  const ordered = useMemo(() => {
    const rows = [...ranked]
    if (sort === 'name') return rows.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''))
    if (sort === 'number') return rows.sort((a, b) => (a.number ?? 9999) - (b.number ?? 9999))
    // The payload's snap_rank ranks on offensive share alone, which puts every
    // defender in a 0.0 tie. Inside a position group the share that matters is
    // that group's own side; on the All tab it is whichever side the player
    // actually played.
    return rows.sort((a, b) => shareIn(b, group) - shareIn(a, group))
  }, [ranked, sort, group])

  const anyInjury = useMemo(() => data.rows.some((row) => row.injury_status), [data.rows])
  const columns = useMemo(
    () => buildColumns({ snaps, injuries: anyInjury, note: data.coverage.note, group }),
    [snaps, anyInjury, data.coverage.note, group],
  )

  const title = data.label ?? `${data.season} ${data.team.name ?? data.team.abbr}`

  return (
    <>
      <TeamHeader
        team={data.team}
        title={`${title} roster`}
        meta={[
          plural(data.counts.all ?? data.rows.length, 'player'),
          ...data.position_groups
            .filter((key) => key !== 'all' && data.counts[key])
            .map((key) => `${GROUP_LABEL[key] ?? key} ${data.counts[key]}`),
        ].join(' · ')}
        subnav={
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              ariaLabel="Position group"
              value={group}
              onChange={(value) => setParam('group', value)}
              options={data.position_groups.map((key) => ({
                value: key,
                label: data.counts[key] ? `${GROUP_LABEL[key] ?? key} ${data.counts[key]}` : (GROUP_LABEL[key] ?? key),
              }))}
            />
            <Segmented
              ariaLabel="Sort"
              value={sort}
              onChange={(value) => setParam('sort', value)}
              options={[
                ...(snaps ? [{ value: 'snaps', label: 'Snap share' }] : []),
                { value: 'number', label: 'Number' },
                { value: 'name', label: 'Name' },
              ]}
            />
          </div>
        }
      />

      {snaps ? (
        <EraBadge from={data.coverage.snaps_from} note="snap counts" className="mb-3" />
      ) : (
        <p className="mb-3 text-[11px] leading-4 text-ink-3">
          Snap counts start in {data.coverage.snaps_from}, so the snap columns are not shown for {data.season}.
        </p>
      )}

      <DataTable
        // A fresh table per tab: the column picker's defaults differ by group,
        // and its hidden set is seeded once per mount.
        key={group}
        rows={ordered}
        columns={columns}
        rowKey={(row, index) => row.gsis_id ?? `${row.name ?? 'unknown'}-${index}`}
        emptyMessage={`No ${group === 'all' ? '' : `${(GROUP_LABEL[group] ?? group).toLowerCase()} `}players are on file for this club in ${data.season}.`}
        caption={
          <>
            {sort === 'snaps'
              ? 'Ordered by snap share, which is the control above the table rather than a sortable header: a player with no matched snap row is held out of that order rather than ranked last.'
              : `Ordered by ${sort}.`}{' '}
            Age is our own computation from birth date
            <ComputedByUs formula="Age in whole years at the start of the season, from the player's birth date." anchor="roster-age" />
            {snaps ? (
              <>
                {' '}
                {data.coverage.note}
                <ComputedByUs formula={data.coverage.note} anchor="snap-share" />
              </>
            ) : null}
          </>
        }
        onExport={(_visible, sorted) =>
          downloadCsv(
            `${data.team.abbr}-${data.season}-roster.csv`,
            columns,
            sorted,
            (row, column) => CSV[column.id]?.(row) ?? '',
          )
        }
      />

      {unranked.length ? (
        <div className="mt-6">
          <Section title="No snap record" note={plural(unranked.length, 'player')}>
            <p className="mb-2 text-[11px] leading-4 text-ink-3">
              {unranked[0].snap_note} They are listed here rather than at the bottom of the snap order.
            </p>
            <DataTable
              rows={[...unranked].sort((a, b) => (a.number ?? 9999) - (b.number ?? 9999))}
              columns={columns.filter((column) => !column.id.startsWith('snap_'))}
              rowKey={(row, index) => row.gsis_id ?? `${row.name ?? 'unknown'}-unmatched-${index}`}
              emptyMessage="Every player on this roster matched a snap-count row."
            />
          </Section>
        </div>
      ) : null}
    </>
  )
}

function buildColumns({
  snaps,
  injuries,
  note,
  group,
}: {
  snaps: boolean
  injuries: boolean
  note: string
  group: string
}): Column<Row>[] {
  const columns: Column<Row>[] = [
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.name,
      render: (row) => (
        <span className="whitespace-nowrap">
          <span className="mr-1.5 text-[11px] text-ink-3">{row.number ?? '—'}</span>
          <PlayerLink id={row.gsis_id} name={row.name} />
        </span>
      ),
    },
    { id: 'position', header: 'Pos', sortValue: (row) => row.position, render: (row) => row.position ?? '—' },
    {
      id: 'depth',
      header: 'Depth',
      optional: true,
      sortValue: (row) => row.depth_chart_position,
      help: 'Depth-chart position as the roster file lists it.',
      render: (row) => row.depth_chart_position ?? '—',
    },
    { id: 'age', header: 'Age', align: 'right', sortValue: (row) => row.age, render: (row) => num(row.age) },
    {
      id: 'height',
      header: 'Ht',
      align: 'right',
      optional: true,
      sortValue: (row) => row.height,
      render: (row) => formatHeight(row.height),
    },
    {
      id: 'weight',
      header: 'Wt',
      align: 'right',
      optional: true,
      sortValue: (row) => row.weight,
      render: (row) => num(row.weight),
    },
    {
      id: 'college',
      header: 'College',
      sortValue: (row) => row.college,
      render: (row) => <CollegeLink college={row.college} />,
    },
    {
      id: 'entry',
      header: 'Entry',
      align: 'right',
      sortValue: (row) => row.entry_year,
      help: 'First season in the league, as the roster file records it.',
      // A year is not a quantity: it never carries a thousands separator.
      render: (row) => row.entry_year ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'draft',
      header: 'Drafted by',
      sortValue: (row) => row.draft_club,
      help: 'The club that drafted him, and his overall pick. Undrafted players carry neither.',
      render: (row) =>
        row.draft_club ? (
          <span className="whitespace-nowrap">
            <TeamLink abbr={row.draft_club} />
            {row.draft_number ? <span className="ml-1.5 text-[11px] text-ink-3">#{row.draft_number}</span> : null}
          </span>
        ) : (
          <span className="text-ink-3">Undrafted</span>
        ),
    },
    {
      id: 'games',
      header: 'G',
      align: 'right',
      sortValue: (row) => row.stat_line?.games ?? null,
      help: 'Games with a statistical row this season.',
      render: (row) => num(row.stat_line?.games),
    },
  ]

  if (snaps) {
    columns.push(
      {
        id: 'snap_off',
        header: 'Off%',
        align: 'right',
        // A column of zeroes on the defensive tab is noise, so it starts hidden
        // there — still in the picker, still in the export.
        optional: group === 'defense' || group === 'special_teams',
        sortValue: (row) => row.offense_share,
        help: note,
        render: (row) => share(row.offense_share, row.snap_note),
      },
      {
        id: 'snap_def',
        header: 'Def%',
        align: 'right',
        optional: group === 'offense' || group === 'special_teams',
        sortValue: (row) => row.defense_share,
        help: note,
        render: (row) => share(row.defense_share, row.snap_note),
      },
      {
        id: 'snap_st',
        header: 'ST%',
        align: 'right',
        sortValue: (row) => row.st_share,
        help: note,
        render: (row) => share(row.st_share, row.snap_note),
      },
      {
        id: 'snap_off_count',
        header: 'Off snaps',
        align: 'right',
        optional: true,
        sortValue: (row) => row.offense_snaps,
        render: (row) => num(row.offense_snaps),
      },
      {
        id: 'snap_def_count',
        header: 'Def snaps',
        align: 'right',
        optional: true,
        sortValue: (row) => row.defense_snaps,
        render: (row) => num(row.defense_snaps),
      },
      {
        id: 'snap_st_count',
        header: 'ST snaps',
        align: 'right',
        optional: true,
        sortValue: (row) => row.st_snaps,
        render: (row) => num(row.st_snaps),
      },
    )
  }

  columns.push({
    id: 'line',
    header: 'Season line',
    width: '14rem',
    help: 'The headline stats this player recorded for this club in this season.',
    render: (row) => statLine(row),
  })

  if (injuries) {
    columns.push({
      id: 'injury',
      header: 'Designation',
      sortValue: (row) => row.injury_status,
      help: 'The most recent weekly game-status designation on file.',
      render: (row) => row.injury_status ?? <span className="text-ink-3">—</span>,
    })
  }

  columns.push({
    id: 'status',
    header: 'Status',
    optional: true,
    sortValue: (row) => row.status,
    help: 'Roster status code as the source records it: ACT, RES, CUT, DEV, INA.',
    render: (row) => row.status ?? '—',
  })

  return columns
}

function shareIn(row: Row, group: string): number {
  if (group === 'offense') return row.offense_share ?? 0
  if (group === 'defense') return row.defense_share ?? 0
  if (group === 'special_teams') return row.st_share ?? 0
  return Math.max(row.offense_share ?? 0, row.defense_share ?? 0, row.st_share ?? 0)
}

/** A share we could not match is an em dash carrying the reason, never a zero. */
function share(value: number | null | undefined, note: string | null | undefined): React.ReactNode {
  if (value === null || value === undefined) {
    return (
      <span className="text-ink-3" title={note ?? undefined}>
        —
      </span>
    )
  }
  return rate(value)
}

const DEFENSIVE: readonly string[] = ['def_sacks', 'def_interceptions', 'def_tackles_solo']
const OFFENSIVE: readonly string[] = ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions']
const SHORT: Record<string, string> = {
  def_sacks: 'sk',
  def_interceptions: 'int',
  def_tackles_solo: 'tkl',
  passing_yards: 'pass yds',
  rushing_yards: 'rush yds',
  receiving_yards: 'rec yds',
  receptions: 'rec',
}

function statLine(row: Row): React.ReactNode {
  const line = row.stat_line
  if (!line) {
    return (
      <span className="text-ink-3" title="No season stat row for this player with this club.">
        —
      </span>
    )
  }
  const keys = row.position_group === 'defense' ? DEFENSIVE : OFFENSIVE
  const parts = keys
    .filter((key) => line[key])
    .sort((a, b) => (line[b] ?? 0) - (line[a] ?? 0))
    .slice(0, 3)
    .map((key) => `${value(line[key], key)} ${SHORT[key] ?? key}`)
  if (!parts.length) return <span className="text-ink-3">None recorded</span>
  return <span className="truncate">{parts.join(' · ')}</span>
}

const CSV: Record<string, (row: Row) => string | number | null | undefined> = {
  player: (row) => `${row.number ?? ''} ${row.name ?? ''}`.trim(),
  position: (row) => row.position,
  depth: (row) => row.depth_chart_position,
  age: (row) => row.age,
  height: (row) => row.height,
  weight: (row) => row.weight,
  college: (row) => row.college,
  entry: (row) => row.entry_year,
  draft: (row) => (row.draft_club ? `${row.draft_club}${row.draft_number ? ` #${row.draft_number}` : ''}` : 'Undrafted'),
  games: (row) => row.stat_line?.games,
  snap_off: (row) => row.offense_share,
  snap_def: (row) => row.defense_share,
  snap_st: (row) => row.st_share,
  snap_off_count: (row) => row.offense_snaps,
  snap_def_count: (row) => row.defense_snaps,
  snap_st_count: (row) => row.st_snaps,
  injury: (row) => row.injury_status,
  status: (row) => row.status,
  line: (row) => {
    const keys = row.position_group === 'defense' ? DEFENSIVE : OFFENSIVE
    return row.stat_line ? keys.map((key) => `${key}=${row.stat_line?.[key] ?? ''}`).join(' ') : ''
  },
}

/**
 * Decimals come from the shared formatter; ids it does not recognise fall back
 * to one decimal, which would print "97.0" receptions. A whole number on a
 * default-precision stat is written whole, and a half-sack keeps its half.
 */
function value(input: number | null | undefined, statId: string): string {
  if (input === null || input === undefined) return '—'
  const decimals = decimalsFor(statId)
  return num(input, decimals === 1 && Number.isInteger(input) ? 0 : decimals)
}
