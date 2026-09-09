import { Users } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useTeamSeason, type TeamSeason } from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { PlayerLink } from '../../components/ui/EntityLink'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { PageHeader, PrimaryAction, Section, Tile, TileRow } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { decimalsFor, num, ordinal, plural, rate, record as formatRecord, signed, stat, winPct } from '../../design/format'
import { ScheduleTable } from './blocks/ScheduleTable'
import { TeamStatsTable } from './blocks/TeamStatsTable'
import { TeamHeader } from './blocks/TeamHeader'

type Rating = NonNullable<TeamSeason['ratings']>[number]
type DriveSide = NonNullable<NonNullable<TeamSeason['drive_profile']>['team']>
type DriveRow = NonNullable<TeamSeason['drive_log']>[number]
type InjuryRow = NonNullable<NonNullable<TeamSeason['injuries']>['rows']>[number]

/**
 * The cockpit for one team-season, and the busiest page in the product.
 *
 * Every block here is optional in the payload and every one of them is removed
 * rather than shown empty: a 2004 season has no snap counts, a 2003 season has
 * no injuries, and a page that renders their headers with dashes underneath is
 * claiming we looked and found nothing.
 */
export function TeamSeasonPage() {
  const { abbr = '', season = '' } = useParams()
  const parsed = Number(season)
  const query = useTeamSeason(abbr, Number.isFinite(parsed) && parsed > 0 ? parsed : undefined)
  const data = query.data
  useCrumbLabel(`/teams/${abbr}`, data?.team.name)
  useAnchorScroll(!!data)

  return (
    <>
      {data ? null : <PageHeader title={`${season} ${abbr.toUpperCase()}`} meta="Team season" />}
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {data ? <TeamSeasonBody data={data} abbr={abbr} /> : null}
      </QueryBoundary>
    </>
  )
}

function TeamSeasonBody({ data, abbr }: { data: TeamSeason; abbr: string }) {
  const { team, record, ratings, schedule, team_stats, drive_profile, drive_log, roster_leaders, special_teams, injuries } =
    data
  const pageKey = `team-season:${team.abbr}`

  const meta = [
    record && record.w !== null && record.w !== undefined
      ? `${formatRecord(record.w, record.l ?? 0, record.t ?? 0)} · ${winPct(record.pct)}`
      : null,
    data.division_finish ? `${ordinal(data.division_finish)} in the ${data.division_label}` : data.division_label,
    data.coaches?.length ? data.coaches.join(', ') : data.coach,
    data.playoff_result,
    data.season_completed ? null : 'Season in progress',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <TeamHeader
        team={team}
        title={data.label ?? `${data.season} ${team.name ?? team.abbr}`}
        meta={meta}
        prev={data.prev_season ? { to: `/teams/${team.abbr}/${data.prev_season}`, label: `${data.prev_season} season` } : undefined}
        next={data.next_season ? { to: `/teams/${team.abbr}/${data.next_season}`, label: `${data.next_season} season` } : undefined}
        action={
          <PrimaryAction to={data.roster_href}>
            <Users className="h-4 w-4" />
            Full roster
          </PrimaryAction>
        }
      />

      {ratings?.length ? <RatingTiles ratings={ratings} /> : null}

      {schedule?.length ? (
        <div id="schedule">
          <Section title="Schedule & results" note={plural(schedule.length, 'game')}>
            <ScheduleTable rows={schedule} abbr={team.abbr} season={data.season} />
          </Section>
        </div>
      ) : null}

      {team_stats?.rows.length ? (
        <div id="team-stats">
          <Section title="Team stats vs opponents" note="Produced beside allowed">
            <TeamStatsTable stats={team_stats} abbr={team.abbr} season={data.season} />
          </Section>
        </div>
      ) : null}

      {drive_profile && (drive_profile.team || drive_profile.opponent) ? (
        <div id="drives">
          <Section title="Drive profile" note={drive_profile.regular_season_only ? 'Regular season only' : undefined}>
            <div className="grid gap-5 sm:grid-cols-2">
              {drive_profile.team ? <DriveSidePanel title={team.name ?? team.abbr} side={drive_profile.team} /> : null}
              {drive_profile.opponent ? <DriveSidePanel title="Opponents" side={drive_profile.opponent} /> : null}
            </div>
            <p className="mt-2 text-[11px] leading-4 text-ink-3">
              {drive_profile.method}
              <ComputedByUs formula={drive_profile.method} anchor="drives" />
            </p>
          </Section>
        </div>
      ) : null}

      {roster_leaders && (roster_leaders.by_snap_share?.length || roster_leaders.by_stat?.length) ? (
        <div id="roster-leaders">
          <Section title="Roster leaders" note="Snap-share leaders and the leader in each headline stat">
            <div className="grid gap-5 sm:grid-cols-2">
              {roster_leaders.by_snap_share?.length ? (
                <div>
                  <h3 className="text-[13px] font-medium">
                    Snap-share leaders
                    <ComputedByUs
                      formula={roster_leaders.snap_share_coverage?.note ?? 'Snap share is player snaps over team snaps.'}
                      anchor="snap-share"
                    />
                  </h3>
                  {roster_leaders.snap_share_coverage ? (
                    <EraBadge from={roster_leaders.snap_share_coverage.first_season} note="snap counts" />
                  ) : null}
                  <ul className="mt-1.5">
                    {roster_leaders.by_snap_share.slice(0, 5).map((leader) => (
                      <li
                        key={leader.pfr_id}
                        className="flex items-baseline gap-2 border-b border-row-rule py-1 last:border-b-0"
                      >
                        {/* Snap rows carry a PFR id and no gsis id, so these names
                            are text rather than links that would 404. */}
                        <span className="min-w-0 flex-1 truncate text-[13px]">{leader.player ?? '—'}</span>
                        <span className="shrink-0 text-[11px] text-ink-3">{plural(leader.games, 'game')}</span>
                        <span className="shrink-0 text-[12px]">{shareLine(leader)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {roster_leaders.by_stat?.length ? (
                <div>
                  <h3 className="text-[13px] font-medium">Statistical leaders</h3>
                  <ul className="mt-1.5">
                    {roster_leaders.by_stat.map((leader) => (
                      <li
                        key={leader.stat}
                        className="flex items-baseline gap-2 border-b border-row-rule py-1 last:border-b-0"
                      >
                        <span className="w-32 shrink-0 truncate text-[11px] text-ink-3">{leader.label}</span>
                        <span className="min-w-0 flex-1 truncate text-[13px]">
                          <PlayerLink id={leader.gsis_id} name={leader.player} />
                          {leader.position ? <span className="ml-1.5 text-[11px] text-ink-3">{leader.position}</span> : null}
                        </span>
                        <span className="shrink-0 text-[13px]">{value(leader.value, leader.stat)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </Section>
        </div>
      ) : null}

      {special_teams?.rows.length ? (
        <div id="special-teams">
          <Section
            title="Special teams"
            collapsible
            defaultCollapsed
            pageKey={pageKey}
            sectionKey="special-teams"
            count={plural(special_teams.rows.length, 'measure')}
          >
            <ul className="grid max-w-[48rem] gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
              {special_teams.rows.map((row) => (
                <li key={row.stat} className="flex items-baseline justify-between gap-2 border-b border-row-rule py-1">
                  <span className="text-[12px] text-ink-2">{row.label}</span>
                  <span className="text-[13px]">{value(row.value, row.stat)}</span>
                </li>
              ))}
            </ul>
            {special_teams.not_available.length ? (
              <ul className="mt-2 space-y-0.5">
                {special_teams.not_available.map((reason) => (
                  <li key={reason} className="text-[11px] leading-4 text-ink-3">
                    {reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </Section>
        </div>
      ) : null}

      {injuries?.rows?.length ? (
        <div id="injuries">
          <Section
            title="Injury summary"
            collapsible
            defaultCollapsed
            pageKey={pageKey}
            sectionKey="injuries"
            count={plural(injuries.rows.length, 'player')}
          >
            <InjuryTable rows={injuries.rows} note={injuries.coverage.note} from={injuries.coverage.first_season} abbr={abbr} season={data.season} />
          </Section>
        </div>
      ) : null}

      {drive_log?.length ? (
        <div id="drive-log">
          <Section
            title="Full drive log"
            collapsible
            defaultCollapsed
            pageKey={pageKey}
            sectionKey="drive-log"
            count={plural(drive_log.length, 'drive')}
          >
            <DriveLogTable rows={drive_log} abbr={abbr} season={data.season} />
          </Section>
        </div>
      ) : null}
    </>
  )
}

/**
 * Four tiles, no colour, each with its 1-of-32 rank as context. The rank is a
 * number, never a hue, and the two we solve for carry their formula.
 */
function RatingTiles({ ratings }: { ratings: Rating[] }) {
  const byId = new Map(ratings.map((rating) => [rating.id, rating]))
  const offense = byId.get('offense_epa_per_play')
  const defense = byId.get('defense_epa_per_play')
  const pointsFor = byId.get('pf')
  const pointsAgainst = byId.get('pa')
  const srs = byId.get('srs')
  const pythagorean = byId.get('pythagorean_wins')

  const tiles: React.ReactNode[] = []

  for (const rating of [offense, defense]) {
    if (!rating) continue
    tiles.push(
      <Tile
        key={rating.id}
        label={rating.label}
        value={
          <>
            {stat(rating.value, 'epa_per_play')}
            {rating.computed_by_us && rating.formula ? <ComputedByUs formula={rating.formula} anchor="epa" /> : null}
          </>
        }
        context={rankLine(rating)}
      />,
    )
  }

  if (pointsFor && pointsAgainst) {
    tiles.push(
      <Tile
        key="points"
        label="Points for / against"
        value={
          <>
            {num(pointsFor.value)} / {num(pointsAgainst.value)}
            {pointsAgainst.formula ? <ComputedByUs formula={pointsAgainst.formula} anchor="points-allowed" /> : null}
          </>
        }
        context={`${rankLine(pointsFor)} scoring · ${rankLine(pointsAgainst)} allowed`}
      />,
    )
  }

  if (srs) {
    tiles.push(
      <Tile
        key="srs"
        label={srs.label}
        value={
          <>
            {signed(srs.value, 1)}
            {srs.formula ? <ComputedByUs formula={srs.formula} anchor="srs" /> : null}
          </>
        }
        context={
          <>
            {rankLine(srs)}
            {pythagorean ? (
              <>
                {' · '}
                {num(pythagorean.value, 1)} Pythagorean wins
                {pythagorean.formula ? <ComputedByUs formula={pythagorean.formula} anchor="pythagorean" /> : null}
              </>
            ) : null}
          </>
        }
      />,
    )
  }

  if (!tiles.length) return null
  return <TileRow>{tiles.slice(0, 4)}</TileRow>
}

function rankLine(rating: Rating): string {
  return rating.rank ? `${ordinal(rating.rank)} of ${rating.of}` : `unranked of ${rating.of}`
}

function DriveSidePanel({ title, side }: { title: string; side: DriveSide }) {
  const total = Object.values(side.result_mix).reduce((sum, count) => sum + count, 0)
  const mix = Object.entries(side.result_mix).sort((a, b) => b[1] - a[1])

  return (
    <div>
      <h3 className="text-[13px] font-medium">{title}</h3>
      <dl className="mt-1 grid grid-cols-2 gap-x-4">
        <Fact label="Drives per game" value={num(side.drives_per_game, 1)} />
        <Fact label="Plays per drive" value={num(side.plays_per_drive, 1)} />
        <Fact
          label="Average start"
          value={side.avg_start_yardline_100 === null || side.avg_start_yardline_100 === undefined ? '—' : `own ${num(100 - side.avg_start_yardline_100, 1)}`}
        />
        <Fact label="Seconds per drive" value={num(side.seconds_per_drive, 0)} />
      </dl>
      {total > 0 ? (
        <>
          <div className="mt-2 flex h-3 w-full overflow-hidden rounded-sm bg-track" role="img" aria-label={`Drive results: ${mix.map(([label, count]) => `${label} ${count}`).join(', ')}`}>
            {mix.map(([label, count]) => (
              <span
                key={label}
                title={`${label} · ${count} of ${total}`}
                className="h-full border-r border-page last:border-r-0"
                style={{ width: `${(count / total) * 100}%`, background: `var(${resultTone(label)})` }}
              />
            ))}
          </div>
          {/* The bar's table equivalent, in the same place rather than a click away. */}
          <ul className="mt-1 grid grid-cols-2 gap-x-4">
            {mix.map(([label, count]) => (
              <li key={label} className="flex items-baseline justify-between gap-2 text-[11px] text-ink-3">
                <span className="truncate">{label}</span>
                <span>
                  {count} · {rate(count / total)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-[11px] text-ink-3">No drives were charted for this side.</p>
      )}
      <p className="mt-1 text-[11px] text-ink-3">
        {plural(side.drives, 'drive')} over {plural(side.games, 'game')}
      </p>
    </div>
  )
}

/**
 * The two semantic colours, and only where they carry meaning: a drive that
 * ended in points, a drive that ended in a giveaway. Everything else is neutral,
 * with a 1px page-coloured separator so adjacent neutral segments stay legible.
 */
function resultTone(label: string): string {
  const lower = label.toLowerCase()
  if (lower.includes('touchdown') && !lower.startsWith('opp')) return '--c-positive'
  if (lower === 'field goal') return '--c-positive'
  if (lower.includes('turnover') || lower.startsWith('opp')) return '--c-negative'
  return '--c-text-tertiary'
}

function Fact({ label, value: shown }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-row-rule py-1">
      <dt className="text-[11px] text-ink-3">{label}</dt>
      <dd className="text-[13px]">{shown}</dd>
    </div>
  )
}

function shareLine(leader: { offense_share?: number | null; defense_share?: number | null; st_share?: number | null }): string {
  const parts = [
    ['Off', leader.offense_share],
    ['Def', leader.defense_share],
    ['ST', leader.st_share],
  ]
    .filter((entry) => typeof entry[1] === 'number' && (entry[1] as number) > 0)
    .map((entry) => `${entry[0]} ${rate(entry[1] as number)}`)
  return parts.length ? parts.join(' · ') : '—'
}

function InjuryTable({
  rows,
  note,
  from,
  abbr,
  season,
}: {
  rows: InjuryRow[]
  note: string
  from: number
  abbr: string
  season: number
}) {
  const columns: Column<InjuryRow>[] = [
    {
      id: 'player',
      header: 'Player',
      sortValue: (row) => row.player,
      render: (row) => <PlayerLink id={row.gsis_id} name={row.player} />,
    },
    {
      id: 'listed',
      header: 'Weeks listed',
      align: 'right',
      sortValue: (row) => row.weeks_listed,
      render: (row) => num(row.weeks_listed),
    },
    { id: 'out', header: 'Out', align: 'right', sortValue: (row) => row.weeks_out, render: (row) => num(row.weeks_out) },
    {
      id: 'doubtful',
      header: 'Doubtful',
      align: 'right',
      sortValue: (row) => row.weeks_doubtful,
      render: (row) => num(row.weeks_doubtful),
    },
    {
      id: 'questionable',
      header: 'Questionable',
      align: 'right',
      sortValue: (row) => row.weeks_questionable,
      render: (row) => num(row.weeks_questionable),
    },
  ]

  return (
    <>
      <EraBadge from={from} note={note} className="mb-1.5" />
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row, index) => row.gsis_id ?? `${row.player ?? 'unknown'}-${index}`}
        initialSort={{ id: 'listed', desc: true }}
        emptyMessage="No player on this roster carried a weekly game-status designation."
        onExport={(_visible, sorted) =>
          downloadCsv(`${abbr}-${season}-injuries.csv`, columns, sorted, (row, column) => INJURY_CSV[column.id]?.(row) ?? '')
        }
      />
    </>
  )
}

const INJURY_CSV: Record<string, (row: InjuryRow) => string | number | null | undefined> = {
  player: (row) => row.player,
  listed: (row) => row.weeks_listed,
  out: (row) => row.weeks_out,
  doubtful: (row) => row.weeks_doubtful,
  questionable: (row) => row.weeks_questionable,
}

function DriveLogTable({ rows, abbr, season }: { rows: DriveRow[]; abbr: string; season: number }) {
  const columns: Column<DriveRow>[] = [
    {
      id: 'week',
      header: 'Wk',
      width: '4rem',
      sortValue: (row) => row.week,
      render: (row) => <Link to={row.game_href}>{row.week ?? '—'}</Link>,
    },
    { id: 'opponent', header: 'Opp', sortValue: (row) => row.opponent, render: (row) => row.opponent ?? '—' },
    { id: 'drive', header: 'Dr', align: 'right', sortValue: (row) => row.drive, render: (row) => num(row.drive) },
    { id: 'start', header: 'Start', sortValue: (row) => row.start_yardline_100, render: (row) => row.start_yard_line ?? '—' },
    { id: 'end', header: 'End', sortValue: (row) => row.end_yardline_100, render: (row) => row.end_yard_line ?? '—' },
    { id: 'plays', header: 'Plays', align: 'right', sortValue: (row) => row.plays, render: (row) => num(row.plays) },
    {
      id: 'first_downs',
      header: '1st D',
      align: 'right',
      optional: true,
      sortValue: (row) => row.first_downs,
      render: (row) => num(row.first_downs),
    },
    {
      id: 'top',
      header: 'TOP',
      align: 'right',
      sortValue: (row) => row.top_seconds,
      help: 'Time of possession.',
      render: (row) => row.time_of_possession ?? '—',
    },
    {
      id: 'result',
      header: 'Result',
      sortValue: (row) => row.result,
      render: (row) =>
        row.scored ? <span className="text-positive">{row.result ?? '—'}</span> : (row.result ?? <span className="text-ink-3">—</span>),
    },
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row, index) => `${row.game_id}-${row.drive ?? index}`}
      emptyMessage="No drives were charted for this club in this season."
      caption="Every drive in game order, newest game last. The week links to the game."
      onExport={(_visible, sorted) =>
        downloadCsv(`${abbr}-${season}-drives.csv`, columns, sorted, (row, column) => DRIVE_CSV[column.id]?.(row) ?? '')
      }
    />
  )
}

const DRIVE_CSV: Record<string, (row: DriveRow) => string | number | null | undefined> = {
  week: (row) => row.week,
  opponent: (row) => row.opponent,
  drive: (row) => row.drive,
  start: (row) => row.start_yard_line,
  end: (row) => row.end_yard_line,
  plays: (row) => row.plays,
  first_downs: (row) => row.first_downs,
  top: (row) => row.time_of_possession,
  result: (row) => row.result,
}

/**
 * Decimals come from the shared formatter; ids it does not recognise fall back
 * to one decimal, which would print "32.0" field goals. A whole number on a
 * default-precision stat is written whole, and a half-sack keeps its half.
 */
function value(input: number | null | undefined, statId: string): string {
  if (input === null || input === undefined) return '—'
  const decimals = decimalsFor(statId)
  return num(input, decimals === 1 && Number.isInteger(input) ? 0 : decimals)
}
