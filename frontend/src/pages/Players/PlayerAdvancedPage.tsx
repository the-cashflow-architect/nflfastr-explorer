import { useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { TrendLine } from '../../components/charts/TrendLine'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { decimalsFor, num, plural } from '../../design/format'
import { usePlayerAdvanced, usePlayerHub, type PlayerAdvanced } from '../../api/endpoints'
import { StatValue } from './blocks/CareerTable'
import { PlayerMiniHeader, SeasonPicker } from './blocks/PlayerHeader'

/**
 * Next Gen Stats, PFR charting, snap share and QBR — the four narrow-window
 * sources, each with the window it actually has *for this player*.
 *
 * The banner is generated from those per-player windows rather than from the
 * datasets' start years: telling a 2019 rookie that his Next Gen Stats run from
 * 2016 is the exact failure this page exists to avoid. A source with no rows
 * for him has no section at all and is named in the banner instead.
 */

const ALL = 'all'
const PAGE_KEY = 'player-advanced'

type Block = NonNullable<PlayerAdvanced['ngs']>[number]
type BlockRow = Block['rows'][number]

//: Columns that identify the player or the file's own keys rather than
//: measuring anything. Hidden from every advanced table.
const IDENTITY_COLUMNS = new Set([
  'player', 'player_id', 'player_gsis_id', 'pfr_id', 'espn_id', 'player_display_name',
  'player_first_name', 'player_last_name', 'player_short_name', 'player_jersey_number',
  'name_first', 'name_last', 'name_display', 'name_short', 'headshot_href',
])

//: Short headers for the columns whose file names are sentences. Anything not
//: listed is prettified from its own name rather than renamed by guesswork.
const LABELS: Record<string, string> = {
  season_type: 'Type',
  team_abbr: 'Team',
  team_abb: 'Team',
  player_position: 'Pos',
  game_week: 'Week',
  avg_time_to_throw: 'Time to throw',
  avg_completed_air_yards: 'Completed air yds',
  avg_intended_air_yards: 'Intended air yds',
  avg_air_yards_differential: 'Air yds differential',
  max_completed_air_distance: 'Max completed air',
  avg_air_yards_to_sticks: 'Air yds to sticks',
  avg_air_distance: 'Air distance',
  max_air_distance: 'Max air distance',
  completion_percentage: 'Comp %',
  expected_completion_percentage: 'Expected comp %',
  completion_percentage_above_expectation: 'CPOE',
  passer_rating: 'Rating',
  pass_touchdowns: 'Pass TD',
  rush_touchdowns: 'Rush TD',
  rec_touchdowns: 'Rec TD',
  percent_attempts_gte_eight_defenders: 'Eight in the box %',
  avg_time_to_los: 'Time to line',
  rush_yards_over_expected: 'Rush yds over expected',
  rush_yards_over_expected_per_att: 'RYOE per carry',
  percent_share_of_intended_air_yards: 'Air yards share',
  avg_yac_above_expectation: 'YAC over expected',
  avg_expected_yac: 'Expected YAC',
  pass_yards_after_catch: 'Pass YAC',
  pass_yards_after_catch_per_completion: 'YAC per completion',
  intended_air_yards_per_pass_attempt: 'Intended air yds / att',
  completed_air_yards_per_completion: 'Completed air yds / comp',
  completed_air_yards_per_pass_attempt: 'Completed air yds / att',
  scramble_yards_per_attempt: 'Scramble yds / att',
  qbr_total: 'QBR',
  pts_added: 'Points added',
  epa_total: 'EPA',
  qb_plays: 'Plays',
  qbr_raw: 'Raw QBR',
  exp_sack: 'Expected sack',
}

//: The columns each source leads with. Everything else in the file stays one
//: click away in the column picker and in the export, never dropped. A source
//: with no entry here — or one whose names have moved — shows every column.
const PRIMARY: Record<string, string[]> = {
  ngs_passing: [
    'season', 'season_type', 'week', 'team_abbr', 'attempts', 'completion_percentage',
    'expected_completion_percentage', 'completion_percentage_above_expectation',
    'avg_time_to_throw', 'aggressiveness', 'avg_intended_air_yards', 'avg_air_yards_to_sticks',
    'passer_rating', 'pass_yards', 'pass_touchdowns', 'interceptions',
  ],
  ngs_rushing: [
    'season', 'season_type', 'week', 'team_abbr', 'rush_attempts', 'rush_yards', 'rush_touchdowns',
    'efficiency', 'percent_attempts_gte_eight_defenders', 'avg_time_to_los',
    'expected_rush_yards', 'rush_yards_over_expected', 'rush_yards_over_expected_per_att',
  ],
  ngs_receiving: [
    'season', 'season_type', 'week', 'team_abbr', 'targets', 'receptions', 'yards', 'rec_touchdowns',
    'catch_percentage', 'avg_cushion', 'avg_separation', 'avg_intended_air_yards',
    'percent_share_of_intended_air_yards', 'avg_yac', 'avg_expected_yac', 'avg_yac_above_expectation',
  ],
  advstats_pass: [
    'season', 'team', 'pass_attempts', 'pocket_time', 'times_blitzed', 'times_hurried', 'times_hit',
    'times_pressured', 'pressure_pct', 'bad_throws', 'bad_throw_pct', 'on_tgt_throws', 'on_tgt_pct',
    'drops', 'drop_pct', 'throwaways', 'batted_balls',
  ],
  qbr_season: [
    'season', 'season_type', 'rank', 'qbr_total', 'pts_added', 'qb_plays', 'epa_total', 'pass', 'run',
    'sack', 'penalty', 'qualified',
  ],
}

//: Plain-language definitions for the abbreviated headers, shown on hover.
//: Only columns whose meaning is documented get one; the rest carry no popover
//: rather than a guess.
const HELP: Record<string, string> = {
  avg_time_to_throw: 'Seconds from snap to release, averaged over his attempts.',
  avg_completed_air_yards: 'Air yards on completions only, averaged.',
  avg_intended_air_yards: 'Air yards on all attempts, completed or not.',
  avg_air_yards_differential: 'Completed air yards minus intended air yards.',
  aggressiveness: 'Share of attempts thrown into tight coverage — a defender within one yard of the receiver.',
  avg_air_yards_to_sticks: 'Air yards relative to the line to gain. Negative means he throws short of the sticks on average.',
  expected_completion_percentage: "The model's completion probability given depth, separation and pressure.",
  completion_percentage_above_expectation: 'Completion percentage minus the expected figure. CPOE.',
  avg_separation: 'Yards between receiver and nearest defender at the catch point.',
  avg_cushion: 'Yards the defender lines up off the receiver at the snap.',
  avg_yac_above_expectation: 'Yards after catch minus the model’s expectation for that catch.',
  efficiency: 'Distance travelled per yard gained downfield. Lower is more direct.',
  rush_yards_over_expected: 'Rushing yards minus the yards the model expected given the blocking and box.',
  pressure_pct: 'Share of drop-backs where he was pressured.',
  pocket_time: 'Seconds held in the pocket, averaged.',
  bad_throw_pct: 'Share of throws charted as inaccurate, excluding throwaways and spikes.',
  on_tgt_pct: 'Share of throws charted as on target.',
  drop_pct: 'Share of catchable throws dropped by receivers.',
  times_blitzed: 'Drop-backs faced with five or more rushers.',
  qbr_total: 'ESPN Total QBR, 0–100, adjusted for down, distance and opponent.',
  pts_added: 'Points added over an average quarterback, on ESPN’s scale.',
  epa_total: 'Expected points added across his plays, as ESPN measures it.',
  qb_plays: 'Plays ESPN credits to him, including sacks, scrambles and penalties.',
  week: 'The file\u2019s own week number. Week 0 is its season-total row, not a game.',
}

export function PlayerAdvancedPage() {
  const { gsisId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const hubQuery = usePlayerHub(gsisId)
  const hub = hubQuery.data

  const season = params.get('season') ?? ALL
  const query = usePlayerAdvanced(gsisId, { season: season === ALL ? null : Number(season) })
  const data = query.data

  useCrumbLabel(`/players/${gsisId}/advanced`, hub ? `${hub.identity.display_name} · Advanced` : undefined)

  const seasons = useMemo(() => advancedSeasons(data ?? hub), [data, hub])

  return (
    <>
      <PlayerMiniHeader hub={hub} gsisId={gsisId} section="Advanced" />
      <PageHeader
        title="Advanced"
        meta={
          season === ALL
            ? 'Every season these sources hold for him'
            : `Season ${season}`
        }
      />

      {seasons.length ? (
        <div className="mt-3">
          <SeasonPicker
            seasons={seasons}
            value={season}
            onChange={(value) => {
              const next = new URLSearchParams(params)
              if (value === ALL) next.delete('season')
              else next.set('season', value)
              setParams(next, { replace: true })
            }}
            allValue={ALL}
            allLabel="All seasons"
            ariaLabel="Season"
          />
        </div>
      ) : null}

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <Advanced data={data} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function Advanced({ data }: { data: PlayerAdvanced }) {
  const ngs = data.ngs ?? []
  const advstats = data.advstats ?? []
  const snaps = data.snaps ?? []
  const nothing = !ngs.length && !advstats.length && !snaps.length && !data.qbr

  return (
    <>
      <CoverageBanner data={data} />

      {nothing ? (
        <p className="px-1 py-6 text-[13px] text-ink-3">
          {data.note ??
            'None of the advanced sources has a row for him in this scope. The windows above say which ones were tried.'}
        </p>
      ) : null}

      {ngs.map((block, index) => (
        <BlockSection key={block.source} block={block} chart open={index === 0} />
      ))}

      {advstats.map((block, index) => (
        <BlockSection
          key={block.source}
          block={block}
          open={index === 0}
          note="Charted by Pro-Football-Reference and published through nflverse."
        />
      ))}

      {snaps.length ? <SnapSection snaps={snaps} /> : null}

      {data.qbr ? <BlockSection block={data.qbr} /> : null}
    </>
  )
}

function CoverageBanner({ data }: { data: PlayerAdvanced }) {
  return (
    <div className="mb-6 rounded-md border border-line bg-raised px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-[0.04em] text-ink-3">Coverage for this player</p>
      <ul className="mt-1 space-y-0.5 text-[12px] leading-5">
        {data.coverage.map((entry) => (
          <li key={entry.source} className="flex flex-wrap items-baseline gap-x-2">
            <span className="min-w-[15rem]">{entry.name}</span>
            <span className={entry.rows ? undefined : 'text-ink-3'}>
              {entry.rows && entry.first_season
                ? `${entry.first_season}–${entry.last_season}`
                : (entry.note ?? 'No rows for this player.')}
            </span>
            {entry.declared_first_season ? (
              <span className="text-[11px] text-ink-3">{`dataset from ${entry.declared_first_season}`}</span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[11px] leading-4 text-ink-3">{data.coverage_note}</p>
    </div>
  )
}

function BlockSection({
  block,
  note,
  chart,
  open,
}: {
  block: Block
  note?: string
  chart?: boolean
  /** The first block of a family is the page; the rest are the archive. */
  open?: boolean
}) {
  const columns = useMemo(() => block.columns.filter((id) => !IDENTITY_COLUMNS.has(id)), [block.columns])
  const primary = useMemo(() => {
    const wanted = PRIMARY[block.source] ?? []
    const present = wanted.filter((id) => columns.includes(id))
    // If the file's names have moved on, showing everything beats showing three
    // columns and pretending that is the source.
    return present.length >= 3 ? new Set(present) : null
  }, [block.source, columns])
  const window =
    block.first_season && block.last_season
      ? `${block.first_season}–${block.last_season}${
          block.declared_first_season ? ` · file begins ${block.declared_first_season}` : ''
        }`
      : undefined

  return (
    <Section
      title={block.name}
      note={[window, note].filter(Boolean).join(' · ') || undefined}
      collapsible
      defaultCollapsed={!open}
      count={plural(block.rows.length, 'row')}
      pageKey={PAGE_KEY}
      sectionKey={block.source}
    >
      {chart ? <BlockChart block={block} columns={columns} /> : null}
      <DataTable
        rows={block.rows}
        columns={columns.map((id) => tableColumn(id, primary ? !primary.has(id) : false))}
        // QBR ships one "Season Total" row per season type, so the index is part
        // of the key or React sees two rows with the same name.
        rowKey={(row, index) => `${String(row.season ?? '')}-${String(row.week ?? row.game_week ?? '')}-${index}`}
        emptyMessage={`${block.name} holds no row for him in this scope.`}
        onExport={(visible, sorted) =>
          downloadCsv(`${block.source}.csv`, visible, sorted, (row, column) => {
            const value = row[column.id]
            return typeof value === 'number' || typeof value === 'string' ? value : null
          })
        }
      />
    </Section>
  )
}

/**
 * A weekly source plotted by week inside one season, or by season across a
 * career — whichever the rows are. Week 0 is the file's season-total row and
 * never appears in the weekly view.
 */
function BlockChart({ block, columns }: { block: Block; columns: string[] }) {
  const metrics = useMemo(() => {
    const skip = ['season', 'season_type', 'week', 'game_week', 'team_abbr', 'team_abb', 'team', 'player_position', 'qualified', 'rank']
    const preferred = PRIMARY[block.source]
    return columns.filter(
      (id) =>
        !skip.includes(id) &&
        (!preferred || preferred.includes(id)) &&
        block.rows.some((row) => typeof row[id] === 'number'),
    )
  }, [block.rows, block.source, columns])
  const [metric, setMetric] = useState(metrics[0] ?? '')

  const seasons = new Set(block.rows.map((row) => Number(row.season)))
  const weekly = seasons.size === 1
  const points = block.rows
    .filter((row) => (weekly ? Number(row.week) > 0 : Number(row.week ?? 0) === 0))
    .map((row) => ({
      x: weekly ? Number(row.week) : Number(row.season),
      value: typeof row[metric] === 'number' ? (row[metric] as number) : null,
    }))
    .sort((a, b) => a.x - b.x)

  if (!metric || points.filter((point) => point.value !== null).length < 2) return null

  return (
    <div className="mb-3">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-ink-3">{weekly ? 'By week' : 'Season totals by season'}</p>
        <Segmented
          options={metrics.slice(0, 8).map((id) => ({ value: id, label: label(id) }))}
          value={metric}
          onChange={setMetric}
          ariaLabel="Charted metric"
        />
      </div>
      <TrendLine
        data={points}
        xKey="x"
        yKey="value"
        yLabel={label(metric)}
        formatValue={(value) => num(value, decimalsFor(metric))}
      />
    </div>
  )
}

function SnapSection({ snaps }: { snaps: NonNullable<PlayerAdvanced['snaps']> }) {
  const columns: Column<(typeof snaps)[number]>[] = [
    { id: 'season', header: 'Season', sortValue: (row) => row.season, render: (row) => row.season },
    {
      id: 'games',
      header: 'G',
      align: 'right',
      sortValue: (row) => row.games,
      render: (row) => <StatValue value={row.games} unit="count" id="games" />,
    },
    {
      id: 'offense_snaps',
      header: 'Off snaps',
      align: 'right',
      sortValue: (row) => row.offense_snaps ?? null,
      render: (row) => <StatValue value={row.offense_snaps} unit="count" id="snaps" />,
    },
    {
      id: 'offense_share',
      header: 'Share',
      align: 'right',
      help: snaps[0]?.share_note,
      sortValue: (row) => row.offense_share ?? null,
      render: (row) => <StatValue value={row.offense_share} unit="percent" id="snap_pct" />,
    },
  ]

  const points = snaps
    .map((row) => ({ season: row.season, value: row.offense_share ?? null }))
    .sort((a, b) => a.season - b.season)

  return (
    <Section
      title="Snap share"
      collapsible
      defaultCollapsed
      count={plural(snaps.length, 'season')}
      pageKey={PAGE_KEY}
      sectionKey="snaps"
    >
      {points.filter((point) => point.value !== null).length >= 2 ? (
        <TrendLine
          data={points}
          xKey="season"
          yKey="value"
          yLabel="Offensive snap share"
          formatValue={(value) => `${num(value, 1)}%`}
        />
      ) : null}
      <DataTable
        rows={snaps}
        columns={columns}
        rowKey={(row) => String(row.season)}
        emptyMessage="No season of his has a snap-count row."
        caption={
          <>
            {snaps[0]?.share_note}
            <ComputedByUs
              formula="Snaps played over team snaps, recovered from the per-game percentages"
              anchor="snap-share"
            />
          </>
        }
        onExport={(visible, sorted) =>
          downloadCsv('snap-share.csv', visible, sorted, (row, column) =>
            column.id === 'season'
              ? row.season
              : column.id === 'games'
                ? row.games
                : column.id === 'offense_snaps'
                  ? (row.offense_snaps ?? null)
                  : (row.offense_share ?? null),
          )
        }
      />
    </Section>
  )
}

function tableColumn(id: string, optional: boolean): Column<BlockRow> {
  const numeric = id !== 'season_type' && id !== 'team' && id !== 'game_week'
  return {
    id,
    header: label(id),
    help: HELP[id],
    optional,
    align: numeric ? 'right' : 'left',
    sortValue: (row) => {
      const value = row[id]
      return typeof value === 'number' || typeof value === 'string' ? value : null
    },
    render: (row) => cell(row[id], id),
  }
}

function cell(value: unknown, id: string): React.ReactNode {
  if (value === null || value === undefined || value === '') return <span className="text-ink-3">—</span>
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    // A season is a label, not a quantity: 2,024.0 is the giveaway that a
    // generic renderer was pointed at an identifier.
    if (id === 'season') return String(Math.round(value))
    // Week 0 is the season-total row these files carry alongside the weeks.
    if (id === 'week' && value === 0) return 'Season'
    return num(value, blockDecimals(id))
  }
  return String(value)
}

/**
 * These files arrive as floats whatever the column means, so the name decides.
 * An average never rounds to a whole number, and a count never carries ".0" —
 * "26.0 touchdowns" is the tell of a renderer that was not told what it holds.
 */
function blockDecimals(id: string): number {
  if (/^avg_|_avg$|_per_|percentage|_pct$|share|efficiency|rating|_time$|expected/.test(id)) {
    return Math.max(1, decimalsFor(id))
  }
  if (
    /(week|rank|plays|snaps|games|attempts|completions|receptions|targets|touchdowns|interceptions|yards|throws|throwaways|spikes|drops|balls|scrambles|blitzed|hurried|hit|pressured|tds)$/.test(id)
  ) {
    return 0
  }
  return decimalsFor(id)
}

function label(id: string): string {
  if (LABELS[id]) return LABELS[id]
  const words = id.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Every season any of this player's advanced sources actually covers. */
function advancedSeasons(data: PlayerAdvanced | ReturnType<typeof usePlayerHub>['data']): number[] {
  const windows = data?.coverage ?? []
  const first = windows.filter((entry) => entry.rows && entry.first_season).map((entry) => entry.first_season as number)
  const last = windows.filter((entry) => entry.rows && entry.last_season).map((entry) => entry.last_season as number)
  if (!first.length || !last.length) return []
  const out: number[] = []
  for (let season = Math.max(...last); season >= Math.min(...first); season -= 1) out.push(season)
  return out
}
