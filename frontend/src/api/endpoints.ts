import { useQuery, type UseQueryOptions, type UseQueryResult } from '@tanstack/react-query'
import { api } from './client'
import type { operations } from './schema'
import { CACHE_MAX_AGE } from '../lib/offline'

/**
 * Every call the product makes to the API, typed from the server's own schema.
 *
 * The types here are *generated* — `npm run gen:api` re-derives `schema.d.ts`
 * from the running app's OpenAPI document. That is the point: a hand-written
 * client type agrees with the server exactly once, on the day it is written, and
 * after that a renamed field is a blank cell in production rather than a red
 * build. Here it is a compile error in the file that has to change.
 *
 * Pages import the hooks, never `fetch`. One place decides caching, one place
 * decides how a failure surfaces.
 */

type Ok<T extends keyof operations> = operations[T] extends {
  responses: { 200: { content: { 'application/json': infer R } } }
}
  ? R
  : never

type Params<T extends keyof operations> = operations[T] extends { parameters: { query?: infer Q } }
  ? Q
  : never

export type Coverage = Ok<'get_coverage_api_coverage_get'>
export type SearchResults = Ok<'get_search_api_search_get'>
export type PlayerIndex = Ok<'get_players_api_players_get'>
export type PlayerHub = Ok<'get_player_api_players__gsis_id__get'>
export type PlayerPercentiles = Ok<'get_player_percentiles_api_players__gsis_id__percentiles_get'>
export type PlayerGameLog = Ok<'get_player_gamelog_api_players__gsis_id__gamelog_get'>
export type PlayerSplits = Ok<'get_player_splits_api_players__gsis_id__splits_get'>
export type PlayerAdvanced = Ok<'get_player_advanced_api_players__gsis_id__advanced_get'>
export type TeamIndex = Ok<'get_team_index_api_teams_get'>
export type Franchise = Ok<'get_franchise_api_teams__abbr__get'>
export type TeamSeason = Ok<'get_team_season_api_teams__abbr___season__get'>
export type TeamRoster = Ok<'get_team_roster_api_teams__abbr___season__roster_get'>
export type Game = Ok<'get_game_api_games__game_id__get'>
export type GamePlays = Ok<'get_game_plays_api_games__game_id__plays_get'>
export type SeasonIndex = Ok<'get_season_index_api_seasons_get'>
export type SeasonHub = Ok<'get_season_hub_api_seasons__season__get'>
export type Standings = Ok<'get_season_standings_api_seasons__season__standings_get'>
export type WeekScoreboard = Ok<'get_week_scoreboard_api_seasons__season__week__week__get'>
export type LeadersIndex = Ok<'get_leaders_index_api_leaders_get'>
export type Leaderboard = Ok<'get_leaderboard_api_leaders__category___stat__get'>
export type DraftIndex = Ok<'get_draft_index_api_draft_get'>
export type DraftClass = Ok<'get_draft_class_api_draft__year__get'>

export type PlayerIndexParams = Params<'get_players_api_players_get'>
export type PlayerGameLogParams = Params<'get_player_gamelog_api_players__gsis_id__gamelog_get'>
export type PlayerSplitsParams = Params<'get_player_splits_api_players__gsis_id__splits_get'>
export type PlayerAdvancedParams = Params<'get_player_advanced_api_players__gsis_id__advanced_get'>
export type PlayerPercentileParams = Params<'get_player_percentiles_api_players__gsis_id__percentiles_get'>
export type GamePlaysParams = Params<'get_game_plays_api_games__game_id__plays_get'>
export type LeaderboardParams = Params<'get_leaderboard_api_leaders__category___stat__get'>
export type StandingsParams = Params<'get_season_standings_api_seasons__season__standings_get'>
export type TeamIndexParams = Params<'get_team_index_api_teams_get'>

/** Reference data changes weekly at most; an hour of cache costs the visitor nothing. */
const HOUR = 60 * 60 * 1000
// gcTime has to be at least the persisted cache's max age. An entry dropped
// from memory is dropped from the next snapshot written to disk, so a two-hour
// gcTime quietly emptied the saved cache of anything not viewed in the last two
// hours — TanStack's persistence docs call this out as the classic mistake.
const REFERENCE = { staleTime: HOUR, gcTime: CACHE_MAX_AGE }

type Extra<T> = Omit<UseQueryOptions<T, Error, T, readonly unknown[]>, 'queryKey' | 'queryFn'>

function reference<T>(key: readonly unknown[], path: string, params?: Record<string, unknown>, extra?: Extra<T>) {
  return { queryKey: key, queryFn: () => api<T>(path, params), ...REFERENCE, ...extra }
}

/**
 * useQuery for reference pages: when a refresh fails, keep showing what it has.
 *
 * React Query v5 keeps the data when a refetch fails but flips the query to an
 * error, and QueryBoundary — rightly — renders an error in place of the page.
 * With a saved cache that is the wrong trade: the visitor on the subway, or a
 * reviewer on the day the server is down, had real figures on screen and gets a
 * connection error instead.
 *
 * So a failure only surfaces as the page's error when there is nothing to show.
 * It is not hidden: the FreshnessBanner reads the same query and says the
 * figures could not be updated, and when they were from. With no data at all,
 * the error reaches QueryBoundary exactly as before.
 */
function useReferenceQuery<T>(options: UseQueryOptions<T, Error, T, readonly unknown[]>): UseQueryResult<T, Error> {
  const result = useQuery(options)
  if (result.error && result.data !== undefined) {
    return { ...result, error: null } as unknown as UseQueryResult<T, Error>
  }
  return result
}

export const useCoverageQuery = () => useReferenceQuery(reference<Coverage>(['coverage'], '/api/coverage'))

/** One search result. Groups arrive in a fixed order and may be empty. */
export type SearchItem = NonNullable<SearchResults['groups']>[number]['items'][number]

export const searchQuery = (q: string, limit = 8) =>
  reference<SearchResults>(['search', q, limit], '/api/search', { q, limit }, {
    enabled: q.trim().length >= 2,
    // A search is typed, not browsed: half a minute is plenty and keeps the
    // palette instant when someone backspaces a character.
    staleTime: 30_000,
  })

export const usePlayerIndex = (params: PlayerIndexParams) =>
  useReferenceQuery(reference<PlayerIndex>(['players', params], '/api/players', params ?? {}))

export const usePlayerHub = (gsisId: string | undefined) =>
  useReferenceQuery(reference<PlayerHub>(['player', gsisId], `/api/players/${gsisId}`, undefined, { enabled: !!gsisId }))

export const usePlayerPercentiles = (gsisId: string | undefined, params?: PlayerPercentileParams) =>
  useReferenceQuery(
    reference<PlayerPercentiles>(['player-percentiles', gsisId, params], `/api/players/${gsisId}/percentiles`, params ?? {}, {
      enabled: !!gsisId,
    }),
  )

export const usePlayerGameLog = (gsisId: string | undefined, params?: PlayerGameLogParams) =>
  useReferenceQuery(
    reference<PlayerGameLog>(['player-gamelog', gsisId, params], `/api/players/${gsisId}/gamelog`, params ?? {}, {
      enabled: !!gsisId,
    }),
  )

export const usePlayerSplits = (gsisId: string | undefined, params?: PlayerSplitsParams) =>
  useReferenceQuery(
    reference<PlayerSplits>(['player-splits', gsisId, params], `/api/players/${gsisId}/splits`, params ?? {}, {
      enabled: !!gsisId,
    }),
  )

export const usePlayerAdvanced = (gsisId: string | undefined, params?: PlayerAdvancedParams) =>
  useReferenceQuery(
    reference<PlayerAdvanced>(['player-advanced', gsisId, params], `/api/players/${gsisId}/advanced`, params ?? {}, {
      enabled: !!gsisId,
    }),
  )

export const useTeamIndex = (params?: TeamIndexParams) =>
  useReferenceQuery(reference<TeamIndex>(['teams', params], '/api/teams', params ?? {}))

export const useFranchise = (abbr: string | undefined) =>
  useReferenceQuery(reference<Franchise>(['franchise', abbr], `/api/teams/${abbr}`, undefined, { enabled: !!abbr }))

export const useTeamSeason = (abbr: string | undefined, season: number | undefined) =>
  useReferenceQuery(
    reference<TeamSeason>(['team-season', abbr, season], `/api/teams/${abbr}/${season}`, undefined, {
      enabled: !!abbr && !!season,
    }),
  )

export const useTeamRoster = (abbr: string | undefined, season: number | undefined) =>
  useReferenceQuery(
    reference<TeamRoster>(['team-roster', abbr, season], `/api/teams/${abbr}/${season}/roster`, undefined, {
      enabled: !!abbr && !!season,
    }),
  )

export const useGame = (gameId: string | undefined) =>
  useReferenceQuery(reference<Game>(['game', gameId], `/api/games/${gameId}`, undefined, { enabled: !!gameId }))

export const useGamePlays = (gameId: string | undefined, params?: GamePlaysParams, enabled = true) =>
  useReferenceQuery(
    reference<GamePlays>(['game-plays', gameId, params], `/api/games/${gameId}/plays`, params ?? {}, {
      // The play log is large and lives behind a disclosure, so it is not
      // fetched until somebody opens it.
      enabled: enabled && !!gameId,
      // A season still materialising answers 503; retrying once gives it a
      // moment without turning a slow page into a spinner that never ends.
      retry: 1,
    }),
  )

export const useSeasonIndex = () => useReferenceQuery(reference<SeasonIndex>(['seasons'], '/api/seasons'))

export const useSeasonHub = (season: number | undefined) =>
  useReferenceQuery(reference<SeasonHub>(['season', season], `/api/seasons/${season}`, undefined, { enabled: !!season }))

export const useStandings = (season: number | undefined, params?: StandingsParams) =>
  useReferenceQuery(
    reference<Standings>(['standings', season, params], `/api/seasons/${season}/standings`, params ?? {}, {
      enabled: !!season,
    }),
  )

export const useWeekScoreboard = (season: number | undefined, week: number | undefined) =>
  useReferenceQuery(
    reference<WeekScoreboard>(['week', season, week], `/api/seasons/${season}/week/${week}`, undefined, {
      enabled: !!season && !!week,
    }),
  )

export const useLeadersIndex = () => useReferenceQuery(reference<LeadersIndex>(['leaders'], '/api/leaders'))

export const useLeaderboard = (category: string | undefined, stat: string | undefined, params?: LeaderboardParams) =>
  useReferenceQuery(
    reference<Leaderboard>(['leaderboard', category, stat, params], `/api/leaders/${category}/${stat}`, params ?? {}, {
      enabled: !!category && !!stat,
    }),
  )

export const useDraftIndex = () => useReferenceQuery(reference<DraftIndex>(['draft'], '/api/draft'))

export const useDraftClass = (year: number | undefined) =>
  useReferenceQuery(reference<DraftClass>(['draft-class', year], `/api/draft/${year}`, undefined, { enabled: !!year }))
