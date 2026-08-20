import type { SortSpec } from '../types'

/**
 * Position-aware presets for the Basic / Advanced / Fantasy stat tabs.
 *
 * PFR splits player stats into separate pages per stat family (Passing,
 * Rushing & Receiving, Defense, ...) because a QB and a CB don't share a
 * meaningful "basic" table. We have one wide dataset instead of separate
 * pages, so position pills + these presets recreate the same effect:
 * picking a position narrows both the rows (via the `position_group`
 * filter) and which columns/sort make sense for them.
 */

export interface PositionPill {
  id: string
  label: string
  /** Values matched against `position_group` with an `in` filter. Empty = no filter (All). */
  positionGroups: string[]
  hint: string
}

export const POSITION_PILLS: PositionPill[] = [
  { id: 'all', label: 'All', positionGroups: [], hint: 'Every position, mixed together.' },
  { id: 'qb', label: 'QB', positionGroups: ['QB'], hint: 'Quarterbacks.' },
  { id: 'rb', label: 'RB', positionGroups: ['RB'], hint: 'Running backs and fullbacks.' },
  { id: 'wr', label: 'WR', positionGroups: ['WR'], hint: 'Wide receivers.' },
  { id: 'te', label: 'TE', positionGroups: ['TE'], hint: 'Tight ends.' },
  {
    id: 'def',
    label: 'Defense',
    positionGroups: ['DL', 'LB', 'DB'],
    hint: 'Defensive linemen, linebackers, and defensive backs.',
  },
  { id: 'st', label: 'K / P', positionGroups: ['SPEC'], hint: 'Kickers, punters, and long snappers.' },
]

interface StatFamily {
  basicColumns: string[]
  basicSort: SortSpec[]
  advancedColumns: string[] | null
  advancedSort: SortSpec[]
  /** Shown when advancedColumns is null, explaining the gap honestly. */
  advancedUnavailableReason?: string
}

const IDENTITY_WEEKLY = ['season', 'week', 'player_display_name', 'position', 'team', 'opponent_team']
// player_season has no per-game opponent, and its team column is
// "recent_team" rather than "team" (a player can change teams mid-season).
const IDENTITY_SEASON = ['season', 'player_display_name', 'position', 'recent_team', 'games']

const FAMILIES: Record<string, StatFamily> = {
  all: {
    basicColumns: [
      'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
      'carries', 'rushing_yards', 'rushing_tds',
      'receptions', 'targets', 'receiving_yards', 'receiving_tds',
    ],
    basicSort: [],
    advancedColumns: ['passing_epa', 'rushing_epa', 'receiving_epa', 'pacr', 'racr', 'wopr'],
    advancedSort: [{ field: 'passing_epa', direction: 'desc' }],
  },
  qb: {
    basicColumns: [
      'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
      'sacks_suffered', 'rushing_yards', 'rushing_tds',
    ],
    basicSort: [{ field: 'passing_yards', direction: 'desc' }],
    advancedColumns: ['passing_epa', 'passing_cpoe', 'pacr', 'rushing_epa'],
    advancedSort: [{ field: 'passing_epa', direction: 'desc' }],
  },
  rb: {
    basicColumns: [
      'carries', 'rushing_yards', 'rushing_tds', 'rushing_first_downs',
      'receptions', 'targets', 'receiving_yards', 'receiving_tds',
    ],
    basicSort: [{ field: 'rushing_yards', direction: 'desc' }],
    advancedColumns: ['rushing_epa', 'receiving_epa', 'target_share'],
    advancedSort: [{ field: 'rushing_epa', direction: 'desc' }],
  },
  wr: {
    basicColumns: [
      'targets', 'receptions', 'receiving_yards', 'receiving_tds',
      'receiving_air_yards', 'receiving_yards_after_catch',
    ],
    basicSort: [{ field: 'receiving_yards', direction: 'desc' }],
    advancedColumns: ['receiving_epa', 'racr', 'wopr', 'target_share', 'air_yards_share'],
    advancedSort: [{ field: 'receiving_epa', direction: 'desc' }],
  },
  te: {
    basicColumns: [
      'targets', 'receptions', 'receiving_yards', 'receiving_tds',
      'receiving_air_yards', 'receiving_yards_after_catch',
    ],
    basicSort: [{ field: 'receiving_yards', direction: 'desc' }],
    advancedColumns: ['receiving_epa', 'racr', 'wopr', 'target_share'],
    advancedSort: [{ field: 'receiving_epa', direction: 'desc' }],
  },
  def: {
    basicColumns: [
      'def_tackles_solo', 'def_tackles_with_assist', 'def_tackles_for_loss',
      'def_sacks', 'def_qb_hits', 'def_interceptions', 'def_pass_defended',
      'def_fumbles_forced', 'def_tds',
    ],
    basicSort: [{ field: 'def_tackles_solo', direction: 'desc' }],
    advancedColumns: null,
    advancedSort: [],
    advancedUnavailableReason:
      "This dataset doesn't include efficiency metrics for individual defenders — only counting stats (tackles, sacks, takeaways).",
  },
  st: {
    basicColumns: [
      'fg_made', 'fg_att', 'fg_pct', 'fg_long',
      'pat_made', 'pat_att',
      'pt_att', 'pt_yards', 'pt_net_yards',
    ],
    basicSort: [{ field: 'fg_made', direction: 'desc' }],
    advancedColumns: null,
    advancedSort: [],
    advancedUnavailableReason: "There isn't an efficiency metric that applies across kicking and punting together.",
  },
}

export function getStatFamily(positionPillId: string): StatFamily {
  return FAMILIES[positionPillId] ?? FAMILIES.all
}

export function basicColumnsFor(positionPillId: string, hasWeek: boolean): string[] {
  const identity = hasWeek ? IDENTITY_WEEKLY : IDENTITY_SEASON
  return [...identity, ...getStatFamily(positionPillId).basicColumns]
}

export function advancedColumnsFor(positionPillId: string, hasWeek: boolean): string[] | null {
  const family = getStatFamily(positionPillId)
  if (!family.advancedColumns) return null
  const identity = hasWeek ? IDENTITY_WEEKLY : IDENTITY_SEASON
  return [...identity, ...family.advancedColumns]
}

export const FANTASY_COLUMNS = ['fantasy_points', 'fantasy_points_ppr']
export const FANTASY_SORT: SortSpec[] = [{ field: 'fantasy_points_ppr', direction: 'desc' }]

export function fantasyColumnsFor(hasWeek: boolean): string[] {
  const identity = hasWeek ? IDENTITY_WEEKLY : IDENTITY_SEASON
  return [...identity, ...FANTASY_COLUMNS]
}

export type StatTab = 'basic' | 'advanced' | 'fantasy' | 'custom'

export const STAT_TAB_LABELS: Record<StatTab, string> = {
  basic: 'Basic',
  advanced: 'Advanced',
  fantasy: 'Fantasy',
  custom: 'Custom',
}
