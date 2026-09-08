"""Six derived tables that keep the value of 27 seasons of plays without keeping
27 seasons of plays.

Play-by-play is the only dataset here that cannot live in the database whole: the
projection alone is roughly 55 MB per six seasons, and the site wants drive charts,
win-probability curves and career splits back to 1999. So the plays are read once,
per season, and reduced to the six narrow tables below — together a few tens of
megabytes for the whole window, and none of them needs a play scan at request time.

Three constraints shape everything in this module.

**One season in flight at a time.** `derive_season` asks the loader for one
season's relation, writes every derived row for it, checkpoints, and moves on.
Peak memory is a function of the widest single season, never of how many seasons
the build covers. `derive_all` is a loop, deliberately, not a UNION.

**Delete-then-insert, keyed on season.** Every table carries a `season` column and
every write removes that season first, so re-deriving a season is idempotent and a
half-finished build can simply be re-run. Nothing here is append-only.

**Counts, never rates.** Not one column in these tables is a ratio. A rate is
`SUM(numerator) / SUM(denominator)` computed at read time, which is the only way a
career split can be a SUM over season rows instead of an average of averages
(SPEC 0.7). `derived_player_season_situational` exists precisely so that a
fifteen-season career split is 240 small rows rather than 700,000 plays.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .alignment import canonical_team_sql
from .buckets import BUCKETS, ROLES

logger = logging.getLogger(__name__)

# Points kept per game in the win-probability series. The chart is ~700px wide, so
# more points than this are pixels nobody can see, stored for every game since 1999.
# The sampler below keeps exactly this many for a game with more plays, plus every
# scoring play, because a WP curve that skips the touchdown is a lie about the game.
WP_POINTS_PER_GAME = 120


@dataclass(frozen=True)
class DerivedTable:
    """One derived table: its columns, its types, and the SELECT that fills it."""

    name: str
    #: (column, DuckDB type), in the order the SELECT produces them.
    columns: tuple[tuple[str, str], ...]
    #: (relation, season) -> a SELECT producing exactly `columns`.
    build: Callable[[str, int], str]
    description: str = ""

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.columns)

    def ddl(self) -> str:
        body = ", ".join(f'"{name}" {dtype}' for name, dtype in self.columns)
        return f"CREATE TABLE IF NOT EXISTS {self.name} ({body})"

    def insert_sql(self, relation: str, season: int) -> str:
        cols = ", ".join(f'"{c}"' for c in self.column_names)
        return f"INSERT INTO {self.name} ({cols}) {self.build(relation, season)}"


# --- SQL fragments -----------------------------------------------------------


def _source(relation: str, season: int) -> str:
    """The one CTE every derived table starts from.

    The season filter is repeated even though `pbp_relation` already scopes a
    resident season: an attached season file holds one season, the resident table
    holds six, and a derived table that quietly picked up a neighbouring season
    would break the delete-then-insert contract in a way no row count would show.
    """
    return f"p AS (SELECT * FROM {relation} AS src WHERE season = {int(season)})"


def _seconds_sql(column: str) -> str:
    """"3:20" -> 200. NULL for anything that does not parse, never 0.

    A drive with an unparsed clock is a drive whose time of possession we do not
    know; writing 0 would make it look like a three-and-out that took no time.
    """
    return (
        f"try_cast(split_part({column}, ':', 1) AS INTEGER) * 60"
        f" + try_cast(split_part({column}, ':', 2) AS INTEGER)"
    )


def _yardline_100_sql(side: str, number: str, plain: str, posteam: str) -> str:
    """Resolve a text yard line ("KC 25", "50") to yards from the opponent goal.

    The text says which side of the field the ball is on, not which direction the
    drive is going, so the same string means two different things depending on who
    has it: "KC 25" is 75 yards out when Kansas City is on offence and 25 when it
    is not (SPEC 0.6). Midfield carries no team code at all.

    The side code is canonicalised because these are free-text strings that were
    never touched by the loader's team-code normalisation, so a 2015 drive can say
    STL while `posteam` — normalised at load — says LA.
    """
    return (
        "CASE"
        f" WHEN {plain} IS NOT NULL THEN {plain}"
        f" WHEN {number} IS NULL THEN NULL"
        f" WHEN {canonical_team_sql(side)} = {posteam} THEN 100 - {number}"
        f" ELSE {number} END"
    )


def _parsed_yard_lines(prefix: str, column: str) -> str:
    """The three pieces `_yardline_100_sql` needs, extracted once each."""
    return (
        f"nullif(split_part(trim({column}), ' ', 1), '') AS {prefix}_side,"
        f" try_cast(nullif(split_part(trim({column}), ' ', 2), '') AS INTEGER) AS {prefix}_num,"
        f" try_cast(trim({column}) AS INTEGER) AS {prefix}_plain"
    )


# --- derived_drives ----------------------------------------------------------


def _drives_sql(relation: str, season: int) -> str:
    # Drive-level columns repeat identically on every play of the drive, so one
    # row per drive is an aggregate. arg_min(col, play_id) rather than any_value:
    # it takes the value from the drive's own first play deterministically, and it
    # steps over the NULL posteam that end-of-quarter rows carry.
    return f"""
WITH {_source(relation, season)},
d AS (
  SELECT
    game_id,
    {int(season)} AS season,
    arg_min(CAST(week AS INTEGER), play_id) AS week,
    CAST(fixed_drive AS INTEGER) AS drive,
    arg_min(posteam, play_id) AS posteam,
    arg_min(defteam, play_id) AS defteam,
    arg_min(CAST(drive_play_count AS INTEGER), play_id) AS plays,
    arg_min(drive_time_of_possession, play_id) AS time_of_possession,
    arg_min(CAST(drive_first_downs AS INTEGER), play_id) AS first_downs,
    arg_min(fixed_drive_result, play_id) AS result,
    max(CAST(drive_ended_with_score AS INTEGER)) AS scored,
    arg_min(drive_start_yard_line, play_id) AS start_yard_line,
    arg_min(drive_end_yard_line, play_id) AS end_yard_line
  FROM p
  WHERE fixed_drive IS NOT NULL
  GROUP BY game_id, CAST(fixed_drive AS INTEGER)
),
y AS (
  SELECT d.*,
    {_parsed_yard_lines('s', 'start_yard_line')},
    {_parsed_yard_lines('e', 'end_yard_line')}
  FROM d
)
SELECT
  game_id, season, week, drive, posteam, defteam, plays,
  time_of_possession,
  {_seconds_sql('time_of_possession')} AS top_seconds,
  first_downs, result,
  scored = 1 AS scored,
  start_yard_line, end_yard_line,
  {_yardline_100_sql('s_side', 's_num', 's_plain', 'posteam')} AS start_yardline_100,
  {_yardline_100_sql('e_side', 'e_num', 'e_plain', 'posteam')} AS end_yardline_100
FROM y
"""


# --- derived_scoring_plays ---------------------------------------------------


def _scoring_plays_sql(relation: str, season: int) -> str:
    # nflfastR's running totals are the score *at the start of the play* — the same
    # state the win-probability model is fed, and consistent with `score_differential`,
    # which its own dictionary defines that way. The score a scoring play produced is
    # therefore on the *next* row, which is why this reaches forward with LEAD rather
    # than differencing backwards. Games end on a non-play row (END GAME), so the
    # fallback only fires on a truncated file, not on a walk-off touchdown.
    return f"""
WITH {_source(relation, season)},
s AS (
  SELECT
    game_id,
    {int(season)} AS season,
    CAST(week AS INTEGER) AS week,
    CAST(play_id AS INTEGER) AS play_id,
    CAST(qtr AS INTEGER) AS qtr,
    CAST(quarter_seconds_remaining AS INTEGER) AS quarter_seconds_remaining,
    CAST(game_seconds_remaining AS INTEGER) AS game_seconds_remaining,
    posteam, defteam, td_team, td_player_id, td_player_name, play_type, "desc",
    COALESCE(CAST(sp AS INTEGER), 0) AS sp,
    COALESCE(CAST(touchdown AS INTEGER), 0) AS touchdown,
    COALESCE(CAST(safety AS INTEGER), 0) AS safety,
    COALESCE(CAST(extra_point_attempt AS INTEGER), 0) AS extra_point_attempt,
    COALESCE(CAST(two_point_attempt AS INTEGER), 0) AS two_point_attempt,
    field_goal_result,
    CAST(total_home_score AS INTEGER) AS home_before,
    CAST(total_away_score AS INTEGER) AS away_before,
    COALESCE(
      lead(CAST(total_home_score AS INTEGER)) OVER w,
      CAST(total_home_score AS INTEGER)
    ) AS home_after,
    COALESCE(
      lead(CAST(total_away_score AS INTEGER)) OVER w,
      CAST(total_away_score AS INTEGER)
    ) AS away_after
  FROM p
  WINDOW w AS (PARTITION BY game_id ORDER BY play_id)
)
SELECT
  game_id, season, week, play_id, qtr,
  quarter_seconds_remaining, game_seconds_remaining,
  CASE
    WHEN safety = 1 THEN defteam
    WHEN td_team IS NOT NULL THEN td_team
    ELSE posteam
  END AS scoring_team,
  posteam,
  CASE
    WHEN touchdown = 1 THEN 'touchdown'
    WHEN safety = 1 THEN 'safety'
    WHEN extra_point_attempt = 1 THEN 'extra_point'
    WHEN two_point_attempt = 1 THEN 'two_point'
    WHEN field_goal_result = 'made' THEN 'field_goal'
    ELSE 'other'
  END AS scoring_type,
  td_player_id, td_player_name, play_type, "desc" AS description,
  home_after AS home_score,
  away_after AS away_score
FROM s
WHERE sp = 1 OR home_after > home_before OR away_after > away_before
"""


# --- derived_wp_series -------------------------------------------------------


def _wp_series_sql(relation: str, season: int) -> str:
    # Even sampling rather than "every nth play": floor(rn*T/n) steps up exactly T
    # times across a game, so a game with more than T plays keeps exactly T evenly
    # spaced points and a short one keeps all of them. Scoring plays are kept on top
    # of the sample — they are the shape of the curve, and there are only a handful.
    target = int(WP_POINTS_PER_GAME)
    return f"""
WITH {_source(relation, season)},
r AS (
  SELECT
    game_id,
    CAST(play_id AS INTEGER) AS play_id,
    CAST(game_seconds_remaining AS INTEGER) AS game_seconds_remaining,
    CAST(home_wp AS DOUBLE) AS home_wp,
    CAST(total_home_score AS INTEGER) AS home_score,
    CAST(total_away_score AS INTEGER) AS away_score,
    COALESCE(CAST(sp AS INTEGER), 0) AS sp,
    row_number() OVER (PARTITION BY game_id ORDER BY play_id) AS rn,
    count(*) OVER (PARTITION BY game_id) AS n
  FROM p
  WHERE home_wp IS NOT NULL
)
SELECT
  game_id, {int(season)} AS season, play_id, game_seconds_remaining,
  home_wp, home_score, away_score
FROM r
WHERE rn = 1
   OR sp = 1
   OR floor(rn * {target} / n) > floor((rn - 1) * {target} / n)
"""


# --- derived_game_team_stats -------------------------------------------------


def _game_team_stats_sql(relation: str, season: int) -> str:
    # Two rows per game, built from a two-row team frame joined back to the plays,
    # because a team's line is not one filter: offence is `posteam = team` while
    # penalties are `penalty_team = team` and happen on the opponent's snaps too.
    # Every column here is a count or a total; EPA per play and success rate are the
    # reader's division, not ours.
    return f"""
WITH {_source(relation, season)},
teams AS (
  SELECT DISTINCT game_id, home_team AS team, away_team AS opponent
  FROM p WHERE home_team IS NOT NULL
  UNION ALL
  SELECT DISTINCT game_id, away_team AS team, home_team AS opponent
  FROM p WHERE away_team IS NOT NULL
),
drive_rows AS (
  SELECT
    game_id,
    CAST(fixed_drive AS INTEGER) AS drive,
    arg_min(posteam, play_id) AS team,
    {_seconds_sql("arg_min(drive_time_of_possession, play_id)")} AS top_seconds
  FROM p
  WHERE fixed_drive IS NOT NULL
  GROUP BY game_id, CAST(fixed_drive AS INTEGER)
),
drive_roll AS (
  SELECT game_id, team, count(*) AS drives, sum(top_seconds) AS top_seconds
  FROM drive_rows
  WHERE team IS NOT NULL
  GROUP BY game_id, team
),
agg AS (
  SELECT
    t.game_id,
    {int(season)} AS season,
    max(CAST(p.week AS INTEGER)) AS week,
    t.team, t.opponent,
    count(*) FILTER (
      WHERE p.posteam = t.team AND (p.pass = 1 OR p.rush = 1)
    ) AS plays,
    sum(CAST(p.yards_gained AS DOUBLE)) FILTER (
      WHERE p.posteam = t.team AND (p.pass = 1 OR p.rush = 1)
    ) AS yards,
    sum(CAST(p.epa AS DOUBLE)) FILTER (
      WHERE p.posteam = t.team AND (p.pass = 1 OR p.rush = 1)
    ) AS epa_total,
    sum(CAST(p.success AS INTEGER)) FILTER (
      WHERE p.posteam = t.team AND (p.pass = 1 OR p.rush = 1)
    ) AS successes,
    sum(CAST(p.pass AS INTEGER)) FILTER (WHERE p.posteam = t.team) AS dropbacks,
    sum(CAST(p.first_down AS INTEGER)) FILTER (WHERE p.posteam = t.team) AS first_downs,
    sum(
      COALESCE(CAST(p.interception AS INTEGER), 0)
      + COALESCE(CAST(p.fumble_lost AS INTEGER), 0)
    ) FILTER (WHERE p.posteam = t.team) AS turnovers,
    count(*) FILTER (WHERE p.penalty_team = t.team) AS penalties,
    sum(CAST(p.penalty_yards AS DOUBLE)) FILTER (
      WHERE p.penalty_team = t.team
    ) AS penalty_yards
  FROM teams t
  JOIN p ON p.game_id = t.game_id
  GROUP BY t.game_id, t.team, t.opponent
)
SELECT
  a.game_id, a.season, a.week, a.team, a.opponent,
  a.plays, a.yards, a.epa_total, a.successes, a.dropbacks, a.first_downs,
  a.turnovers, a.penalties, a.penalty_yards,
  COALESCE(d.top_seconds, 0) AS top_seconds,
  COALESCE(d.drives, 0) AS drives
FROM agg a
LEFT JOIN drive_roll d ON d.game_id = a.game_id AND d.team = a.team
"""


# --- derived_player_game_epa -------------------------------------------------


def _role_rows_sql(columns: str) -> str:
    """One SELECT per offensive role, unioned into a long player-play frame."""
    parts = []
    for r in ROLES:
        parts.append(
            f"  SELECT {r.id_column} AS gsis_id, '{r.key}' AS role,"
            f" {r.touchdown_column} AS role_touchdown, {columns}"
            f"  FROM p WHERE {r.id_column} IS NOT NULL"
        )
    return "\n  UNION ALL\n".join(parts)


def _player_game_epa_sql(relation: str, season: int) -> str:
    # air_yards is NULL on every play before 2006 (SPEC 0.2), and SUM over an
    # all-NULL group is NULL in DuckDB — which is exactly what we want stored. A
    # COALESCE(...,0) here would turn "nobody charted it" into "he threw it at the
    # line of scrimmage" for seven seasons. Rushing rows are NULL for the same
    # reason in every season: a run has no air yards.
    columns = (
        "game_id, play_id, week, posteam, epa, success, air_yards"
    )
    return f"""
WITH {_source(relation, season)},
r AS (
{_role_rows_sql(columns)}
)
SELECT
  game_id,
  {int(season)} AS season,
  arg_min(CAST(week AS INTEGER), play_id) AS week,
  gsis_id,
  role,
  arg_min(posteam, play_id) AS team,
  count(*) AS plays,
  sum(CAST(epa AS DOUBLE)) AS epa_total,
  sum(CAST(success AS INTEGER)) AS successes,
  sum(CAST(air_yards AS DOUBLE)) AS air_yards_total
FROM r
GROUP BY game_id, gsis_id, role
"""


# --- derived_player_season_situational ---------------------------------------


def _situational_sql(relation: str, season: int) -> str:
    # Sixteen aggregates over one role frame, unioned. The buckets overlap, so this
    # is deliberately not a GROUP BY over a bucket column: a play belongs to several
    # of them and each one counts it once.
    columns = (
        "play_id, epa, success, yards_gained, first_down,"
        " down, ydstogo, yardline_100, qtr, half_seconds_remaining,"
        " score_differential, wp"
    )
    branches = []
    for b in BUCKETS:
        branches.append(
            f"""  SELECT
    {int(season)} AS season, gsis_id, role, '{b.key}' AS bucket,
    count(*) AS plays,
    sum(CAST(epa AS DOUBLE)) AS epa_total,
    sum(CAST(success AS INTEGER)) AS successes,
    sum(CAST(yards_gained AS DOUBLE)) AS yards,
    sum(COALESCE(CAST(role_touchdown AS INTEGER), 0)) AS touchdowns,
    sum(CAST(first_down AS INTEGER)) AS first_downs
  FROM r
  WHERE {b.predicate}
  GROUP BY gsis_id, role"""
        )
    head = f"""
WITH {_source(relation, season)},
r AS (
{_role_rows_sql(columns)}
)
"""
    return head + "\n  UNION ALL\n".join(branches) + "\n"


TABLES: tuple[DerivedTable, ...] = (
    DerivedTable(
        name="derived_drives",
        description="One row per drive, with the text yard lines resolved to integers.",
        columns=(
            ("game_id", "VARCHAR"),
            ("season", "INTEGER"),
            ("week", "INTEGER"),
            ("drive", "INTEGER"),
            ("posteam", "VARCHAR"),
            ("defteam", "VARCHAR"),
            ("plays", "INTEGER"),
            ("time_of_possession", "VARCHAR"),
            ("top_seconds", "INTEGER"),
            ("first_downs", "INTEGER"),
            ("result", "VARCHAR"),
            ("scored", "BOOLEAN"),
            ("start_yard_line", "VARCHAR"),
            ("end_yard_line", "VARCHAR"),
            ("start_yardline_100", "INTEGER"),
            ("end_yardline_100", "INTEGER"),
        ),
        build=_drives_sql,
    ),
    DerivedTable(
        name="derived_scoring_plays",
        description="Every play that changed the score, with the score it produced.",
        columns=(
            ("game_id", "VARCHAR"),
            ("season", "INTEGER"),
            ("week", "INTEGER"),
            ("play_id", "INTEGER"),
            ("qtr", "INTEGER"),
            ("quarter_seconds_remaining", "INTEGER"),
            ("game_seconds_remaining", "INTEGER"),
            ("scoring_team", "VARCHAR"),
            ("posteam", "VARCHAR"),
            ("scoring_type", "VARCHAR"),
            ("td_player_id", "VARCHAR"),
            ("td_player_name", "VARCHAR"),
            ("play_type", "VARCHAR"),
            ("description", "VARCHAR"),
            ("home_score", "INTEGER"),
            ("away_score", "INTEGER"),
        ),
        build=_scoring_plays_sql,
    ),
    DerivedTable(
        name="derived_wp_series",
        description="A downsampled win-probability curve per game.",
        columns=(
            ("game_id", "VARCHAR"),
            ("season", "INTEGER"),
            ("play_id", "INTEGER"),
            ("game_seconds_remaining", "INTEGER"),
            ("home_wp", "DOUBLE"),
            ("home_score", "INTEGER"),
            ("away_score", "INTEGER"),
        ),
        build=_wp_series_sql,
    ),
    DerivedTable(
        name="derived_game_team_stats",
        description="Two rows per game: one team's counted production.",
        columns=(
            ("game_id", "VARCHAR"),
            ("season", "INTEGER"),
            ("week", "INTEGER"),
            ("team", "VARCHAR"),
            ("opponent", "VARCHAR"),
            ("plays", "INTEGER"),
            ("yards", "DOUBLE"),
            ("epa_total", "DOUBLE"),
            ("successes", "INTEGER"),
            ("dropbacks", "INTEGER"),
            ("first_downs", "INTEGER"),
            ("turnovers", "INTEGER"),
            ("penalties", "INTEGER"),
            ("penalty_yards", "DOUBLE"),
            ("top_seconds", "INTEGER"),
            ("drives", "INTEGER"),
        ),
        build=_game_team_stats_sql,
    ),
    DerivedTable(
        name="derived_player_game_epa",
        description="Per player, game and offensive role: plays, EPA, successes, air yards.",
        columns=(
            ("game_id", "VARCHAR"),
            ("season", "INTEGER"),
            ("week", "INTEGER"),
            ("gsis_id", "VARCHAR"),
            ("role", "VARCHAR"),
            ("team", "VARCHAR"),
            ("plays", "INTEGER"),
            ("epa_total", "DOUBLE"),
            ("successes", "INTEGER"),
            ("air_yards_total", "DOUBLE"),
        ),
        build=_player_game_epa_sql,
    ),
    DerivedTable(
        name="derived_player_season_situational",
        description="Per player, season, role and bucket: counts only, so careers pool.",
        columns=(
            ("season", "INTEGER"),
            ("gsis_id", "VARCHAR"),
            ("role", "VARCHAR"),
            ("bucket", "VARCHAR"),
            ("plays", "INTEGER"),
            ("epa_total", "DOUBLE"),
            ("successes", "INTEGER"),
            ("yards", "DOUBLE"),
            ("touchdowns", "INTEGER"),
            ("first_downs", "INTEGER"),
        ),
        build=_situational_sql,
    ),
)

BY_NAME: dict[str, DerivedTable] = {t.name: t for t in TABLES}


def derived_tables() -> tuple[str, ...]:
    """The table names, for `/api/coverage` to report."""
    return tuple(t.name for t in TABLES)


def table(name: str) -> DerivedTable:
    try:
        return BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"Unknown derived table {name!r}") from exc


def ensure_tables(cur) -> None:
    """Create any derived table that does not exist yet. Safe to call always."""
    for derived in TABLES:
        cur.execute(derived.ddl())


def insert_season(
    cur,
    relation: str,
    season: int,
    tables: Sequence[DerivedTable] = TABLES,
) -> dict[str, int]:
    """Rewrite one season of derived rows from `relation`, and count them.

    Delete-then-insert per table, so calling this twice for the same season leaves
    the same rows rather than doubling them. Taking the relation as an argument
    rather than a loader is what lets the tests drive these transforms over a
    hand-built table with plays the fixture seasons do not contain.
    """
    written: dict[str, int] = {}
    for derived in tables:
        cur.execute(f"DELETE FROM {derived.name} WHERE season = ?", [season])
        cur.execute(derived.insert_sql(relation, season))
        written[derived.name] = cur.execute(
            f"SELECT count(*) FROM {derived.name} WHERE season = ?", [season]
        ).fetchone()[0]
    return written


def derive_season(loader, season: int) -> dict[str, int]:
    """Build every derived table for one season, then release it.

    Raises `loader.SeasonBusy` if two other seasons are already materialising —
    the build loop is sequential, so that only happens when a request beat it to
    the cache.
    """
    relation = loader.pbp_relation(season)
    cur = loader.cursor()
    ensure_tables(cur)
    written = insert_season(cur, relation, season)
    # Between seasons, not at the end: without it the written pages pile up as
    # dirty blocks until the commit, and a 27-season build fails at the finish
    # line rather than streaming.
    loader._checkpoint(cur)
    logger.info(
        "Derived %s: %s",
        season,
        ", ".join(f"{name} {rows}" for name, rows in written.items()),
    )
    return written


def derive_all(loader, seasons: Iterable[int]) -> dict[int, dict[str, int]]:
    """Derive a run of seasons, one at a time.

    A loop rather than one wide statement on purpose: peak memory must be a
    function of the largest season, not of how many seasons were asked for.
    """
    results: dict[int, dict[str, int]] = {}
    for season in seasons:
        results[season] = derive_season(loader, season)
    return results
