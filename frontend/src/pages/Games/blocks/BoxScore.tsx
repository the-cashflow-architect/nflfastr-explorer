import type { Game } from '../../../api/endpoints'
import { DataTable, type Column } from '../../../components/ui/DataTable'
import { downloadCsv } from '../../../components/ui/downloadCsv'
import { PlayerLink } from '../../../components/ui/EntityLink'
import { EraBadge } from '../../../components/ui/Honesty'
import { Segmented } from '../../../components/ui/Page'
import { decimalsFor, num, rate } from '../../../design/format'

type BoxScoreData = NonNullable<Game['box_score']>
type BoxCategory = BoxScoreData['categories'][number]
type BoxRow = BoxCategory['home'][number]
type SnapsData = NonNullable<Game['snaps']>
type SnapRow = SnapsData['home'][number]

/**
 * The box score, one category at a time, away club first.
 *
 * Only the categories the payload carries are offered: a game whose weekly file
 * has no kicking columns has no kicking tab, rather than a tab that opens onto
 * two empty tables.
 */
export function BoxScore({
  box,
  data,
  category,
  onCategoryChange,
}: {
  box: BoxScoreData
  data: Game
  category: string
  onCategoryChange: (id: string) => void
}) {
  const current = box.categories.find((entry) => entry.id === category) ?? box.categories[0]
  const away = data.header.away
  const home = data.header.home

  return (
    <div>
      <Segmented
        ariaLabel="Box score category"
        value={current.id}
        onChange={onCategoryChange}
        options={box.categories.map((entry) => ({ value: entry.id, label: entry.label }))}
      />

      <div className="mt-3 space-y-5">
        <BoxTable
          title={away.name ?? away.abbr ?? 'Away'}
          rows={current.away}
          category={current}
          gameId={data.game_id}
          side="away"
        />
        <BoxTable
          title={home.name ?? home.abbr ?? 'Home'}
          rows={current.home}
          category={current}
          gameId={data.game_id}
          side="home"
        />
      </div>

      <p className="mt-2 text-[11px] leading-4 text-ink-3">{box.note}</p>
      {box.charting_note ? <p className="mt-1 text-[11px] leading-4 text-ink-3">{box.charting_note}</p> : null}
    </div>
  )
}

function BoxTable({
  title,
  rows,
  category,
  gameId,
  side,
}: {
  title: string
  rows: BoxRow[]
  category: BoxCategory
  gameId: string
  side: 'home' | 'away'
}) {
  // Decimals come from the stat, not from this component — except that the
  // weekly file stores counts as floats, so a column whose every value is whole
  // is printed whole. Half-sacks and half-tackles-for-loss keep their decimal.
  const decimals = new Map(
    category.columns.map((column) => [
      column.id,
      decimalsForColumn(column.id, [...category.home, ...category.away].map((row) => row.values[column.id])),
    ]),
  )

  const columns: Column<BoxRow>[] = [
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.name,
      render: (row) => <PlayerLink id={row.player_id} name={row.name} />,
    },
    {
      id: 'position',
      header: 'Pos',
      width: '4rem',
      sortValue: (row) => row.position,
      render: (row) => <span className="text-ink-2">{row.position ?? '—'}</span>,
    },
    ...category.columns.map<Column<BoxRow>>((column) => ({
      id: column.id,
      header: column.label,
      align: 'right' as const,
      sortValue: (row) => row.values[column.id],
      render: (row) => num(row.values[column.id], decimals.get(column.id) ?? 0),
    })),
  ]

  return (
    <div>
      <h3 className="mb-1 text-[13px] font-medium">{title}</h3>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row, index) => row.player_id ?? `${index}`}
        initialSort={{ id: category.columns[0]?.id ?? 'player', desc: true }}
        emptyMessage={`No ${category.label.toLowerCase()} line for ${title} in this game.`}
        onExport={(visible, sorted) =>
          downloadCsv(`${gameId}-${category.id}-${side}.csv`, visible, sorted, (row, column) =>
            column.id === 'player' ? row.name : column.id === 'position' ? row.position : row.values[column.id],
          )
        }
      />
    </div>
  )
}

/**
 * Snap counts for both clubs.
 *
 * The join to a player page runs through `pfr_id` and misses about one row in
 * five hundred. A miss keeps its snaps and loses only its link — which is what
 * `PlayerLink` does with a name and no id — because a player who was on the
 * field is not a player who played zero snaps.
 */
export function SnapCounts({ snaps, data }: { snaps: SnapsData; data: Game }) {
  const away = data.header.away
  const home = data.header.home
  return (
    <div className="space-y-5">
      <SnapTable title={away.name ?? away.abbr ?? 'Away'} rows={snaps.away} gameId={data.game_id} side="away" />
      <SnapTable title={home.name ?? home.abbr ?? 'Home'} rows={snaps.home} gameId={data.game_id} side="home" />
      <div>
        <p className="text-[11px] leading-4 text-ink-3">{snaps.note}</p>
        {snaps.unmatched_players ? (
          <p className="text-[11px] leading-4 text-ink-3">
            {snaps.unmatched_players} players in this game kept their snaps without a player page to link to.
          </p>
        ) : null}
        <EraBadge from={snaps.first_season} note="snap counts begin here" />
      </div>
    </div>
  )
}

function SnapTable({
  title,
  rows,
  gameId,
  side,
}: {
  title: string
  rows: SnapRow[]
  gameId: string
  side: 'home' | 'away'
}) {
  const columns: Column<SnapRow>[] = [
    {
      id: 'player',
      header: 'Player',
      width: '12rem',
      sortValue: (row) => row.name,
      render: (row) => <PlayerLink id={row.gsis_id} name={row.name} />,
    },
    {
      id: 'position',
      header: 'Pos',
      width: '4rem',
      sortValue: (row) => row.position,
      render: (row) => <span className="text-ink-2">{row.position ?? '—'}</span>,
    },
    { id: 'offense_snaps', header: 'Off', align: 'right', sortValue: (row) => row.offense_snaps, render: (row) => num(row.offense_snaps, 0) },
    { id: 'offense_pct', header: 'Off %', align: 'right', sortValue: (row) => row.offense_pct, render: (row) => rate(row.offense_pct, 0) },
    { id: 'defense_snaps', header: 'Def', align: 'right', sortValue: (row) => row.defense_snaps, render: (row) => num(row.defense_snaps, 0) },
    { id: 'defense_pct', header: 'Def %', align: 'right', sortValue: (row) => row.defense_pct, render: (row) => rate(row.defense_pct, 0) },
    { id: 'st_snaps', header: 'ST', align: 'right', sortValue: (row) => row.st_snaps, render: (row) => num(row.st_snaps, 0) },
    { id: 'st_pct', header: 'ST %', align: 'right', sortValue: (row) => row.st_pct, render: (row) => rate(row.st_pct, 0) },
  ]

  return (
    <div>
      <h3 className="mb-1 text-[13px] font-medium">{title}</h3>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row, index) => row.gsis_id ?? `${index}`}
        initialSort={{ id: 'offense_snaps', desc: true }}
        emptyMessage={`We hold no snap sheet for ${title} in this game.`}
        onExport={(visible, sorted) =>
          downloadCsv(`${gameId}-snaps-${side}.csv`, visible, sorted, (row, column) =>
            column.id === 'player'
              ? row.name
              : column.id === 'position'
                ? row.position
                : (row[column.id as keyof SnapRow] as number | null | undefined),
          )
        }
      />
    </div>
  )
}

function decimalsForColumn(id: string, values: (number | null | undefined)[]): number {
  const declared = decimalsFor(id)
  if (declared > 1) return declared
  const present = values.filter((value): value is number => value !== null && value !== undefined && !Number.isNaN(value))
  return present.length > 0 && present.every((value) => Number.isInteger(value)) ? 0 : declared
}
