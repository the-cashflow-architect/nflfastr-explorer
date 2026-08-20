import type { QuickSuggestion } from '../components/FilterBar'

const range = (min: number | null, max: number | null) => ({ min, max })
const one = (defId: string, value: unknown): QuickSuggestion['filters'] => [{ defId, value }]

/** One-click filter shortcuts, contextual to the position currently selected. */
export function quickSuggestionsFor(positionId: string): QuickSuggestion[] {
  switch (positionId) {
    case 'qb':
      return [
        { label: '300+ Pass Yds', filters: one('passing_yards', range(300, null)) },
        { label: 'Multi-TD Game', filters: one('passing_tds', range(2, null)) },
        { label: 'No INTs', filters: one('passing_interceptions', range(null, 0)) },
      ]
    case 'rb':
      return [
        { label: '100+ Rush Yds', filters: one('rushing_yards', range(100, null)) },
        { label: 'Rushing TD', filters: one('rushing_tds', range(1, null)) },
      ]
    case 'wr':
    case 'te':
      return [
        { label: '100+ Rec Yds', filters: one('receiving_yards', range(100, null)) },
        { label: '8+ Receptions', filters: one('receptions', range(8, null)) },
      ]
    case 'def':
      return [
        { label: '10+ Tackles', filters: one('def_tackles_solo', range(10, null)) },
        { label: 'Sack', filters: one('def_sacks', range(1, null)) },
        { label: 'Interception', filters: one('def_interceptions', range(1, null)) },
      ]
    case 'st':
      return [{ label: '3+ FGs Made', filters: one('fg_made', range(3, null)) }]
    default:
      return []
  }
}

/**
 * The situations people ask for most in play-by-play — this replaces the
 * old standalone "presets" list, which only worked for Plays and used a
 * separate mechanism from every other filter. These are just filters,
 * pre-filled; they show as normal removable/editable chips once applied.
 */
export const PLAY_QUICK_SUGGESTIONS: QuickSuggestion[] = [
  { label: 'Red Zone', filters: one('yardline_100', range(null, 20)) },
  { label: 'Goal Line', filters: one('yardline_100', range(null, 6)) },
  { label: '3rd Down', filters: one('down', [3]) },
  { label: '4th Down', filters: one('down', [4]) },
  {
    label: 'Close & Late',
    filters: [
      { defId: 'qtr', value: [4] },
      { defId: 'score_diff', value: range(-10, 10) },
    ],
  },
  { label: 'Explosive Play', filters: one('yards_gained', range(20, null)) },
  { label: 'Touchdown', filters: one('touchdown', true) },
  { label: 'High EPA', filters: one('min_epa', range(2, null)) },
]
