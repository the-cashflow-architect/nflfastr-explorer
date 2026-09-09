import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMemo } from 'react'
import { useDraftClass, type DraftClass } from '../../api/endpoints'
import { DataTable, type Column } from '../../components/ui/DataTable'
import { downloadCsv } from '../../components/ui/downloadCsv'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, Section, TileRow, Tile } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { num, plural, signed } from '../../design/format'

/**
 * One class, one board. The draft is the single part of the product that
 * reaches before 1999 — the coverage note says so, because every other
 * leaderboard in the product would have taught a visitor the opposite.
 *
 * Approximate Value here is PFR's own figure, not ours: `w_av` and `dr_av`
 * come straight from draft_picks.parquet. We do not recompute it, and we do
 * not build a per-season breakdown of it, because no per-season value exists
 * in any nflverse file (see /about/data).
 */

const PAGE_KEY = 'draft-class'

type Pick = DraftClass['picks'][number]
type BestValue = DraftClass['best_value'][number]

export function DraftClassPage() {
  const { year = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const yearNum = Number(year)
  const query = useDraftClass(Number.isFinite(yearNum) && yearNum > 0 ? yearNum : undefined)
  const data = query.data

  useCrumbLabel(`/draft/${year}`, data ? `${data.year} NFL Draft` : undefined)
  useAnchorScroll(!!data)

  const team = params.get('team')

  const setTeam = (value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set('team', value)
    else next.delete('team')
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        title={data ? `${data.year} NFL Draft` : `${year} NFL Draft`}
        meta={data ? plural(data.summary.picks, 'pick') : undefined}
        prev={data?.prev_year ? { to: `/draft/${data.prev_year}`, label: `${data.prev_year} draft` } : undefined}
        next={data?.next_year ? { to: `/draft/${data.next_year}`, label: `${data.next_year} draft` } : undefined}
        subnav={data && !team ? <RoundNav rounds={data.rounds} picks={data.picks} /> : undefined}
      />

      <div className="mt-4">
        <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
          {data ? <Class data={data} team={team} onTeam={setTeam} /> : null}
        </QueryBoundary>
      </div>
    </>
  )
}

function RoundNav({ rounds, picks }: { rounds: number[]; picks: Pick[] }) {
  const present = new Set(picks.map((pick) => pick.round))
  return (
    <nav aria-label="Jump to round" className="flex flex-wrap gap-1">
      {rounds.map((round) =>
        present.has(round) ? (
          <a
            key={round}
            href={`#round-${round}`}
            className="motion-state rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-2 no-underline hover:border-line-strong hover:text-ink"
          >
            {`Rd ${round}`}
          </a>
        ) : null,
      )}
    </nav>
  )
}

function Class({ data, team, onTeam }: { data: DraftClass; team: string | null; onTeam: (value: string | null) => void }) {
  const picks = useMemo(() => (team ? data.picks.filter((pick) => pick.team === team) : data.picks), [data.picks, team])

  // The first pick of each round in the *unfiltered* board gets the anchor id,
  // so the round nav still lands correctly if it is showing at all.
  const roundAnchors = useMemo(() => {
    const seen = new Set<number>()
    const anchors = new Map<Pick, string>()
    for (const pick of data.picks) {
      if (!seen.has(pick.round)) {
        seen.add(pick.round)
        anchors.set(pick, `round-${pick.round}`)
      }
    }
    return anchors
  }, [data.picks])

  return (
    <>
      <p className="mb-5 max-w-3xl text-[12px] leading-5 text-ink-3">{data.coverage_note}</p>

      <TileRow>
        <Tile
          label="Pro Bowlers"
          value={num(data.summary.pro_bowlers, 0)}
          context={`players in this class with a Pro Bowl on their PFR record, of ${plural(data.summary.picks, 'pick')}`}
        />
        <Tile
          label="All-Pros"
          value={num(data.summary.all_pros, 0)}
          context={`players in this class with an All-Pro selection, of ${plural(data.summary.picks, 'pick')}`}
        />
        <Tile label="Hall of Famers" value={num(data.summary.hof, 0)} context={`of ${plural(data.summary.picks, 'pick')} in this class`} />
        {data.summary.median_games !== null && data.summary.median_games !== undefined ? (
          <Tile
            label="Median career games"
            value={num(data.summary.median_games, 0)}
            context="among picks with a recorded games count — a pick with none is excluded, not counted as zero"
          />
        ) : null}
      </TileRow>

      <Section
        title="Draft board"
        note={team ? `Filtered to ${team} · ${plural(picks.length, 'pick')}` : undefined}
        controls={<TeamChips filters={data.team_filters} value={team} onChange={onTeam} />}
      >
        <DataTable
          rows={picks}
          columns={boardColumns()}
          rowKey={(pick) => `${pick.round}-${pick.pick}`}
          rowId={(pick) => roundAnchors.get(pick)}
          emptyMessage={team ? `No pick by ${team} in this class.` : 'No picks on file for this class.'}
          caption={<>{data.av_note}</>}
          onExport={(visible, sorted) => downloadCsv(`draft-${data.year}.csv`, visible, sorted, (row, column) => boardExport(row, column.id))}
        />
      </Section>

      <Section
        title="Combine measurables"
        note={team ? `Filtered to ${team}` : undefined}
        collapsible
        defaultCollapsed
        count={plural(picks.length, 'pick')}
        pageKey={PAGE_KEY}
        sectionKey="combine"
      >
        <DataTable
          rows={picks}
          columns={combineColumns()}
          rowKey={(pick) => `${pick.round}-${pick.pick}-combine`}
          emptyMessage="No pick in this view."
          caption={<>{data.combine_note}</>}
          onExport={(visible, sorted) =>
            downloadCsv(`draft-${data.year}-combine.csv`, visible, sorted, (row, column) => combineExport(row, column.id))
          }
        />
      </Section>

      <Section
        title="Best value by round"
        collapsible
        defaultCollapsed
        count={plural(data.best_value.length, 'pick')}
        pageKey={PAGE_KEY}
        sectionKey="best-value"
      >
        <DataTable
          rows={data.best_value}
          columns={bestValueColumns()}
          rowKey={(row) => `${row.round}-${row.pick}`}
          emptyMessage="No pick in this class qualifies for the cohort below."
          caption={<>{data.best_value_cohort.note}</>}
          onExport={(visible, sorted) =>
            downloadCsv(`draft-${data.year}-best-value.csv`, visible, sorted, (row, column) => bestValueExport(row, column.id))
          }
        />
      </Section>
    </>
  )
}

function TeamChips({
  filters,
  value,
  onChange,
}: {
  filters: DraftClass['team_filters']
  value: string | null
  onChange: (value: string | null) => void
}) {
  return (
    <div className="flex flex-wrap gap-1">
      <button
        type="button"
        onClick={() => onChange(null)}
        aria-pressed={!value}
        className={`motion-state rounded border px-1.5 py-0.5 text-[11px] ${!value ? 'border-line-strong text-ink' : 'border-line text-ink-3 hover:border-line-strong'}`}
      >
        All teams
      </button>
      {filters.map((filter) => (
        <button
          key={filter.team}
          type="button"
          onClick={() => onChange(filter.team === value ? null : filter.team)}
          aria-pressed={filter.team === value}
          className={`motion-state rounded border px-1.5 py-0.5 text-[11px] ${
            filter.team === value ? 'border-line-strong text-ink' : 'border-line text-ink-3 hover:border-line-strong'
          }`}
        >
          {filter.team}
        </button>
      ))}
    </div>
  )
}

function boardColumns(): Column<Pick>[] {
  return [
    { id: 'round', header: 'Rd', width: '3rem', align: 'right', sortValue: (row) => row.round, render: (row) => row.round },
    { id: 'pick', header: 'Pick', width: '3.5rem', align: 'right', sortValue: (row) => row.pick, render: (row) => row.pick },
    {
      id: 'team',
      header: 'Team',
      width: '5rem',
      sortValue: (row) => row.team ?? row.pfr_team_code ?? '',
      render: (row) => <TeamCell pick={row} />,
    },
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.player ?? '',
      render: (row) => <PlayerCell pick={row} />,
    },
    { id: 'position', header: 'Pos', width: '4rem', sortValue: (row) => row.position ?? '', render: (row) => row.position ?? em() },
    {
      id: 'age',
      header: 'Age',
      align: 'right',
      width: '3.5rem',
      sortValue: (row) => row.age ?? null,
      render: (row) => (row.age ? num(row.age, 0) : em()),
    },
    {
      id: 'college',
      header: 'College',
      width: '9rem',
      sortValue: (row) => row.college ?? '',
      render: (row) => row.college ?? em(),
    },
    {
      id: 'last_season',
      header: 'Last season',
      align: 'right',
      width: '6rem',
      help: "PFR's own record of the last season played, from the draft file — not our 1999 stat window.",
      sortValue: (row) => row.last_season_played ?? null,
      render: (row) => (row.last_season_played ? String(row.last_season_played) : em()),
    },
    {
      id: 'games',
      header: 'G',
      align: 'right',
      help: 'Career games, as PFR recorded the full career — not our 1999 stat window.',
      sortValue: (row) => row.games ?? null,
      render: (row) => num(row.games ?? null, 0),
    },
    {
      id: 'seasons_started',
      header: 'GS Seasons',
      align: 'right',
      help: 'Seasons PFR credits as a starter.',
      optional: true,
      sortValue: (row) => row.seasons_started ?? null,
      render: (row) => num(row.seasons_started ?? null, 0),
    },
    {
      id: 'probowls',
      header: 'PB',
      align: 'right',
      help: 'Pro Bowl selections, PFR career total.',
      sortValue: (row) => row.probowls ?? null,
      render: (row) => num(row.probowls ?? null, 0),
    },
    {
      id: 'allpro',
      header: 'AP',
      align: 'right',
      help: 'All-Pro selections, PFR career total.',
      sortValue: (row) => row.allpro ?? null,
      render: (row) => num(row.allpro ?? null, 0),
    },
    {
      id: 'w_av',
      header: 'AV',
      align: 'right',
      help: "PFR's weighted career Approximate Value — career total, not per season.",
      sortValue: (row) => row.w_av ?? null,
      render: (row) => num(row.w_av ?? null, 0),
    },
    {
      id: 'dr_av',
      header: 'Draft AV',
      align: 'right',
      optional: true,
      help: "The same player's Approximate Value earned with the club that drafted them.",
      sortValue: (row) => row.dr_av ?? null,
      render: (row) => num(row.dr_av ?? null, 0),
    },
  ]
}

function boardExport(row: Pick, columnId: string): string | number | null {
  switch (columnId) {
    case 'round':
      return row.round
    case 'pick':
      return row.pick
    case 'team':
      return row.team ?? row.pfr_team_code ?? null
    case 'player':
      return row.player ?? null
    case 'position':
      return row.position ?? null
    case 'age':
      return row.age ?? null
    case 'college':
      return row.college ?? null
    case 'last_season':
      return row.last_season_played ?? null
    case 'games':
      return row.games ?? null
    case 'seasons_started':
      return row.seasons_started ?? null
    case 'probowls':
      return row.probowls ?? null
    case 'allpro':
      return row.allpro ?? null
    case 'w_av':
      return row.w_av ?? null
    case 'dr_av':
      return row.dr_av ?? null
    default:
      return null
  }
}

function combineColumns(): Column<Pick>[] {
  return [
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.player ?? '',
      render: (row) => <PlayerCell pick={row} />,
    },
    { id: 'college', header: 'College', width: '9rem', sortValue: (row) => row.college ?? '', render: (row) => row.college ?? em() },
    {
      id: 'forty',
      header: '40 yd',
      align: 'right',
      sortValue: (row) => row.combine?.forty ?? null,
      render: (row) => (row.combine?.forty != null ? num(row.combine.forty, 2) : em()),
    },
    {
      id: 'bench',
      header: 'Bench',
      align: 'right',
      sortValue: (row) => row.combine?.bench ?? null,
      render: (row) => (row.combine?.bench != null ? num(row.combine.bench, 0) : em()),
    },
    {
      id: 'vertical',
      header: 'Vertical',
      align: 'right',
      sortValue: (row) => row.combine?.vertical ?? null,
      render: (row) => (row.combine?.vertical != null ? num(row.combine.vertical, 1) : em()),
    },
    {
      id: 'broad',
      header: 'Broad',
      align: 'right',
      sortValue: (row) => row.combine?.broad ?? null,
      render: (row) => (row.combine?.broad != null ? num(row.combine.broad, 0) : em()),
    },
    {
      id: 'cone',
      header: 'Cone',
      align: 'right',
      optional: true,
      sortValue: (row) => row.combine?.cone ?? null,
      render: (row) => (row.combine?.cone != null ? num(row.combine.cone, 2) : em()),
    },
    {
      id: 'shuttle',
      header: 'Shuttle',
      align: 'right',
      optional: true,
      sortValue: (row) => row.combine?.shuttle ?? null,
      render: (row) => (row.combine?.shuttle != null ? num(row.combine.shuttle, 2) : em()),
    },
    {
      id: 'match',
      header: 'Match',
      help: 'How this pick was joined to a combine row. No match renders blank, never a guess.',
      sortValue: (row) => row.combine_match_confidence ?? '',
      render: (row) =>
        row.combine_match_confidence ? (
          <span className="text-[11px] uppercase tracking-[0.03em] text-ink-3">{row.combine_match_confidence}</span>
        ) : (
          em()
        ),
    },
  ]
}

function combineExport(row: Pick, columnId: string): string | number | null {
  switch (columnId) {
    case 'player':
      return row.player ?? null
    case 'college':
      return row.college ?? null
    case 'forty':
      return row.combine?.forty ?? null
    case 'bench':
      return row.combine?.bench ?? null
    case 'vertical':
      return row.combine?.vertical ?? null
    case 'broad':
      return row.combine?.broad ?? null
    case 'cone':
      return row.combine?.cone ?? null
    case 'shuttle':
      return row.combine?.shuttle ?? null
    case 'match':
      return row.combine_match_confidence ?? null
    default:
      return null
  }
}

function bestValueColumns(): Column<BestValue>[] {
  return [
    { id: 'round', header: 'Rd', width: '3rem', align: 'right', sortValue: (row) => row.round, render: (row) => row.round },
    { id: 'pick', header: 'Pick', width: '3.5rem', align: 'right', sortValue: (row) => row.pick, render: (row) => row.pick },
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.player ?? '',
      render: (row) => <BestValuePlayer row={row} />,
    },
    {
      id: 'w_av',
      header: 'Career AV',
      align: 'right',
      help: "PFR's weighted career Approximate Value.",
      sortValue: (row) => row.w_av,
      render: (row) => num(row.w_av, 0),
    },
    {
      id: 'slot_median_av',
      header: 'Slot median',
      align: 'right',
      help: 'Median career AV at this exact pick slot, across the cohort below.',
      sortValue: (row) => row.slot_median_av,
      render: (row) => num(row.slot_median_av, 0),
    },
    {
      id: 'delta',
      header: 'Delta',
      align: 'right',
      emphasis: true,
      sortValue: (row) => row.delta,
      render: (row) => (
        <>
          {signed(row.delta, 0)}
          <ComputedByUs formula="Career AV minus the median career AV at that pick slot, over the cohort stated below." anchor="draft-best-value" />
        </>
      ),
    },
  ]
}

function bestValueExport(row: BestValue, columnId: string): string | number | null {
  switch (columnId) {
    case 'round':
      return row.round
    case 'pick':
      return row.pick
    case 'player':
      return row.player ?? null
    case 'w_av':
      return row.w_av
    case 'slot_median_av':
      return row.slot_median_av
    case 'delta':
      return row.delta
    default:
      return null
  }
}

function PlayerCell({ pick }: { pick: Pick }) {
  if (!pick.player) return em()
  const name =
    pick.gsis_id && pick.player_href ? <Link to={pick.player_href}>{pick.player}</Link> : <span>{pick.player}</span>
  if (!pick.hof) return name
  return (
    <span>
      {name}
      <span className="ml-1 text-[10px] font-semibold text-ink-3" title="Pro Football Hall of Fame">
        HOF
      </span>
    </span>
  )
}

function BestValuePlayer({ row }: { row: BestValue }) {
  if (!row.player) return em()
  if (!row.gsis_id || !row.player_href) return <span>{row.player}</span>
  return <Link to={row.player_href}>{row.player}</Link>
}

function TeamCell({ pick }: { pick: Pick }) {
  const label = pick.team ?? pick.pfr_team_code
  if (!label) return em()
  if (!pick.team_href) return <span>{label}</span>
  return <Link to={pick.team_href}>{label}</Link>
}

function em() {
  return <span className="text-ink-3">—</span>
}
