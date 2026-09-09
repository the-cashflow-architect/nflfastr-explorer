"""One game, answered twice: everything but the plays, and then the plays.

The split is the point. A game page is a dozen small blocks that all come from
narrow tables — the schedule row, the four derived play summaries, a box score,
a snap sheet — and one block, the play log, that is a few hundred wide rows and
may need a season's play-by-play to be materialised first. Loading the second
with the first would make every game page wait on a download it usually does not
need, so `game()` never touches `pbp` and `plays()` is a separate request.

Four rules do the work here.

**Only fields that exist.** The schedule file is read column by column: whatever
`games` actually carries reaches the header, and nothing else does. Attendance,
game duration and TV network are in no verified source, so they are not keys with
null values — they are absent, and `/about/data` says why. The same applies to a
block: no scoring plays means no line score, not a 0-0 grid.

**Context for a single game is a percentile, never a rank.** A team's game is
placed among every team-game in that season ("81st percentile of 544 team-games"),
because ranking one afternoon against thirty-two season totals is a category
error. 1-of-32 ranks belong to team-season pages (SPEC section 3, correction 5).

**Rates are computed here, from counts.** `derived_game_team_stats` stores plays,
EPA totals and successes; EPA per play and success rate are divisions done at read
time and never stored or averaged (SPEC 0.7).

**A scheduled game is not a 0-0 game.** `games` carries the 2026 schedule, whose
rows have no scores. Those games answer with the fixture information they really
have — teams, kickoff, venue, closing line — and `status.played = false`; every
block that would describe a result is absent rather than zeroed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Mapping, Sequence

from .. import sources
from ..config import PBP_RESIDENT_SEASONS, data_dir, latest_season
from ..deps import get_loader
from ..etl import alignment, derived
from ..etl.pbp_derive import DERIVED_NAME as PBP_DERIVED
from ..loader import SeasonBusy

logger = logging.getLogger(__name__)

#: Most win-probability points shipped for the hero chart. The derived series
#: already holds ~120 points per game, so this is a ceiling rather than a routine
#: downsample — it exists so a game with a long overtime cannot ship a thousand.
MAX_WP_POINTS = 200

#: Play-log paging. The 500 cap is the spec's; the default is what a virtualised
#: table can render without the first page being most of the game.
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100


class UnknownGame(LookupError):
    """No game in the schedule file carries this id."""


class SourceUnavailable(RuntimeError):
    """A file this endpoint is built on has not been loaded into this deployment.

    Distinct from "this game has no such data", which is answered by the block
    being absent. This one is a deployment state, not a fact about football.
    """


class SeasonLoading(RuntimeError):
    """This season's plays are still being materialised.

    Carries a sentence naming the season, because "try again" without saying what
    is loading is indistinguishable from a failure.
    """


# --- small shared helpers ----------------------------------------------------


def _loader(loader: Any) -> Any:
    return loader or get_loader()


def _table_columns(loader: Any, table: str) -> set[str]:
    if not loader.table_exists(table):
        return set()
    return {row[0] for row in loader.cursor().execute(f"DESCRIBE {table}").fetchall()}


def _have(loader: Any, source_id: str) -> bool:
    """Is this source loaded? Never raises — an absent source removes a block."""
    table = sources.get(source_id).table
    if loader.table_exists(table):
        return True
    try:
        loader.ensure(source_id)
    except Exception:  # noqa: BLE001 - any download failure is "we don't have it"
        logger.warning(
            "Source %s is unavailable; blocks that need it are omitted",
            source_id,
            exc_info=True,
        )
        return False
    return loader.table_exists(table)


def _first_present(columns: Iterable[str], candidates: Sequence[str]) -> str | None:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    """SUM/SUM, or None. Never 0 for "we could not divide" (SPEC 0.7)."""
    if numerator is None or not denominator:
        return None
    return float(numerator) / float(denominator)


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _bool(value: Any) -> bool | None:
    """0/1/true/false from a CSV column, or None. A missing flag is not False."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "t", "yes"):
            return True
        if text in ("0", "false", "f", "no"):
            return False
        return None
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return None


def _clock(seconds: Any) -> str | None:
    """Quarter seconds remaining as the game clock reads it. None stays None."""
    if seconds is None:
        return None
    total = int(seconds)
    if total < 0:
        return None
    return f"{total // 60}:{total % 60:02d}"


def _period_label(quarter: int | None) -> str:
    if quarter is None:
        return "?"
    if quarter <= 4:
        return str(quarter)
    return "OT" if quarter == 5 else f"OT{quarter - 4}"


def _still_loading(season: int) -> str:
    return (
        f"The {season} season is still loading, try again in a few seconds. "
        "Older seasons are materialised on demand, two at a time."
    )


def _season_is_resident(season: int) -> bool:
    """Do this season's plays live in the main database, or load on demand?

    Read from the same two configuration values the loader itself uses, rather
    than from its private attachment bookkeeping.
    """
    last = latest_season()
    return season > last - PBP_RESIDENT_SEASONS


def _season_materialised(season: int) -> bool:
    """Has this older season already been written to its own database file?"""
    return os.path.exists(os.path.join(data_dir(), f"pbp_{season}.duckdb"))


def _ensure_derived(loader: Any, season: int, table: str) -> bool:
    """Build the play-derived tables if they are stale, and say whether we have one.

    `SeasonBusy` while building is not a failure and not an empty block: it means
    two other seasons are materialising, so the honest answer is to say which
    season the visitor is waiting on.
    """
    try:
        derived.ensure(loader, PBP_DERIVED, table=table)
    except SeasonBusy as exc:
        raise SeasonLoading(_still_loading(season)) from exc
    return loader.table_exists(table)


def _rows(cur: Any, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    """Query results as dicts keyed by the column names the query produced."""
    result = cur.execute(sql, list(params))
    names = [d[0] for d in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


# --- the schedule row --------------------------------------------------------

#: Everything the header may show, and where it comes from. A field absent from
#: the loaded `games` table is absent from the payload: the schedule file has no
#: attendance, no game duration and no TV network, and a null key for one of those
#: would read as "we have this and it is empty" (SPEC section 7).
_HEADER_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("season", "season", "int"),
    ("week", "week", "int"),
    ("game_type", "game_type", "str"),
    ("gameday", "gameday", "date"),
    ("weekday", "weekday", "str"),
    ("gametime", "gametime", "str"),
    ("location", "location", "str"),
    ("stadium", "stadium", "str"),
    ("stadium_id", "stadium_id", "str"),
    ("roof", "roof", "str"),
    ("surface", "surface", "str"),
    ("temp", "temp", "number"),
    ("wind", "wind", "number"),
    ("referee", "referee", "str"),
    ("div_game", "div_game", "bool"),
    ("overtime", "overtime", "bool"),
    ("away_rest", "away_rest", "int"),
    ("home_rest", "home_rest", "int"),
)

#: The closing line, when the schedule file carries it. Odds columns are read the
#: same way — present or absent, never invented.
_BETTING_FIELDS: tuple[tuple[str, str], ...] = (
    ("spread_line", "spread_line"),
    ("total_line", "total_line"),
    ("home_moneyline", "home_moneyline"),
    ("away_moneyline", "away_moneyline"),
    ("home_spread_odds", "home_spread_odds"),
    ("away_spread_odds", "away_spread_odds"),
    ("over_odds", "over_odds"),
    ("under_odds", "under_odds"),
)


def _game_row(loader: Any, game_id: str) -> dict[str, Any]:
    cur = loader.cursor()
    rows = _rows(cur, "SELECT * FROM games WHERE game_id = ?", [game_id])
    if not rows:
        raise UnknownGame(f"No game in our schedule has the id {game_id!r}.")
    return rows[0]


def _cast(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "int":
        return _int(value)
    if kind == "bool":
        return _bool(value)
    if kind == "number":
        return float(value)
    # Dates, kickoff times and stadium ids are strings to the page. DuckDB's CSV
    # sniffer types some of them as DATE or TIME depending on the file, so they
    # are rendered here rather than handed to the serialiser as whatever the
    # sniffer decided.
    return value if isinstance(value, str) else str(value)


def _branding(loader: Any) -> dict[str, dict[str, Any]]:
    """Colours, logos and names by current franchise code.

    `team_conf` and `team_division` are deliberately not read here: that file
    carries present-day membership only (SPEC 0.1), and a game page has no reason
    to ask it about structure.
    """
    if not _have(loader, "teams_meta"):
        return {}
    cur = loader.cursor()
    columns = _table_columns(loader, "teams_meta")
    wanted = [
        c
        for c in (
            "team_abbr", "team_name", "team_nick", "team_color", "team_color2",
            "team_logo_espn", "team_logo_squared", "team_wordmark",
        )
        if c in columns
    ]
    if "team_abbr" not in wanted:
        return {}
    rows = _rows(cur, f"SELECT {', '.join(wanted)} FROM teams_meta", [])
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = alignment.current_code(row.get("team_abbr"))
        if code is None:
            continue
        # The branding file ships the pre-relocation clubs too — STL beside LA,
        # SD beside LAC, OAK beside LV — and they canonicalise onto the same
        # franchise. Last write wins takes whichever the file lists later, which
        # is the historical one, so a present-tense page ends up calling the Rams
        # "St. Louis". A row whose own abbreviation is already the current code
        # wins; historical names come from `alignment.label_in_season`, which has
        # a season to make them right.
        if code in out and row.get("team_abbr") != code:
            continue
        out[code] = {
            "name": row.get("team_name"),
            "nick": row.get("team_nick"),
            "logo": row.get("team_logo_squared") or row.get("team_logo_espn"),
            "logo_espn": row.get("team_logo_espn"),
            "wordmark": row.get("team_wordmark"),
            "colors": {
                "primary": row.get("team_color"),
                "secondary": row.get("team_color2"),
            },
        }
    return out


_RECORD_METHOD = (
    "Record entering this game is computed by us from earlier games of the same "
    "season in the schedule file, counting only games that have been played."
)


def _records_entering(
    loader: Any, season: int, week: int | None, teams: Sequence[str]
) -> dict[str, dict[str, int]]:
    """Each club's W-L-T in this season before this week. Computed, and labelled."""
    if week is None:
        return {}
    cur = loader.cursor()
    rows = _rows(
        cur,
        "SELECT home_team, away_team, home_score, away_score FROM games "
        "WHERE season = ? AND week < ? "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL",
        [season, week],
    )
    out = {team: {"w": 0, "l": 0, "t": 0} for team in teams}
    for row in rows:
        home, away = row["home_team"], row["away_team"]
        home_score, away_score = int(row["home_score"]), int(row["away_score"])
        for team, own, other in ((home, home_score, away_score), (away, away_score, home_score)):
            if team not in out:
                continue
            if own > other:
                out[team]["w"] += 1
            elif own < other:
                out[team]["l"] += 1
            else:
                out[team]["t"] += 1
    return out


def _team_side(
    row: Mapping[str, Any],
    side: str,
    season: int,
    branding: Mapping[str, dict[str, Any]],
    records: Mapping[str, dict[str, int]],
) -> dict[str, Any]:
    code = row.get(f"{side}_team")
    brand = dict(branding.get(code, {})) if code else {}
    name = brand.get("name")
    payload: dict[str, Any] = {
        "side": side,
        "abbr": code,
        # What the club actually played under that season — STL, not LA, in 2001.
        "code_in_season": alignment.code_in_season(code, season) if code else None,
        "name": None if name is None else alignment.label_in_season(code, season, name),
        "nick": brand.get("nick"),
        "logo": brand.get("logo"),
        "logo_espn": brand.get("logo_espn"),
        "wordmark": brand.get("wordmark"),
        "colors": brand.get("colors") or {"primary": None, "secondary": None},
        "score": _int(row.get(f"{side}_score")),
        "href": f"/teams/{code}/{season}" if code else None,
        "franchise_href": f"/teams/{code}" if code else None,
    }
    coach = row.get(f"{side}_coach")
    if coach:
        payload["coach"] = coach
    qb = row.get(f"{side}_qb_name")
    if qb:
        payload["starting_qb"] = qb
    record = records.get(code) if code else None
    if record is not None:
        payload["record_entering"] = dict(record)
    return payload


# --- line score --------------------------------------------------------------


def _line_score(
    loader: Any, game_id: str, season: int, row: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Quarter-by-quarter points, read off the running score of the scoring plays.

    `derived_scoring_plays` carries the score *after* each scoring play, so a
    period's points are the difference between the running score at its last
    scoring play and at the previous period's. Periods in which nobody scored are
    still rows — a 0 there is a fact about the game, not a missing value — but a
    game with no scoring plays at all has no line score rather than a 0-0 grid.
    """
    if not _ensure_derived(loader, season, "derived_scoring_plays"):
        return None
    cur = loader.cursor()
    plays = _rows(
        cur,
        "SELECT play_id, qtr, home_score, away_score FROM derived_scoring_plays "
        "WHERE game_id = ? ORDER BY play_id",
        [game_id],
    )
    if not plays:
        return None

    last_by_period: dict[int, tuple[int, int]] = {}
    for play in plays:
        quarter = _int(play.get("qtr"))
        if quarter is None:
            continue
        home, away = _int(play.get("home_score")), _int(play.get("away_score"))
        if home is None or away is None:
            continue
        last_by_period[quarter] = (home, away)
    if not last_by_period:
        return None

    periods: list[dict[str, Any]] = []
    running = (0, 0)
    for quarter in range(1, max(last_by_period) + 1):
        end = last_by_period.get(quarter, running)
        periods.append({
            "period": quarter,
            "label": _period_label(quarter),
            "home": end[0] - running[0],
            "away": end[1] - running[1],
        })
        running = end

    final_home = _int(row.get("home_score"))
    final_away = _int(row.get("away_score"))
    note = None
    if (
        final_home is not None
        and final_away is not None
        and (running[0], running[1]) != (final_home, final_away)
    ):
        # The scoring plays and the schedule file disagree. Say so rather than
        # quietly printing a line score that does not add up to the final.
        note = (
            "The scoring plays sum to "
            f"{running[0]}-{running[1]}, which does not match the final score "
            f"of {final_home}-{final_away} in the schedule file."
        )
    return {
        "periods": periods,
        "home_total": running[0],
        "away_total": running[1],
        "final_home": final_home,
        "final_away": final_away,
        "source": "derived_scoring_plays",
        "note": note,
    }


# --- scoring summary ---------------------------------------------------------


def _scoring(loader: Any, game_id: str, season: int) -> list[dict[str, Any]]:
    if not _ensure_derived(loader, season, "derived_scoring_plays"):
        return []
    cur = loader.cursor()
    rows = _rows(
        cur,
        "SELECT play_id, qtr, quarter_seconds_remaining, game_seconds_remaining, "
        "scoring_team, posteam, scoring_type, td_player_id, td_player_name, "
        "play_type, description, home_score, away_score "
        "FROM derived_scoring_plays WHERE game_id = ? ORDER BY play_id",
        [game_id],
    )
    out = []
    for row in rows:
        player_id = row.get("td_player_id")
        out.append({
            "play_id": _int(row.get("play_id")),
            "quarter": _int(row.get("qtr")),
            "period_label": _period_label(_int(row.get("qtr"))),
            "clock": _clock(row.get("quarter_seconds_remaining")),
            "seconds_remaining": _int(row.get("game_seconds_remaining")),
            "team": row.get("scoring_team"),
            "posteam": row.get("posteam"),
            "scoring_type": row.get("scoring_type"),
            "play_type": row.get("play_type"),
            "description": row.get("description"),
            "scorer": row.get("td_player_name"),
            "scorer_href": f"/players/{player_id}" if player_id else None,
            "home_score": _int(row.get("home_score")),
            "away_score": _int(row.get("away_score")),
            "anchor": f"play-{_int(row.get('play_id'))}",
        })
    return out


# --- team stats comparison ---------------------------------------------------

_PERCENTILE_METHOD = (
    "Context is a percentile among every team-game in that season, not a rank out "
    "of 32: a single game is not a season. The percentile is the share of that "
    "season's team-games below this one plus half the share equal to it, and n is "
    "the number of team-games that carry the stat."
)

_TEAM_STATS_NOTE = (
    "Counted from the play-derived per-game table. Sacks, third- and fourth-down "
    "conversions and the rush/pass split of yards are not in it, so they are "
    "absent here rather than guessed."
)


def _stat_values(entry: Mapping[str, Any]) -> dict[str, float | None]:
    """Every comparison number for one team-game, rates divided at read time."""
    plays = entry.get("plays")
    return {
        "plays": _as_float(plays),
        "yards": _as_float(entry.get("yards")),
        "yards_per_play": _ratio(entry.get("yards"), plays),
        "first_downs": _as_float(entry.get("first_downs")),
        "epa_total": _as_float(entry.get("epa_total")),
        "epa_per_play": _ratio(entry.get("epa_total"), plays),
        "success_rate": _ratio(entry.get("successes"), plays),
        "turnovers": _as_float(entry.get("turnovers")),
        "penalties": _as_float(entry.get("penalties")),
        "penalty_yards": _as_float(entry.get("penalty_yards")),
        "dropbacks": _as_float(entry.get("dropbacks")),
        "drives": _as_float(entry.get("drives")),
        "top_seconds": _as_float(entry.get("top_seconds")),
    }


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


#: (id, label, unit, higher_is_better)
_TEAM_STAT_SPECS: tuple[tuple[str, str, str, bool], ...] = (
    ("first_downs", "First downs", "count", True),
    ("yards", "Yards from scrimmage", "yards", True),
    ("plays", "Offensive plays", "count", True),
    ("yards_per_play", "Yards per play", "yards", True),
    ("epa_per_play", "EPA per play", "epa", True),
    ("success_rate", "Success rate", "rate", True),
    ("epa_total", "Total EPA", "epa", True),
    ("dropbacks", "Dropbacks", "count", True),
    ("turnovers", "Turnovers lost", "count", False),
    ("penalties", "Penalties", "count", False),
    ("penalty_yards", "Penalty yards", "yards", False),
    ("drives", "Drives", "count", True),
    ("top_seconds", "Time of possession", "seconds", True),
)


def _percentile(values: Sequence[float], value: float) -> float:
    """Share below, plus half the share equal — symmetric in ties."""
    n = len(values)
    if not n:
        return 0.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / n


def _team_stats(
    loader: Any, game_id: str, season: int, home: str | None, away: str | None
) -> dict[str, Any] | None:
    if not _ensure_derived(loader, season, "derived_game_team_stats"):
        return None
    cur = loader.cursor()
    season_rows = _rows(
        cur,
        "SELECT game_id, team, opponent, plays, yards, epa_total, successes, "
        "dropbacks, first_downs, turnovers, penalties, penalty_yards, "
        "top_seconds, drives FROM derived_game_team_stats WHERE season = ?",
        [season],
    )
    if not season_rows:
        return None
    mine = {
        row["team"]: _stat_values(row)
        for row in season_rows
        if row["game_id"] == game_id
    }
    if home not in mine and away not in mine:
        return None

    cohort: dict[str, list[float]] = {}
    for row in season_rows:
        for key, value in _stat_values(row).items():
            if value is not None:
                cohort.setdefault(key, []).append(value)

    rows: list[dict[str, Any]] = []
    for stat_id, label, unit, higher_is_better in _TEAM_STAT_SPECS:
        home_value = mine.get(home, {}).get(stat_id)
        away_value = mine.get(away, {}).get(stat_id)
        if home_value is None and away_value is None:
            continue
        population = cohort.get(stat_id, [])
        rows.append({
            "stat": stat_id,
            "label": label,
            "unit": unit,
            "higher_is_better": higher_is_better,
            "home": _round(home_value),
            "away": _round(away_value),
            "home_context": _context(population, home_value, season),
            "away_context": _context(population, away_value, season),
        })
    if not rows:
        return None
    return {
        "rows": rows,
        "team_games_in_season": len({(r["game_id"], r["team"]) for r in season_rows}),
        "computed_by_us": True,
        "percentile_method": _PERCENTILE_METHOD,
        "note": _TEAM_STATS_NOTE,
    }


def _context(
    population: Sequence[float], value: float | None, season: int
) -> dict[str, Any] | None:
    if value is None or not population:
        return None
    return {
        "percentile": _round(_percentile(population, value), 4),
        "n": len(population),
        "season": season,
    }


# --- drives ------------------------------------------------------------------

_DRIVE_NOTE = (
    "Net yards is computed by us as the difference between the drive's start and "
    "end distance from the opponent's goal line, which the ETL resolved from the "
    "text yard lines. Drive EPA is not stored in the derived table and is not "
    "shown rather than being reconstructed from a play scan."
)


def _drives(loader: Any, game_id: str, season: int) -> list[dict[str, Any]]:
    if not _ensure_derived(loader, season, "derived_drives"):
        return []
    cur = loader.cursor()
    rows = _rows(
        cur,
        "SELECT drive, posteam, defteam, plays, time_of_possession, top_seconds, "
        "first_downs, result, scored, start_yard_line, end_yard_line, "
        "start_yardline_100, end_yardline_100 FROM derived_drives "
        "WHERE game_id = ? ORDER BY drive",
        [game_id],
    )
    out = []
    for row in rows:
        start, end = _int(row.get("start_yardline_100")), _int(row.get("end_yardline_100"))
        out.append({
            "drive": _int(row.get("drive")),
            "team": row.get("posteam"),
            "opponent": row.get("defteam"),
            "plays": _int(row.get("plays")),
            "time_of_possession": row.get("time_of_possession"),
            "top_seconds": _int(row.get("top_seconds")),
            "first_downs": _int(row.get("first_downs")),
            "result": row.get("result"),
            "scored": None if row.get("scored") is None else bool(row.get("scored")),
            "start_yard_line": row.get("start_yard_line"),
            "end_yard_line": row.get("end_yard_line"),
            "start_yardline_100": start,
            "end_yardline_100": end,
            "net_yards": None if start is None or end is None else start - end,
        })
    return out


# --- win probability ---------------------------------------------------------

_WP_NOTE = (
    "Win probability is nflfastR's own model, downsampled at build time to about "
    "120 points per game plus every scoring play. The Vegas-informed series is not "
    "in our play-by-play projection, so only the one model is shown."
)

_SWING_NOTE = (
    "The biggest swing is measured by us across consecutive points of the stored "
    "series, which keeps every scoring play but not every play, so it names the "
    "largest swing we hold rather than certainly the game's largest single WPA."
)


def _win_probability(
    loader: Any, game_id: str, season: int, scoring: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    if not _ensure_derived(loader, season, "derived_wp_series"):
        return None
    cur = loader.cursor()
    rows = _rows(
        cur,
        "SELECT play_id, game_seconds_remaining, home_wp, home_score, away_score "
        "FROM derived_wp_series WHERE game_id = ? AND home_wp IS NOT NULL "
        "ORDER BY play_id",
        [game_id],
    )
    if not rows:
        return None
    kept = _downsample(rows, MAX_WP_POINTS)
    points = [
        {
            "play_id": _int(row.get("play_id")),
            "secs": _int(row.get("game_seconds_remaining")),
            "home_wp": _round(row.get("home_wp")),
            "home_score": _int(row.get("home_score")),
            "away_score": _int(row.get("away_score")),
        }
        for row in kept
    ]

    described = {play["play_id"]: play for play in scoring}
    markers = [
        {
            "play_id": play["play_id"],
            "secs": play["seconds_remaining"],
            "team": play["team"],
            "scoring_type": play["scoring_type"],
            "label": play["description"],
            "home_score": play["home_score"],
            "away_score": play["away_score"],
        }
        for play in scoring
    ]

    biggest = None
    for previous, current in zip(rows, rows[1:]):
        before, after = previous.get("home_wp"), current.get("home_wp")
        if before is None or after is None:
            continue
        delta = float(after) - float(before)
        if biggest is None or abs(delta) > abs(biggest["delta"]):
            play_id = _int(current.get("play_id"))
            biggest = {
                "play_id": play_id,
                "secs": _int(current.get("game_seconds_remaining")),
                "delta": delta,
                "home_wp_before": _round(before),
                "home_wp_after": _round(after),
                "description": (described.get(play_id) or {}).get("description"),
                "computed_by_us": True,
                "note": _SWING_NOTE,
            }
    if biggest is not None:
        biggest["delta"] = _round(biggest["delta"])

    return {
        "points": points,
        "points_stored": len(rows),
        "markers": markers,
        "biggest_swing": biggest,
        "note": _WP_NOTE,
    }


def _downsample(rows: Sequence[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Even sampling that keeps the first and last point, or everything if it fits."""
    n = len(rows)
    if n <= target:
        return list(rows)
    kept = [
        row
        for index, row in enumerate(rows, start=1)
        if index in (1, n)
        or (index * target) // n > ((index - 1) * target) // n
    ]
    return kept


# --- box score ---------------------------------------------------------------

#: Each category, and the candidate spellings of its columns. A column the loaded
#: weekly file does not carry is not in the table; a category none of whose
#: columns exist is not in the payload. Kick and punt returns are deliberately
#: absent: no column in the verified weekly file is known to carry them, and
#: guessing a name would produce a silently empty block.
_BOX_CATEGORIES: tuple[tuple[str, str, tuple[str, ...], tuple[tuple[str, str, tuple[str, ...], bool], ...]], ...] = (
    (
        "passing",
        "Passing",
        ("attempts", "passing_attempts", "pass_attempts", "completions"),
        (
            ("completions", "Cmp", ("completions",), False),
            ("attempts", "Att", ("attempts", "passing_attempts", "pass_attempts"), False),
            ("passing_yards", "Yds", ("passing_yards",), False),
            ("passing_tds", "TD", ("passing_tds",), False),
            ("interceptions", "Int", ("passing_interceptions", "interceptions"), False),
            ("sacks", "Sk", ("sacks_suffered", "sacks"), False),
            ("passing_epa", "EPA", ("passing_epa",), False),
            ("passing_air_yards", "Air yds", ("passing_air_yards",), True),
            ("passing_cpoe", "CPOE", ("passing_cpoe",), True),
        ),
    ),
    (
        "rushing",
        "Rushing",
        ("carries", "rushing_attempts", "rush_atts"),
        (
            ("carries", "Att", ("carries", "rushing_attempts", "rush_atts"), False),
            ("rushing_yards", "Yds", ("rushing_yards",), False),
            ("rushing_tds", "TD", ("rushing_tds",), False),
            ("rushing_first_downs", "1D", ("rushing_first_downs",), False),
            ("rushing_epa", "EPA", ("rushing_epa",), False),
        ),
    ),
    (
        "receiving",
        "Receiving",
        ("targets", "receptions"),
        (
            ("targets", "Tgt", ("targets",), False),
            ("receptions", "Rec", ("receptions",), False),
            ("receiving_yards", "Yds", ("receiving_yards",), False),
            ("receiving_tds", "TD", ("receiving_tds",), False),
            ("receiving_first_downs", "1D", ("receiving_first_downs",), False),
            ("receiving_epa", "EPA", ("receiving_epa",), False),
            ("receiving_air_yards", "Air yds", ("receiving_air_yards",), True),
            (
                "receiving_yards_after_catch", "YAC",
                ("receiving_yards_after_catch",), True,
            ),
        ),
    ),
    (
        "defense",
        "Defense",
        ("def_tackles_solo", "def_sacks", "def_interceptions"),
        (
            ("tackles_solo", "Solo", ("def_tackles_solo",), False),
            ("tackles_assist", "Ast", ("def_tackles_with_assist", "def_tackle_assists"), False),
            ("tackles_for_loss", "TFL", ("def_tackles_for_loss",), False),
            ("sacks", "Sk", ("def_sacks",), False),
            ("qb_hits", "QB hits", ("def_qb_hits",), False),
            ("interceptions", "Int", ("def_interceptions",), False),
            ("passes_defended", "PD", ("def_pass_defended", "def_passes_defended"), False),
            ("forced_fumbles", "FF", ("def_fumbles_forced", "def_forced_fumbles"), False),
        ),
    ),
    (
        "kicking",
        "Kicking",
        ("fg_att", "fg_made", "pat_att", "pat_made"),
        (
            ("fg_made", "FGM", ("fg_made",), False),
            ("fg_att", "FGA", ("fg_att",), False),
            ("fg_long", "Long", ("fg_long",), False),
            ("fg_blocked", "Blk", ("fg_blocked",), False),
            ("pat_made", "XPM", ("pat_made",), False),
            ("pat_att", "XPA", ("pat_att",), False),
        ),
    ),
    (
        "punting",
        "Punting",
        ("punts", "punt_yards"),
        (
            ("punts", "Punts", ("punts", "punt_attempts"), False),
            ("punt_yards", "Yds", ("punt_yards",), False),
            ("punt_net_yards", "Net", ("punt_net_yards",), False),
            ("punt_long", "Long", ("punt_long",), False),
            ("punt_blocked", "Blk", ("punt_blocked",), False),
        ),
    ),
)

_BOX_NOTE = (
    "Box-score lines come from the weekly player file, never summed from plays. A "
    "category appears only where the loaded file carries its columns and at least "
    "one player has a figure in this game."
)


def _box_score(
    loader: Any,
    row: Mapping[str, Any],
    season: int,
    week: int | None,
    home: str | None,
    away: str | None,
) -> dict[str, Any] | None:
    """Per-player lines for both clubs, one table per category.

    The weekly file is keyed by season, week and team rather than by game id in
    the release we read, so that is the join; where a `game_id` column does exist
    it is preferred, because it cannot be confused by a rescheduled week.
    """
    if not _have(loader, "player_week") or home is None or away is None:
        return None
    columns = _table_columns(loader, "player_week")
    if not columns:
        return None
    name_column = _first_present(columns, ("player_display_name", "player_name"))
    id_column = _first_present(columns, ("player_id", "gsis_id"))
    if name_column is None or id_column is None or "team" not in columns:
        return None

    charted = season >= sources.CHARTING_FIRST_SEASON
    resolved: list[tuple[str, str, list[tuple[str, str, str]], tuple[str, ...]]] = []
    selected: dict[str, str] = {}
    for cat_id, label, gates, fields in _BOX_CATEGORIES:
        gate_columns = tuple(c for c in gates if c in columns)
        if not gate_columns:
            continue
        cat_fields = []
        for field_id, field_label, candidates, needs_charting in fields:
            if needs_charting and not charted:
                continue
            column = _first_present(columns, candidates)
            if column is None:
                continue
            cat_fields.append((field_id, field_label, column))
            selected[column] = column
        if cat_fields:
            resolved.append((cat_id, label, cat_fields, gate_columns))
            for column in gate_columns:
                selected[column] = column
    if not resolved:
        return None

    game_id_column = _first_present(columns, ("game_id",))
    where = []
    params: list[Any] = []
    if game_id_column is not None:
        where.append(f'"{game_id_column}" = ?')
        params.append(row["game_id"])
    else:
        if week is None:
            return None
        where.append("season = ? AND week = ?")
        params.extend([season, week])
        if "season_type" in columns:
            # REG and POST weeks are numbered in one sequence upstream, but the
            # filter costs nothing and stops a postseason row ever landing in a
            # regular-season game's box score.
            where.append("season_type = ?")
            params.append("REG" if row.get("game_type") == "REG" else "POST")
    where.append("team IN (?, ?)")
    params.extend([home, away])

    picked = sorted(selected)
    select = ", ".join(
        [f'"{id_column}" AS player_id', f'"{name_column}" AS player_name', '"team"']
        + (['"position"'] if "position" in columns else [])
        + [f'"{c}"' for c in picked]
    )
    cur = loader.cursor()
    player_rows = _rows(
        cur,
        f"SELECT {select} FROM player_week WHERE {' AND '.join(where)}",
        params,
    )
    if not player_rows:
        return None

    categories: list[dict[str, Any]] = []
    for cat_id, label, fields, gate_columns in resolved:
        sides: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
        for player in player_rows:
            if not any(_as_float(player.get(c)) for c in gate_columns):
                continue  # no line in this category for this player, in this game
            side = "home" if player["team"] == home else "away"
            sides[side].append({
                "player_id": player.get("player_id"),
                "name": player.get("player_name"),
                "position": player.get("position"),
                "team": player.get("team"),
                "href": (
                    f"/players/{player['player_id']}" if player.get("player_id") else None
                ),
                "values": {
                    field_id: _round(_as_float(player.get(column)), 3)
                    for field_id, _, column in fields
                },
            })
        if not sides["home"] and not sides["away"]:
            continue
        lead = fields[0][0]
        for side in sides.values():
            # Ordered by the category's own leading column — attempts, carries,
            # targets — so the starter is the first row rather than whoever the
            # weekly file happened to write first.
            side.sort(key=lambda r: -(r["values"].get(lead) or 0.0))
        categories.append({
            "id": cat_id,
            "label": label,
            "columns": [
                {"id": field_id, "label": field_label} for field_id, field_label, _ in fields
            ],
            "home": sides["home"],
            "away": sides["away"],
        })
    if not categories:
        return None
    return {
        "categories": categories,
        "charting_note": (
            None
            if charted
            else "Air yards, yards after catch and CPOE were not charted before "
            f"{sources.CHARTING_FIRST_SEASON}, so those columns are absent for this game."
        ),
        "note": _BOX_NOTE,
    }


# --- snap counts -------------------------------------------------------------

_SNAP_NOTE = (
    "Snap counts are matched to players through pfr_id, which resolves about "
    "99.8% of rows. A player no id matched keeps his snaps and has no player link "
    "— never a zero."
)


def _snaps(
    loader: Any,
    row: Mapping[str, Any],
    season: int,
    week: int | None,
    home: str | None,
    away: str | None,
) -> dict[str, Any] | None:
    if season < sources.SNAP_COUNTS_FIRST_SEASON:
        return None
    if not _have(loader, "snap_counts") or home is None or away is None:
        return None
    columns = _table_columns(loader, "snap_counts")
    if not columns or "team" not in columns:
        return None
    key_column = _first_present(columns, ("pfr_player_id", "pfr_id"))
    name_column = _first_present(columns, ("player", "player_name", "full_name"))

    where = []
    params: list[Any] = []
    if "game_id" in columns:
        where.append("game_id = ?")
        params.append(row["game_id"])
    else:
        if week is None:
            return None
        where.append("season = ? AND week = ?")
        params.extend([season, week])
    where.append("team IN (?, ?)")
    params.extend([home, away])

    wanted = [
        c
        for c in (
            "position", "offense_snaps", "offense_pct", "defense_snaps",
            "defense_pct", "st_snaps", "st_pct",
        )
        if c in columns
    ]
    select = ['"team"']
    if key_column:
        select.append(f'"{key_column}" AS pfr_id')
    if name_column:
        select.append(f'"{name_column}" AS player_name')
    select.extend(f'"{c}"' for c in wanted)

    cur = loader.cursor()
    snap_rows = _rows(
        cur,
        f"SELECT {', '.join(select)} FROM snap_counts WHERE {' AND '.join(where)}",
        params,
    )
    if not snap_rows:
        return None

    gsis: dict[str, str] = {}
    if key_column and _have(loader, "players") and "pfr_id" in _table_columns(loader, "players"):
        ids = [r["pfr_id"] for r in snap_rows if r.get("pfr_id")]
        if ids:
            placeholders = ", ".join("?" * len(ids))
            for match in _rows(
                cur,
                f"SELECT pfr_id, gsis_id FROM players WHERE pfr_id IN ({placeholders})",
                ids,
            ):
                if match["pfr_id"] and match["gsis_id"]:
                    gsis[match["pfr_id"]] = match["gsis_id"]

    sides: dict[str, list[dict[str, Any]]] = {"home": [], "away": []}
    unmatched = 0
    for snap in snap_rows:
        gsis_id = gsis.get(snap.get("pfr_id")) if snap.get("pfr_id") else None
        if gsis_id is None:
            unmatched += 1
        side = "home" if snap["team"] == home else "away"
        sides[side].append({
            "gsis_id": gsis_id,
            "href": f"/players/{gsis_id}" if gsis_id else None,
            "name": snap.get("player_name"),
            "position": snap.get("position"),
            "team": snap.get("team"),
            "offense_snaps": _as_float(snap.get("offense_snaps")),
            "offense_pct": _share(snap.get("offense_pct")),
            "defense_snaps": _as_float(snap.get("defense_snaps")),
            "defense_pct": _share(snap.get("defense_pct")),
            "st_snaps": _as_float(snap.get("st_snaps")),
            "st_pct": _share(snap.get("st_pct")),
        })
    for side in sides.values():
        side.sort(
            key=lambda r: -(r["offense_snaps"] or 0.0) - (r["defense_snaps"] or 0.0)
        )
    return {
        "home": sides["home"],
        "away": sides["away"],
        "unmatched_players": unmatched or None,
        "first_season": sources.SNAP_COUNTS_FIRST_SEASON,
        "note": _SNAP_NOTE,
    }


def _share(value: Any) -> float | None:
    """A snap share as a proportion, whatever units the file ships it in.

    nflverse publishes these as 0-1. The guard is here because a silent switch to
    whole percents would turn a 12% special-teamer into a starter and nothing in
    the payload would look wrong.
    """
    number = _as_float(value)
    if number is None:
        return None
    return _round(number / 100.0 if number > 1 else number)


# --- betting and officials ---------------------------------------------------


def _betting(row: Mapping[str, Any], played: bool) -> dict[str, Any] | None:
    """The closing line, and how the game finished against it.

    `spread_line` is the home team's line in the schedule file, positive when the
    home club is favoured. The two result fields are ours, and say so.
    """
    present = {
        key: row[column]
        for key, column in _BETTING_FIELDS
        if column in row and row[column] is not None
    }
    if not present:
        return None
    payload: dict[str, Any] = {key: _as_float(value) for key, value in present.items()}
    home_score, away_score = _int(row.get("home_score")), _int(row.get("away_score"))
    if played and home_score is not None and away_score is not None:
        spread = payload.get("spread_line")
        if spread is not None:
            margin = home_score - away_score
            payload["home_margin"] = margin
            payload["ats_result"] = (
                "push" if margin == spread else "home" if margin > spread else "away"
            )
        total = payload.get("total_line")
        if total is not None:
            points = home_score + away_score
            payload["total_points"] = points
            payload["ou_result"] = (
                "push" if points == total else "over" if points > total else "under"
            )
        payload["computed_by_us"] = ["ats_result", "ou_result"]
    payload["note"] = (
        "Closing line as published in the schedule file. The spread is the home "
        "club's; the against-the-spread and over/under results are computed by us "
        "from the final score."
    )
    return payload


def _officials(loader: Any, game_id: str) -> list[dict[str, Any]] | None:
    """The crew, where the officials file carries this game.

    The file's column names are detected rather than assumed — it is the one
    source here whose shape nothing else in the app reads — and a file with no
    recognisable name column takes the block with it rather than rendering a list
    of blanks.
    """
    if not _have(loader, "officials"):
        return None
    columns = _table_columns(loader, "officials")
    game_column = _first_present(columns, ("game_id", "nflverse_game_id"))
    name_column = _first_present(
        columns, ("official_name", "name", "full_name", "official")
    )
    if game_column is None or name_column is None:
        return None
    position_column = _first_present(
        columns, ("off_pos", "official_position", "position", "role")
    )
    jersey_column = _first_present(columns, ("jersey_number", "number"))
    select = [f'"{name_column}" AS name']
    if position_column:
        select.append(f'"{position_column}" AS position')
    if jersey_column:
        select.append(f'"{jersey_column}" AS jersey_number')
    cur = loader.cursor()
    rows = _rows(
        cur,
        f'SELECT {", ".join(select)} FROM officials WHERE "{game_column}" = ?',
        [game_id],
    )
    crew = [
        {
            "name": row.get("name"),
            "position": row.get("position"),
            "jersey_number": (
                None if row.get("jersey_number") is None else str(row["jersey_number"])
            ),
        }
        for row in rows
        if row.get("name")
    ]
    return crew or None


# --- coverage ----------------------------------------------------------------


def _coverage(season: int) -> dict[str, Any]:
    """The windows this page's blocks live inside, read from the registry.

    Never a literal year: the day this and `sources.py` disagree is the day the
    site starts lying about what it knows.
    """
    return {
        "first_season": sources.FIRST_SEASON,
        "last_season": latest_season(),
        "charting_first_season": sources.CHARTING_FIRST_SEASON,
        "air_yards_charted": season >= sources.CHARTING_FIRST_SEASON,
        "snap_counts_first_season": sources.SNAP_COUNTS_FIRST_SEASON,
        "snap_counts_available": season >= sources.SNAP_COUNTS_FIRST_SEASON,
        "note": (
            "Expected points, win probability, success and drives run from "
            f"{sources.FIRST_SEASON}. Air yards, yards after catch and CPOE were "
            f"not charted before {sources.CHARTING_FIRST_SEASON} and are empty, "
            "not zero, in earlier games. Snap counts begin in "
            f"{sources.SNAP_COUNTS_FIRST_SEASON}."
        ),
    }


def _play_log_info(loader: Any, game_id: str, season: int) -> dict[str, Any]:
    """What the collapsed play-log header can honestly say before it is opened.

    The count is included only when the season's plays are already reachable
    without a download; otherwise it is absent and the note says the count comes
    with the log, because producing it here would trigger the very materialisation
    this endpoint exists to avoid.
    """
    resident = _season_is_resident(season)
    ready = resident or _season_materialised(season)
    total = None
    if ready:
        try:
            relation = loader.pbp_relation(season)
            row = loader.cursor().execute(
                f"SELECT count(*) FROM {relation} AS p WHERE p.game_id = ?", [game_id]
            ).fetchone()
            total = _int(row[0]) if row else None
        except SeasonBusy:
            ready = False
        except Exception:  # noqa: BLE001 - a play count is never worth a 500
            logger.warning("Could not count plays for %s", game_id, exc_info=True)
            ready = False
    return {
        "href": f"/api/games/{game_id}/plays",
        "source": "resident" if resident else "on_demand",
        "ready": ready,
        "total_plays": total,
        "note": (
            None
            if ready
            else (
                f"The {season} season's plays are materialised on demand, which "
                "takes a few seconds the first time. The play count arrives with "
                "the log."
            )
        ),
    }


# --- GET /api/games/{game_id} ------------------------------------------------


def game(game_id: str, *, loader: Any = None) -> dict[str, Any]:
    """Everything the game page renders except the play log.

    Every block is optional. A game that has not been played carries its fixture
    information and nothing that would describe a result; a block whose source is
    not loaded is absent rather than empty.
    """
    loader = _loader(loader)
    if not _have(loader, "games"):
        raise SourceUnavailable(
            "The schedule file is not loaded in this deployment, so no game can be "
            "shown yet."
        )
    row = _game_row(loader, game_id)
    season = _int(row.get("season"))
    if season is None:
        raise SourceUnavailable(f"The schedule row for {game_id!r} carries no season.")
    week = _int(row.get("week"))
    home, away = row.get("home_team"), row.get("away_team")
    home_score, away_score = _int(row.get("home_score")), _int(row.get("away_score"))
    played = home_score is not None and away_score is not None

    branding = _branding(loader)
    records = _records_entering(loader, season, week, [c for c in (home, away) if c])

    header: dict[str, Any] = {"game_id": game_id}
    for key, column, kind in _HEADER_FIELDS:
        if column in row and row[column] is not None:
            header[key] = _cast(row[column], kind)
    header["home"] = _team_side(row, "home", season, branding, records)
    header["away"] = _team_side(row, "away", season, branding, records)
    if records:
        header["record_note"] = _RECORD_METHOD

    payload: dict[str, Any] = {
        "game_id": game_id,
        "season": season,
        "week": week,
        "header": header,
        "status": {
            "played": played,
            "label": "Final" if played else "Scheduled",
            "note": (
                None
                if played
                else (
                    "This game has not been played. Everything below a result — "
                    "score, box score, drives, win probability — does not exist "
                    "yet and is absent rather than shown as zero."
                )
            ),
        },
        "coverage": _coverage(season),
        "season_href": f"/seasons/{season}",
        "week_href": None if week is None else f"/seasons/{season}/week/{week}",
    }
    if played:
        payload["final"] = {
            "home": home_score,
            "away": away_score,
            "winner": (
                None
                if home_score == away_score
                else home if home_score > away_score else away
            ),
            "tie": home_score == away_score,
            "margin": abs(home_score - away_score),
        }

    betting = _betting(row, played)
    if betting is not None:
        payload["betting"] = betting
    officials = _officials(loader, game_id)
    if officials is not None:
        payload["officials"] = officials

    if not played:
        # A scheduled game has a fixture and a line, and nothing else. Stopping
        # here is what keeps the 2026 schedule from rendering as 0-0 finals.
        return payload

    line_score = _line_score(loader, game_id, season, row)
    if line_score is not None:
        payload["line_score"] = line_score
    scoring = _scoring(loader, game_id, season)
    if scoring:
        payload["scoring"] = scoring
    win_probability = _win_probability(loader, game_id, season, scoring)
    if win_probability is not None:
        payload["win_probability"] = win_probability
    team_stats = _team_stats(loader, game_id, season, home, away)
    if team_stats is not None:
        payload["team_stats"] = team_stats
    drives = _drives(loader, game_id, season)
    if drives:
        payload["drives"] = drives
    box_score = _box_score(loader, row, season, week, home, away)
    if box_score is not None:
        payload["box_score"] = box_score
    snaps = _snaps(loader, row, season, week, home, away)
    if snaps is not None:
        payload["snaps"] = snaps
    payload["play_log"] = _play_log_info(loader, game_id, season)
    return payload


# --- GET /api/games/{game_id}/plays ------------------------------------------

_PLAY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("play_id", "play_id"),
    ("qtr", "quarter"),
    ("quarter_seconds_remaining", "quarter_seconds_remaining"),
    ("game_seconds_remaining", "seconds_remaining"),
    ("down", "down"),
    ("ydstogo", "ydstogo"),
    ("yardline_100", "yardline_100"),
    ("posteam", "posteam"),
    ("defteam", "defteam"),
    ("play_type", "play_type"),
    ("desc", "description"),
    ("yards_gained", "yards_gained"),
    ("epa", "epa"),
    ("wpa", "wpa"),
    ("wp", "wp"),
    ("success", "success"),
    ("first_down", "first_down"),
    ("touchdown", "touchdown"),
    ("fixed_drive", "drive"),
)


def plays(
    game_id: str,
    *,
    team: str | None = None,
    quarter: int | None = None,
    down: int | None = None,
    play_type: str | None = None,
    min_abs_epa: float | None = None,
    drive: int | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    loader: Any = None,
) -> dict[str, Any]:
    """The filterable play log, read from the season's plays.

    Separate from `game()` because it is the one block that can need a download:
    seasons outside the resident window are materialised on demand, and while two
    others are already in flight this raises `SeasonLoading` rather than returning
    an empty list, which would read as "this game had no plays".
    """
    loader = _loader(loader)
    if page < 1:
        raise ValueError("Page numbers start at 1.")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"Page size must be between 1 and {MAX_PAGE_SIZE}.")
    if not _have(loader, "games"):
        raise SourceUnavailable(
            "The schedule file is not loaded in this deployment, so no game can be "
            "shown yet."
        )
    row = _game_row(loader, game_id)
    season = _int(row.get("season"))
    if season is None:
        raise SourceUnavailable(f"The schedule row for {game_id!r} carries no season.")
    home, away = row.get("home_team"), row.get("away_team")
    played = row.get("home_score") is not None and row.get("away_score") is not None
    charted = season >= sources.CHARTING_FIRST_SEASON

    base: dict[str, Any] = {
        "game_id": game_id,
        "season": season,
        "played": played,
        "page": page,
        "page_size": page_size,
        "source": "resident" if _season_is_resident(season) else "on_demand",
        "coverage": _coverage(season),
    }
    if not played:
        # No rows key at all: an empty list here would read as "this game had no
        # plays" rather than "this game has not been played".
        base["note"] = (
            "This game has not been played, so there is no play log yet."
        )
        return base

    try:
        relation = loader.pbp_relation(season)
    except SeasonBusy as exc:
        raise SeasonLoading(_still_loading(season)) from exc

    where = ["p.game_id = ?"]
    params: list[Any] = [game_id]
    applied: dict[str, Any] = {}
    if team is not None:
        code = alignment.current_code(team)
        if code is None or code not in (home, away):
            raise ValueError(
                f"{team} did not play in this game — it was {away} at {home}."
            )
        where.append("p.posteam = ?")
        params.append(code)
        applied["team"] = code
    if quarter is not None:
        where.append("p.qtr = ?")
        params.append(quarter)
        applied["quarter"] = quarter
    if down is not None:
        where.append("p.down = ?")
        params.append(down)
        applied["down"] = down
    if play_type is not None:
        where.append("lower(p.play_type) = lower(?)")
        params.append(play_type)
        applied["play_type"] = play_type
    if min_abs_epa is not None:
        # A play with no EPA is not a play with |EPA| of zero, so an EPA filter
        # excludes it rather than counting it as small.
        where.append("p.epa IS NOT NULL AND abs(p.epa) >= ?")
        params.append(float(min_abs_epa))
        applied["min_abs_epa"] = float(min_abs_epa)
    if drive is not None:
        where.append("p.fixed_drive = ?")
        params.append(drive)
        applied["drive"] = drive

    cur = loader.cursor()
    clause = " AND ".join(where)
    total = _int(
        cur.execute(
            f"SELECT count(*) FROM {relation} AS p WHERE {clause}", params
        ).fetchone()[0]
    )

    select = [f'p."{column}" AS "{alias}"' for column, alias in _PLAY_COLUMNS]
    if charted:
        select.append('p."air_yards" AS "air_yards"')
    rows = _rows(
        cur,
        f"SELECT {', '.join(select)} FROM {relation} AS p WHERE {clause} "
        "ORDER BY p.play_id LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    )

    out = []
    for play in rows:
        record: dict[str, Any] = {
            "play_id": _int(play.get("play_id")),
            "quarter": _int(play.get("quarter")),
            "period_label": _period_label(_int(play.get("quarter"))),
            "clock": _clock(play.get("quarter_seconds_remaining")),
            "seconds_remaining": _int(play.get("seconds_remaining")),
            "down": _int(play.get("down")),
            "ydstogo": _int(play.get("ydstogo")),
            "yardline_100": _int(play.get("yardline_100")),
            "posteam": play.get("posteam"),
            "defteam": play.get("defteam"),
            "play_type": play.get("play_type"),
            "description": play.get("description"),
            "yards_gained": _as_float(play.get("yards_gained")),
            "epa": _round(_as_float(play.get("epa"))),
            "wpa": _round(_as_float(play.get("wpa"))),
            "wp": _round(_as_float(play.get("wp"))),
            "success": _bool(play.get("success")),
            "first_down": _bool(play.get("first_down")),
            "touchdown": _bool(play.get("touchdown")),
            "drive": _int(play.get("drive")),
            "anchor": f"play-{_int(play.get('play_id'))}",
        }
        if charted:
            record["air_yards"] = _as_float(play.get("air_yards"))
        out.append(record)

    if total == 0 and not applied:
        # No filters and no rows: the season's plays are loaded and simply do not
        # carry this game. Said out loud, because an empty table with no
        # explanation reads as "this game had no plays".
        base["note"] = (
            f"The {season} play-by-play is loaded but carries no plays for this "
            "game, so there is nothing to show rather than nothing to find."
        )

    base.update({
        "rows": out,
        "total": total,
        "filters_applied": applied,
        "filter_options": _filter_options(cur, relation, game_id),
        "coverage_note": (
            "Air yards are charted from "
            f"{sources.CHARTING_FIRST_SEASON}; this game is earlier, so the column "
            "is absent rather than zero."
            if not charted
            else None
        ),
    })
    return base


def _filter_options(cur: Any, relation: str, game_id: str) -> dict[str, list[Any]]:
    """What this game actually contains, so the filter bar offers nothing empty."""
    rows = _rows(
        cur,
        f"SELECT DISTINCT p.posteam, p.qtr, p.down, p.play_type "
        f"FROM {relation} AS p WHERE p.game_id = ?",
        [game_id],
    )
    teams = sorted({r["posteam"] for r in rows if r["posteam"]})
    quarters = sorted({_int(r["qtr"]) for r in rows if r["qtr"] is not None})
    downs = sorted({_int(r["down"]) for r in rows if r["down"] is not None})
    play_types = sorted({r["play_type"] for r in rows if r["play_type"]})
    return {
        "teams": teams,
        "quarters": quarters,
        "downs": downs,
        "play_types": play_types,
    }
