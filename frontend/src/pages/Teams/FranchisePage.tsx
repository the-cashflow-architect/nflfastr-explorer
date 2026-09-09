import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useFranchise, type Franchise } from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { CollegeLink, PlayerLink } from '../../components/ui/EntityLink'
import { ComputedByUs, EraBadge } from '../../components/ui/Honesty'
import { PageHeader, Section, Segmented, Tile, TileRow } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { decimalsFor, num, ordinal, plural, record as formatRecord, signed, winPct } from '../../design/format'
import { TeamHeader } from './blocks/TeamHeader'

type SeasonRow = Franchise['seasons'][number]
type Pick = NonNullable<Franchise['draft']>['picks'][number]
type Coach = NonNullable<Franchise['coaches']>[number]

/**
 * The franchise hub: everything one club has done inside our window, and an era
 * badge saying plainly where that window starts.
 *
 * A historical code resolves here — /teams/STL answers as the Rams — so every
 * year-by-year row prints the name and the code the club actually went by that
 * season rather than today's.
 */
export function FranchisePage() {
  const { abbr = '' } = useParams()
  const query = useFranchise(abbr)
  const data = query.data
  useCrumbLabel(`/teams/${abbr}`, data?.team.name)
  useAnchorScroll(!!data)

  return (
    <>
      {data ? null : <PageHeader title={abbr.toUpperCase()} meta="Franchise" />}
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {data ? <FranchiseBody data={data} abbr={abbr} /> : null}
      </QueryBoundary>
    </>
  )
}

function FranchiseBody({ data, abbr }: { data: Franchise; abbr: string }) {
  const [params, setParams] = useSearchParams()
  const { team, era, summary, seasons, leaders, draft, coaches } = data

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const name = team.name ?? team.abbr
  const latest = seasons[0]
  // Relocations and rebrands: the column only earns its width when the club
  // actually went by more than one name inside the window.
  const nameVaries = new Set(seasons.map((season) => season.label ?? season.code_in_season)).size > 1

  const meta = [
    latest ? `${latest.conference ?? ''} ${latest.division ?? ''}`.trim() : null,
    `${plural(summary.seasons, 'season')} since ${era.seasons_from}`,
    `${formatRecord(summary.w, summary.l, summary.t)} · ${winPct(summary.pct)}`,
    team.aliases.length > 1 ? `Codes: ${team.aliases.join(', ')}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <TeamHeader team={team} title={name} meta={meta} />

      {/* The honesty contract for this page: not collapsible, not dismissible. */}
      <div className="mb-5 rounded-md border border-line bg-raised px-3 py-2">
        <p className="text-[12px] leading-4 text-ink-2">{era.note}</p>
        {/* The badge adds what the sentence cannot: where the season data stops. */}
        <EraBadge from={era.seasons_from} to={latest?.season} note="season records" className="mt-0.5" />
      </div>

      <TileRow>
        <Tile
          label="Regular season"
          value={formatRecord(summary.w, summary.l, summary.t)}
          context={`${winPct(summary.pct)} · ${plural(summary.games, 'game')} since ${era.seasons_from}`}
        />
        <Tile
          label="Playoff seasons"
          value={num(summary.playoff_appearances)}
          context={`of ${summary.seasons} seasons · ${plural(summary.division_titles, 'division title')}`}
        />
        <Tile
          label="Postseason"
          value={formatRecord(summary.postseason_w, summary.postseason_l)}
          context={`${plural(summary.super_bowls, 'Super Bowl')} won since ${era.seasons_from}`}
        />
        <Tile
          label="Best season"
          value={
            summary.best_season ? (
              <Link to={`/teams/${team.abbr}/${summary.best_season}`}>{summary.best_season}</Link>
            ) : (
              '—'
            )
          }
          context={
            summary.worst_season ? (
              <>
                Worst <Link to={`/teams/${team.abbr}/${summary.worst_season}`}>{summary.worst_season}</Link> · by point
                differential
              </>
            ) : (
              'By point differential'
            )
          }
        />
      </TileRow>

      <div id="year-by-year">
        <Section title="Year by year" note={`Newest first · since ${era.seasons_from}`}>
          <YearByYear rows={seasons} abbr={abbr} showName={nameVaries} formulas={data.formulas} />
        </Section>
      </div>

      {leaders ? (
        <div id="leaders">
          <Section
            title="Franchise leaders"
            collapsible
            // A link that names a category or scope is a link into this block,
            // so it opens rather than making the visitor find the chevron.
            defaultCollapsed={!params.get('leaders') && !params.get('scope')}
            pageKey={`franchise:${team.abbr}`}
            sectionKey="leaders"
            count={`${plural(Object.keys(leaders.categories).length, 'category', 'categories')} since ${leaders.first_season}`}
          >
            <LeadersBlock
              leaders={leaders}
              note={data.leaders_note}
              category={params.get('leaders')}
              scope={params.get('scope')}
              onCategory={(value) => setParam('leaders', value)}
              onScope={(value) => setParam('scope', value)}
            />
          </Section>
        </div>
      ) : null}

      {draft && draft.picks.length ? (
        <div id="draft">
          <Section
            title="Draft history"
            collapsible
            defaultCollapsed={!params.get('decade')}
            pageKey={`franchise:${team.abbr}`}
            sectionKey="draft"
            count={`${plural(draft.picks.length, 'pick')} since ${draft.first_season}`}
          >
            <DraftBlock draft={draft} abbr={abbr} decade={params.get('decade')} onDecade={(value) => setParam('decade', value)} />
          </Section>
        </div>
      ) : null}

      {coaches && coaches.length ? (
        <div id="coaches">
          <Section
            title="Head coaches"
            collapsible
            defaultCollapsed
            pageKey={`franchise:${team.abbr}`}
            sectionKey="coaches"
            count={`${plural(coaches.length, 'coach', 'coaches')} since ${era.seasons_from}`}
          >
            <CoachTable rows={coaches} note={data.coaches_note} abbr={abbr} />
          </Section>
        </div>
      ) : null}
    </>
  )
}

function YearByYear({
  rows,
  abbr,
  showName,
  formulas,
}: {
  rows: SeasonRow[]
  abbr: string
  showName: boolean
  formulas: Franchise['formulas']
}) {
  const columns: Column<SeasonRow>[] = [
    {
      id: 'season',
      header: 'Season',
      width: '5rem',
      sortValue: (row) => row.season,
      render: (row) => <Link to={row.href}>{row.season}</Link>,
    },
    ...(showName
      ? [
          {
            id: 'club',
            header: 'Club',
            sortValue: (row: SeasonRow) => row.label,
            help: 'The name and code the club played under that season.',
            render: (row: SeasonRow) => (
              <span className="whitespace-nowrap">
                {row.label ?? row.code_in_season}
                <span className="ml-1.5 text-[11px] text-ink-3">{row.code_in_season}</span>
              </span>
            ),
          },
        ]
      : []),
    {
      id: 'record',
      header: 'W-L-T',
      align: 'right',
      sortValue: (row) => row.w,
      render: (row) => formatRecord(row.w, row.l, row.t),
    },
    { id: 'pct', header: 'W-L%', align: 'right', sortValue: (row) => row.pct, render: (row) => winPct(row.pct) },
    { id: 'pf', header: 'PF', align: 'right', sortValue: (row) => row.pf, help: 'Points scored.', render: (row) => num(row.pf) },
    { id: 'pa', header: 'PA', align: 'right', sortValue: (row) => row.pa, help: 'Points allowed.', render: (row) => num(row.pa) },
    {
      id: 'diff',
      header: 'Diff',
      align: 'right',
      sortValue: (row) => row.diff,
      help: 'Point differential.',
      render: (row) => signed(row.diff, 0),
    },
    {
      id: 'srs',
      header: 'SRS',
      align: 'right',
      sortValue: (row) => row.srs,
      help: formulas.srs,
      render: (row) => signed(row.srs, 1),
    },
    {
      id: 'sos',
      header: 'SOS',
      align: 'right',
      sortValue: (row) => row.sos,
      help: formulas.sos,
      render: (row) => signed(row.sos, 1),
    },
    {
      id: 'finish',
      header: 'Div',
      align: 'right',
      sortValue: (row) => row.division_finish,
      help: 'Finish within the division that season.',
      render: (row) => (row.division_finish ? ordinal(row.division_finish) : <span className="text-ink-3">—</span>),
    },
    {
      id: 'playoffs',
      header: 'Playoffs',
      sortValue: (row) => row.playoff_result,
      render: (row) => row.playoff_result ?? <span className="text-ink-3">—</span>,
    },
    {
      id: 'coach',
      header: 'Head coach',
      sortValue: (row) => row.coach,
      render: (row) => (row.coaches?.length ? row.coaches.join(', ') : (row.coach ?? <span className="text-ink-3">—</span>)),
    },
    {
      id: 'alignment',
      header: 'Conf/Div',
      optional: true,
      sortValue: (row) => `${row.conference ?? ''} ${row.division ?? ''}`,
      render: (row) => `${row.conference ?? '—'} ${row.division ?? ''}`.trim(),
    },
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => String(row.season)}
      initialSort={{ id: 'season', desc: true }}
      emptyMessage="This club has no seasons inside our window."
      caption={
        <>
          SRS and SOS are our own computation
          <ComputedByUs formula={formulas.srs} anchor="srs" />
        </>
      }
      onExport={(_visible, sorted) =>
        downloadCsv(`${abbr}-seasons.csv`, columns, sorted, (row, column) => SEASON_CSV[column.id]?.(row) ?? '')
      }
    />
  )
}

const SEASON_CSV: Record<string, (row: SeasonRow) => string | number | null | undefined> = {
  season: (row) => row.season,
  club: (row) => row.label,
  record: (row) => formatRecord(row.w, row.l, row.t),
  pct: (row) => row.pct,
  pf: (row) => row.pf,
  pa: (row) => row.pa,
  diff: (row) => row.diff,
  srs: (row) => row.srs,
  sos: (row) => row.sos,
  finish: (row) => row.division_finish,
  playoffs: (row) => row.playoff_result,
  coach: (row) => row.coaches?.join('; ') ?? row.coach,
  alignment: (row) => `${row.conference ?? ''} ${row.division ?? ''}`.trim(),
}

function LeadersBlock({
  leaders,
  note,
  category,
  scope,
  onCategory,
  onScope,
}: {
  leaders: NonNullable<Franchise['leaders']>
  note?: string | null
  category: string | null
  scope: string | null
  onCategory: (value: string) => void
  onScope: (value: string) => void
}) {
  const categories = Object.keys(leaders.categories)
  if (!categories.length) return null
  const active = category && categories.includes(category) ? category : categories[0]
  const single = scope === 'season'
  const boards = leaders.categories[active] ?? []

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Segmented
          ariaLabel="Leader category"
          value={active}
          onChange={onCategory}
          options={categories.map((key) => ({ value: key, label: key.charAt(0).toUpperCase() + key.slice(1) }))}
        />
        <Segmented
          ariaLabel="Leader scope"
          value={single ? 'season' : 'career'}
          onChange={onScope}
          options={[
            { value: 'career', label: 'Career' },
            { value: 'season', label: 'Single season' },
          ]}
        />
      </div>
      {note ? <p className="mb-3 text-[11px] leading-4 text-ink-3">{note}</p> : null}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-3">
        {boards.map((board) => (
          <div key={board.stat} className="rounded-md border border-line bg-raised px-2.5 py-2">
            <h4 className="text-[13px] font-medium">{board.label}</h4>
            <EraBadge from={leaders.first_season} note="this club only" />
            <ol className="mt-1.5">
              {boardRows(board, single).map((row) => (
                <li
                  key={`${row.rank}-${row.gsis_id ?? row.player ?? ''}`}
                  className="flex items-baseline gap-2 border-b border-row-rule py-0.5 last:border-b-0"
                >
                  <span className="w-4 shrink-0 text-right text-[11px] text-ink-3">{row.rank}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px]">
                    <PlayerLink id={row.gsis_id} name={row.player} />
                  </span>
                  <span className="shrink-0 text-[11px] text-ink-3">
                    {row.season ?? spanLabel(row.first_season, row.last_season)}
                  </span>
                  <span className="w-14 shrink-0 text-right text-[12px]">{value(row.value, board.stat)}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  )
}

/** A career row and a single-season row differ by one field; the list reads both. */
interface LeaderRow {
  rank: number
  gsis_id?: string | null
  player?: string | null
  value?: number | null
  season?: number
  first_season?: number | null
  last_season?: number | null
}

function boardRows(
  board: NonNullable<Franchise['leaders']>['categories'][string][number],
  single: boolean,
): LeaderRow[] {
  return single ? board.single_season : board.career
}

function spanLabel(first: number | null | undefined, last: number | null | undefined): string {
  if (!first) return '—'
  return last && last !== first ? `${first}–${last}` : String(first)
}

function DraftBlock({
  draft,
  abbr,
  decade,
  onDecade,
}: {
  draft: NonNullable<Franchise['draft']>
  abbr: string
  decade: string | null
  onDecade: (value: string) => void
}) {
  const decades = useMemo(() => {
    const found = new Set(draft.picks.map((pick) => Math.floor(pick.season / 10) * 10))
    return [...found].sort((a, b) => b - a)
  }, [draft.picks])
  const active = decade && decades.includes(Number(decade)) ? Number(decade) : decades[0]
  const rows = useMemo(
    () =>
      draft.picks
        .filter((pick) => Math.floor(pick.season / 10) * 10 === active)
        .sort(
          (a, b) =>
            b.season - a.season || (a.round ?? 99) - (b.round ?? 99) || (a.pick ?? 999) - (b.pick ?? 999),
        ),
    [draft.picks, active],
  )

  const columns: Column<Pick>[] = [
    {
      id: 'season',
      header: 'Year',
      width: '4.5rem',
      sortValue: (row) => row.season,
      render: (row) => <Link to={row.class_href}>{row.season}</Link>,
    },
    { id: 'round', header: 'Rd', align: 'right', sortValue: (row) => row.round, render: (row) => num(row.round) },
    { id: 'pick', header: 'Pick', align: 'right', sortValue: (row) => row.pick, render: (row) => num(row.pick) },
    {
      id: 'player',
      header: 'Player',
      sortValue: (row) => row.player,
      render: (row) => <PlayerLink id={row.gsis_id} name={row.player} />,
    },
    { id: 'position', header: 'Pos', sortValue: (row) => row.position, render: (row) => row.position ?? '—' },
    {
      id: 'college',
      header: 'College',
      sortValue: (row) => row.college,
      render: (row) => <CollegeLink college={row.college} />,
    },
    {
      id: 'w_av',
      header: 'wAV',
      align: 'right',
      sortValue: (row) => row.w_av,
      help: draft.av_note,
      render: (row) => num(row.w_av),
    },
    {
      id: 'dr_av',
      header: 'drAV',
      align: 'right',
      optional: true,
      sortValue: (row) => row.dr_av,
      help: draft.av_note,
      render: (row) => num(row.dr_av),
    },
    { id: 'games', header: 'G', align: 'right', sortValue: (row) => row.games, render: (row) => num(row.games) },
    {
      id: 'started',
      header: 'St',
      align: 'right',
      optional: true,
      sortValue: (row) => row.seasons_started,
      help: 'Seasons as a primary starter, as PFR counts them.',
      render: (row) => num(row.seasons_started),
    },
    {
      id: 'probowls',
      header: 'PB',
      align: 'right',
      sortValue: (row) => row.probowls,
      help: 'Pro Bowls — a career total from PFR, with no season attached.',
      render: (row) => num(row.probowls),
    },
    {
      id: 'allpro',
      header: 'AP',
      align: 'right',
      optional: true,
      sortValue: (row) => row.allpro,
      help: 'All-Pro selections — a career total from PFR, with no season attached.',
      render: (row) => num(row.allpro),
    },
    {
      id: 'hof',
      header: 'HOF',
      sortValue: (row) => (row.hof ? 1 : 0),
      render: (row) => (row.hof ? 'HOF' : <span className="text-ink-3">—</span>),
    },
  ]

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Segmented
          ariaLabel="Draft decade"
          value={active}
          onChange={(value) => onDecade(String(value))}
          options={decades.map((start) => ({ value: start, label: `${start}s` }))}
        />
        <EraBadge from={draft.first_season} note="the one block with deeper history than our season data" />
      </div>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row) => `${row.season}-${row.round ?? 0}-${row.pick ?? 0}-${row.player ?? ''}`}
        emptyMessage={`No picks are on file for this club in the ${active}s.`}
        caption={
          <>
            {draft.av_note}
            {draft.note ? ` ${draft.note}` : null}
          </>
        }
        onExport={(_visible, sorted) =>
          downloadCsv(`${abbr}-draft-${active}s.csv`, columns, sorted, (row, column) => PICK_CSV[column.id]?.(row) ?? '')
        }
      />
    </div>
  )
}

const PICK_CSV: Record<string, (row: Pick) => string | number | null | undefined> = {
  season: (row) => row.season,
  round: (row) => row.round,
  pick: (row) => row.pick,
  player: (row) => row.player,
  position: (row) => row.position,
  college: (row) => row.college,
  w_av: (row) => row.w_av,
  dr_av: (row) => row.dr_av,
  games: (row) => row.games,
  started: (row) => row.seasons_started,
  probowls: (row) => row.probowls,
  allpro: (row) => row.allpro,
  hof: (row) => (row.hof ? 'HOF' : ''),
}

function CoachTable({ rows, note, abbr }: { rows: Coach[]; note?: string | null; abbr: string }) {
  const columns: Column<Coach>[] = [
    { id: 'coach', header: 'Coach', sortValue: (row) => row.coach, render: (row) => row.coach },
    {
      id: 'span',
      header: 'Seasons',
      sortValue: (row) => row.last_season,
      render: (row) => spanLabel(row.first_season, row.last_season),
    },
    {
      id: 'count',
      header: 'Yrs',
      align: 'right',
      sortValue: (row) => row.seasons_count,
      render: (row) => num(row.seasons_count),
    },
    {
      id: 'record',
      header: 'Regular season',
      align: 'right',
      sortValue: (row) => row.w,
      render: (row) => formatRecord(row.w, row.l, row.t),
    },
    {
      id: 'playoffs',
      header: 'Postseason',
      align: 'right',
      sortValue: (row) => row.playoff_w,
      render: (row) => formatRecord(row.playoff_w, row.playoff_l),
    },
  ]

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.coach}
      initialSort={{ id: 'span', desc: true }}
      emptyMessage="No head coach is named on any game this club played inside our window."
      caption={note}
      onExport={(_visible, sorted) =>
        downloadCsv(`${abbr}-coaches.csv`, columns, sorted, (row, column) => COACH_CSV[column.id]?.(row) ?? '')
      }
    />
  )
}

const COACH_CSV: Record<string, (row: Coach) => string | number | null | undefined> = {
  coach: (row) => row.coach,
  span: (row) => spanLabel(row.first_season, row.last_season),
  count: (row) => row.seasons_count,
  record: (row) => formatRecord(row.w, row.l, row.t),
  playoffs: (row) => formatRecord(row.playoff_w, row.playoff_l),
}

/**
 * Decimals come from the shared formatter; ids it does not recognise fall back
 * to one decimal, which would print "22.0" sacks. A whole number on a
 * default-precision stat is written whole, and a half-sack still shows its half.
 */
function value(input: number | null | undefined, statId: string): string {
  if (input === null || input === undefined) return '—'
  const decimals = decimalsFor(statId)
  return num(input, decimals === 1 && Number.isInteger(input) ? 0 : decimals)
}
