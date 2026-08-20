import type { ColumnMeta, FilterDef } from '../types'
import { HIDDEN_CATEGORIES } from '../types'

// Numeric play-by-play columns that are actually 0/1 flags, not quantities —
// "Touchdown: Yes" reads far better than a min/max range on a column that's
// only ever 0 or 1.
const BOOLEAN_FLAG_FIELDS = new Set([
  'pass', 'rush', 'touchdown', 'pass_touchdown', 'rush_touchdown',
  'interception', 'complete_pass', 'sack', 'first_down',
])

const NUMERIC_DTYPE_MARKERS = ['INT', 'FLOAT', 'DOUBLE', 'DECIMAL']

function isNumeric(c: ColumnMeta): boolean {
  return NUMERIC_DTYPE_MARKERS.some((t) => c.dtype.includes(t))
}

/**
 * The backend only curates a handful of filters (season, team, a few search
 * fields). Everything else numeric — every yardage, TD, tackle, or
 * efficiency column — can still be filtered ("at least N", "at most N", or
 * "did this happen") without the backend needing a hand-written FilterDef
 * for each one. This generates the rest from the dataset's own column list.
 */
export function buildFilterDefs(columns: ColumnMeta[], backendDefs: FilterDef[]): FilterDef[] {
  const covered = new Set(backendDefs.map((d) => d.field))
  const generated: FilterDef[] = []

  for (const col of columns) {
    if (covered.has(col.id)) continue
    if (HIDDEN_CATEGORIES.has(col.category)) continue
    if (col.category === 'identity' || col.category === 'time' || col.category === 'team') continue
    if (!isNumeric(col)) continue

    if (BOOLEAN_FLAG_FIELDS.has(col.id)) {
      generated.push({
        id: col.id,
        field: col.id,
        label: col.label,
        type: 'boolean',
        category: col.category,
        depends_on: [],
        description: col.description,
      })
    } else {
      generated.push({
        id: col.id,
        field: col.id,
        label: col.label,
        type: 'range',
        category: col.category,
        depends_on: [],
        description: col.description,
      })
    }
  }

  return [...backendDefs, ...generated]
}
