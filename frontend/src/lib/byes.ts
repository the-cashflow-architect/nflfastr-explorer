/**
 * Whether a week's idle clubs are worth naming.
 *
 * A postseason week leaves most of the league at home, and listing thirty clubs
 * as "on bye" describes a season that is over rather than a week off. Six is the
 * most any real regular-season week produces, so anything much beyond that is
 * the calendar talking, not a bye.
 *
 * One helper rather than a constant copied into each scoreboard: the rule was
 * written three times and applied in two of them.
 */
const MAX_REAL_BYES = 8

export function byesWorthNaming(teams: readonly string[] | null | undefined): string[] {
  if (!teams?.length || teams.length > MAX_REAL_BYES) return []
  return [...teams]
}
