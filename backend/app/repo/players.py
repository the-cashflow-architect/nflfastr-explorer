"""Everything the player cockpit reads: the index, the hub, and its three sub-pages.

Six payloads, one rule running through all of them: **a block with no data is not in
the payload.** Not an empty array, not a zero, not a dash the frontend has to guess
at. The page renders what it is given and omits what it is not, which is only
honest if this layer never dresses a gap as a result.

Four things that are easy to get wrong here, and how they are handled.

**A quarter of the league has no season stat row.** Offensive linemen, long snappers
and most special-teamers never appear in `stats_player_reg`. Their index row gets a
snap-share headline where snap counts reach (2012+) and an explicit blank with a
reason where they do not — never a `0` in a yards column, which would read as a
career of failure rather than a career nobody counted this way.

**Columns are detected, not assumed.** nflverse renames fields between releases and
this fixture-to-production gap is where a stat line quietly becomes a wall of nulls.
Every stat names its candidate spellings and drops out of the payload if none of
them is in the loaded table.

**Rates are pooled at read time.** A multi-team season's combined row is a sum of its
per-team rows, and a career row is a sum of its seasons; anything stored as a rate
(CPOE) is re-weighted by its own volume first. Nothing here averages an average
(SPEC 0.7).

**Sources are joined on ids, never on names.** Snap counts and PFR advanced stats
reach players through `pfr_id`, ESPN's QBR through `espn_id`. College strings differ
systematically between files, so a name-and-college match would be a guess wearing a
join's clothing (SPEC 0.3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from .. import sources
from ..etl import buckets, derived, franchises, pbp_derive
from ..loader import SeasonBusy
from ..etl.alignment import code_in_season
from .percentiles import (
    CAREER,
    SEASON_TABLE,
    ensure_source,
    first_present,
    position_group_for,
    resolve_loader,
    table_columns,
)
from . import percentiles

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

#: The position groups whose plays the situational ETL can credit to somebody.
#: `buckets.ROLES` is passer, rusher and receiver and nothing else, so a defender's
#: splits table would be empty rather than wrong — the page says so instead of
#: rendering it (SPEC section 3, correction 4).
OFFENSIVE_GROUPS = frozenset({"QB", "RB", "WR", "TE", "FB"})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug_for(display_name: str | None) -> str | None:
    """The URL's human half. `gsis_id` is the identity; this is decoration."""
    if not display_name:
        return None
    return _SLUG_RE.sub("-", display_name.lower()).strip("-") or None


# --- stat lines ----------------------------------------------------------------


@dataclass(frozen=True)
class Stat:
    """One column of the career table, and how to combine it across rows."""

    id: str
    label: str
    #: Candidate spellings; the first present in the loaded table wins.
    columns: tuple[str, ...]
    unit: str = "count"
    #: Present only for a stat upstream stores as a rate. The rate is weighted by
    #: this volume before summing, which is what makes a career row a pooled rate
    #: instead of the mean of the seasons (SPEC 0.7).
    weight: tuple[str, ...] = ()
    #: Read off `sources`. Drives the cell's era note; never written as a year.
    first_season: int | None = None

    @property
    def is_rate(self) -> bool:
        return bool(self.weight)


_ATTEMPTS = ("attempts", "passing_attempts", "pass_attempts")
_CARRIES = ("carries", "rushing_attempts", "rush_atts")

_QB_LINE: tuple[Stat, ...] = (
    Stat("completions", "Cmp", ("completions",)),
    Stat("attempts", "Att", _ATTEMPTS),
    Stat("passing_yards", "Pass yds", ("passing_yards",), unit="yards"),
    Stat("passing_tds", "Pass TD", ("passing_tds",)),
    Stat("interceptions", "Int", ("passing_interceptions", "interceptions")),
    Stat("sacks", "Sacked", ("sacks_suffered", "sacks")),
    Stat("passing_epa", "Pass EPA", ("passing_epa",), unit="epa"),
    Stat(
        "passing_cpoe", "CPOE", ("passing_cpoe",), unit="percent",
        weight=_ATTEMPTS, first_season=sources.CHARTING_FIRST_SEASON,
    ),
    Stat("carries", "Rush att", _CARRIES),
    Stat("rushing_yards", "Rush yds", ("rushing_yards",), unit="yards"),
)

_RB_LINE: tuple[Stat, ...] = (
    Stat("carries", "Rush att", _CARRIES),
    Stat("rushing_yards", "Rush yds", ("rushing_yards",), unit="yards"),
    Stat("rushing_tds", "Rush TD", ("rushing_tds",)),
    Stat("rushing_epa", "Rush EPA", ("rushing_epa",), unit="epa"),
    Stat("targets", "Tgt", ("targets",)),
    Stat("receptions", "Rec", ("receptions",)),
    Stat("receiving_yards", "Rec yds", ("receiving_yards",), unit="yards"),
    Stat("receiving_tds", "Rec TD", ("receiving_tds",)),
)

_RECEIVER_LINE: tuple[Stat, ...] = (
    Stat("targets", "Tgt", ("targets",)),
    Stat("receptions", "Rec", ("receptions",)),
    Stat("receiving_yards", "Rec yds", ("receiving_yards",), unit="yards"),
    Stat("receiving_tds", "Rec TD", ("receiving_tds",)),
    Stat(
        "receiving_air_yards", "Air yds", ("receiving_air_yards",), unit="yards",
        first_season=sources.CHARTING_FIRST_SEASON,
    ),
    Stat("receiving_epa", "Rec EPA", ("receiving_epa",), unit="epa"),
    Stat("carries", "Rush att", _CARRIES),
    Stat("rushing_yards", "Rush yds", ("rushing_yards",), unit="yards"),
)

_DEFENCE_LINE: tuple[Stat, ...] = (
    Stat("tackles_solo", "Solo", ("def_tackles_solo",)),
    Stat("tackles_assist", "Ast", ("def_tackles_with_assist", "def_tackle_assists")),
    Stat("tackles_for_loss", "TFL", ("def_tackles_for_loss",)),
    Stat("sacks", "Sacks", ("def_sacks",)),
    Stat("qb_hits", "QB hits", ("def_qb_hits",)),
    Stat("interceptions", "Int", ("def_interceptions",)),
    Stat("passes_defended", "PD", ("def_pass_defended", "def_passes_defended")),
    Stat("forced_fumbles", "FF", ("def_fumbles_forced", "def_forced_fumbles")),
)

STAT_LINES: dict[str, tuple[Stat, ...]] = {
    "QB": _QB_LINE,
    "RB": _RB_LINE,
    "FB": _RB_LINE,
    "WR": _RECEIVER_LINE,
    "TE": _RECEIVER_LINE,
    "DL": _DEFENCE_LINE,
    "LB": _DEFENCE_LINE,
    "DB": _DEFENCE_LINE,
}


@dataclass(frozen=True)
class Headline:
    """The one career number the index prints for a position group."""

    id: str
    label: str
    columns: tuple[str, ...]
    unit: str = "count"


#: Ordered candidates per group; the first whose column exists wins. Groups absent
#: from this table (OL, SPEC and anything upstream adds) have no counting stat in
#: the season file at all and fall through to the snap-share headline below.
HEADLINES: dict[str, tuple[Headline, ...]] = {
    "QB": (Headline("passing_yards", "Passing yards", ("passing_yards",), "yards"),),
    "RB": (Headline("rushing_yards", "Rushing yards", ("rushing_yards",), "yards"),),
    "FB": (Headline("rushing_yards", "Rushing yards", ("rushing_yards",), "yards"),),
    "WR": (Headline("receiving_yards", "Receiving yards", ("receiving_yards",), "yards"),),
    "TE": (Headline("receiving_yards", "Receiving yards", ("receiving_yards",), "yards"),),
    "DL": (
        Headline("sacks", "Sacks", ("def_sacks",)),
        Headline("tackles_solo", "Solo tackles", ("def_tackles_solo",)),
    ),
    "LB": (
        Headline("tackles_solo", "Solo tackles", ("def_tackles_solo",)),
        Headline("sacks", "Sacks", ("def_sacks",)),
    ),
    "DB": (
        Headline("interceptions", "Interceptions", ("def_interceptions",)),
        Headline("tackles_solo", "Solo tackles", ("def_tackles_solo",)),
    ),
}


def _headline_for(group: str | None, columns: Iterable[str]) -> tuple[Headline, str] | None:
    for option in HEADLINES.get((group or "").upper(), ()):
        column = first_present(columns, option.columns)
        if column is not None:
            return option, column
    return None


# --- small shared pieces --------------------------------------------------------


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _date(value: Any) -> date | None:
    """A calendar date, whatever the column's declared type turned out to be.

    DuckDB hands back a `datetime` for a TIMESTAMP column and a `date` for a DATE
    one, and which of the two a parquet file declares is upstream's choice, not
    ours. Subtracting one from the other raises, so the conversion happens once,
    here, rather than at four call sites that would each get it right until the
    file changed.
    """
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _age(birth_date: Any, on: Any = None) -> float | None:
    born = _date(birth_date)
    reference = _date(on) or date.today()
    if born is None:
        return None
    return round((reference - born).days / 365.25, 1)


def _rate(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _identity_row(loader: Any, gsis_id: str) -> dict[str, Any] | None:
    cur = loader.cursor()
    row = cur.execute(
        """
        SELECT gsis_id, display_name, first_name, last_name, position, position_group,
               jersey_number, birth_date, height, weight, headshot, college_name,
               college_conference, rookie_season, last_season, latest_team, status,
               years_of_experience, draft_year, draft_round, draft_pick, draft_team,
               pfr_id, espn_id
        FROM players WHERE gsis_id = ?
        """,
        [gsis_id],
    ).fetchone()
    if row is None:
        return None
    keys = (
        "gsis_id", "display_name", "first_name", "last_name", "position", "position_group",
        "jersey_number", "birth_date", "height", "weight", "headshot", "college_name",
        "college_conference", "rookie_season", "last_season", "latest_team", "status",
        "years_of_experience", "draft_year", "draft_round", "draft_pick", "draft_team",
        "pfr_id", "espn_id",
    )
    return dict(zip(keys, row))


def _newest_player_season(loader: Any) -> int | None:
    """The newest season any player row claims, for the active/retired rule.

    Read rather than assumed: `latest_season()` is a date calculation and would
    call a player retired the moment the calendar rolls over, before the season it
    names has a single row on file.
    """
    cur = loader.cursor()
    row = cur.execute("SELECT max(last_season) FROM players").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _draft_block(identity: dict[str, Any]) -> dict[str, Any] | None:
    """The draft line, resolved to a franchise we can actually link to.

    `franchise_from_draft_code` returns None for a code that meant two different
    clubs in two different decades; the payload then carries the code as text with
    no link, which is the honest rendering of "we know he was drafted, we do not
    know by whom" (SPEC 0.3, `etl/franchises.py`).
    """
    year = identity.get("draft_year")
    if year is None:
        return None
    code = identity.get("draft_team")
    franchise = franchises.franchise_from_draft_code(code, int(year))
    return {
        "season": int(year),
        "round": identity.get("draft_round"),
        "pick": identity.get("draft_pick"),
        "team_code": code,
        "team": franchise,
        "team_href": f"/teams/{franchise}" if franchise else None,
        "class_href": f"/draft/{int(year)}",
    }


# --- career rollups -------------------------------------------------------------


def _stat_selects(line: Sequence[Stat], columns: Iterable[str]) -> tuple[list[Stat], list[str]]:
    """SELECT fragments for a stat line, skipping stats with no column present."""
    usable: list[Stat] = []
    selects: list[str] = []
    for stat in line:
        column = first_present(columns, stat.columns)
        if column is None:
            continue
        if stat.is_rate:
            weight = first_present(columns, stat.weight)
            if weight is None:
                continue
            selects.append(
                f'sum(CAST("{column}" AS DOUBLE) * CAST("{weight}" AS DOUBLE)) AS "n_{stat.id}"'
            )
            selects.append(
                f'sum(CASE WHEN "{column}" IS NOT NULL THEN CAST("{weight}" AS DOUBLE) END)'
                f' AS "d_{stat.id}"'
            )
        else:
            selects.append(f'sum(CAST("{column}" AS DOUBLE)) AS "n_{stat.id}"')
        usable.append(stat)
    return usable, selects


def _combine(parts: Iterable[dict[str, float | None]], stats: Sequence[Stat]) -> dict[str, float | None]:
    """Sum a set of per-team rows into one, pooling rates over their own weight."""
    parts = list(parts)
    combined: dict[str, float | None] = {}
    for stat in stats:
        numerators = [p.get(f"n_{stat.id}") for p in parts]
        present = [n for n in numerators if n is not None]
        combined[f"n_{stat.id}"] = sum(present) if present else None
        if stat.is_rate:
            weights = [p.get(f"d_{stat.id}") for p in parts]
            present_w = [w for w in weights if w is not None]
            combined[f"d_{stat.id}"] = sum(present_w) if present_w else None
    return combined


def _values(raw: dict[str, float | None], stats: Sequence[Stat]) -> dict[str, float | None]:
    """Raw sums to the numbers the table prints."""
    out: dict[str, float | None] = {}
    for stat in stats:
        numerator = raw.get(f"n_{stat.id}")
        if stat.is_rate:
            out[stat.id] = _rate(numerator, raw.get(f"d_{stat.id}"))
        else:
            out[stat.id] = numerator
    return out


def _league_leaders(
    loader: Any, table: str, seasons: Sequence[int], stats: Sequence[Stat], columns: Iterable[str]
) -> dict[int, dict[str, float]]:
    """The best per-player season total in each of these seasons, per counting stat.

    Counting stats only. A rate leader needs a qualification rule, and applying one
    silently here would put a bold cell next to a player who led on eleven attempts;
    the qualified rate leaders live on the leaderboards, where the threshold is
    printed beside them.
    """
    counting = [s for s in stats if not s.is_rate]
    if not counting or not seasons:
        return {}
    resolved = [(s, first_present(columns, s.columns)) for s in counting]
    resolved = [(s, c) for s, c in resolved if c is not None]
    if not resolved:
        return {}
    inner = ", ".join(f'sum(CAST("{c}" AS DOUBLE)) AS "v_{s.id}"' for s, c in resolved)
    outer = ", ".join(f'max("v_{s.id}")' for s, _ in resolved)
    placeholders = ", ".join("?" for _ in seasons)
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT season, {outer} FROM (
            SELECT season, player_id, {inner} FROM {table}
            WHERE player_id IS NOT NULL AND season IN ({placeholders})
            GROUP BY season, player_id
        ) GROUP BY season
        """,
        list(seasons),
    ).fetchall()
    leaders: dict[int, dict[str, float]] = {}
    for row in rows:
        season = int(row[0])
        leaders[season] = {
            stat.id: float(value)
            for (stat, _), value in zip(resolved, row[1:])
            if value is not None
        }
    return leaders


def _career_table(
    loader: Any,
    gsis_id: str,
    table: str,
    line: Sequence[Stat],
    *,
    with_leaders: bool,
) -> dict[str, Any] | None:
    """One season-by-season table: per-team rows, combined rows, and a career total.

    Returns None when the player has no row at all in this table, which is how the
    postseason block disappears for a player who never played one.
    """
    columns = table_columns(loader, table)
    if not columns:
        return None
    stats, selects = _stat_selects(line, columns)
    games_column = first_present(columns, ("games",))
    games_select = (
        f'sum(CAST("{games_column}" AS DOUBLE)) AS games' if games_column else "NULL AS games"
    )
    cur = loader.cursor()
    rows = cur.execute(
        f"SELECT season, team, {games_select}"
        + ("".join(f", {s}" for s in selects) if selects else "")
        + f" FROM {table} WHERE player_id = ? GROUP BY season, team ORDER BY season, team",
        [gsis_id],
    ).fetchall()
    if not rows:
        return None

    per_row: list[dict[str, Any]] = []
    for row in rows:
        raw = {
            key: _as_float(row[3 + index]) for index, key in enumerate(_expand(stats))
        }
        per_row.append(
            {
                "season": int(row[0]),
                "team": row[1],
                "games": _as_float(row[2]),
                "raw": raw,
            }
        )

    seasons = sorted({r["season"] for r in per_row})
    leaders = (
        _league_leaders(loader, table, seasons, stats, columns) if with_leaders else {}
    )

    out_rows: list[dict[str, Any]] = []
    for season in seasons:
        season_rows = [r for r in per_row if r["season"] == season]
        teams = [r["team"] for r in season_rows if r["team"]]
        combined_raw = _combine((r["raw"] for r in season_rows), stats)
        combined_values = _values(combined_raw, stats)
        combined_games = _sum_optional(r["games"] for r in season_rows)
        led = [
            stat.id
            for stat in stats
            if not stat.is_rate
            and combined_values.get(stat.id) is not None
            and leaders.get(season, {}).get(stat.id) is not None
            and combined_values[stat.id] == leaders[season][stat.id]
            and combined_values[stat.id] > 0
        ]
        if len(season_rows) > 1:
            # Per-team rows first, then the row a career total is actually built
            # from. Leader flags sit on the combined row only: the league lead is
            # a season total, not a half-season with one club.
            for row in season_rows:
                out_rows.append(_table_row(row, stats, season, is_combined=False, teams=None, led=[]))
            out_rows.append(
                _table_row(
                    {"season": season, "team": None, "games": combined_games, "raw": combined_raw},
                    stats, season, is_combined=True, teams=teams, led=led,
                )
            )
        else:
            out_rows.append(
                _table_row(season_rows[0], stats, season, is_combined=False, teams=None, led=led)
            )

    career_raw = _combine(
        (
            _combine((r["raw"] for r in per_row if r["season"] == season), stats)
            for season in seasons
        ),
        stats,
    )
    total = {
        "seasons": len(seasons),
        "first_season": seasons[0],
        "last_season": seasons[-1],
        "games": _sum_optional(r["games"] for r in per_row),
        "stats": _values(career_raw, stats),
    }
    payload: dict[str, Any] = {
        "columns": [
            {
                "id": stat.id,
                "label": stat.label,
                "unit": stat.unit,
                "kind": "rate" if stat.is_rate else "count",
                "first_season": stat.first_season,
            }
            for stat in stats
        ],
        "rows": out_rows,
        "total": total,
    }
    if with_leaders:
        payload["leader_note"] = (
            "Bolded cells led the league that season. Counting stats only — a rate "
            "leader needs a qualification threshold, which the leaderboards state."
        )
    if not stats:
        payload["note"] = (
            "The season stats file carries no columns for this position group, so "
            "this table shows games played only."
        )
    return payload


def _expand(stats: Sequence[Stat]) -> list[str]:
    """The raw-column keys the SELECT produces, in order."""
    keys: list[str] = []
    for stat in stats:
        keys.append(f"n_{stat.id}")
        if stat.is_rate:
            keys.append(f"d_{stat.id}")
    return keys


def _sum_optional(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _table_row(
    row: dict[str, Any],
    stats: Sequence[Stat],
    season: int,
    *,
    is_combined: bool,
    teams: list[str] | None,
    led: Sequence[str],
) -> dict[str, Any]:
    team = row["team"]
    return {
        "season": season,
        "team": team,
        "team_href": f"/teams/{team}/{season}" if team else None,
        "code_in_season": code_in_season(team, season) if team else None,
        "teams": teams,
        "team_label": (
            f"{len(teams)} teams" if is_combined and teams else (team or None)
        ),
        "is_combined": is_combined,
        "games": row["games"],
        "stats": _values(row["raw"], stats),
        "led_league": list(led),
    }


# --- the index ------------------------------------------------------------------


def player_index(
    *,
    q: str | None = None,
    position: str | None = None,
    team: str | None = None,
    season: int | None = None,
    college: str | None = None,
    draft_year: int | None = None,
    status: str | None = None,
    sort: str = "recent",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    loader: Any = None,
) -> dict[str, Any]:
    """The paged, filtered player index, with one headline career stat per row."""
    loader = resolve_loader(loader)
    ensure_source(loader, "players")
    has_seasons = ensure_source(loader, "player_season_reg")
    snaps_available = ensure_source(loader, "snap_counts")

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    columns = table_columns(loader, SEASON_TABLE) if has_seasons else frozenset()

    headline_columns: list[tuple[str, str]] = []
    seen: set[str] = set()
    for options in HEADLINES.values():
        for option in options:
            column = first_present(columns, option.columns)
            if column and column not in seen:
                seen.add(column)
                headline_columns.append((option.id, column))

    # The empty case still has to carry every column the outer SELECT names, or a
    # deployment without season stats fails to answer at all instead of answering
    # with blanks.
    empty_headlines = "".join(f', NULL::DOUBLE AS "h_{column}"' for _, column in headline_columns)
    career_cte = (
        "SELECT NULL::VARCHAR AS gsis_id, NULL::INTEGER AS first_stat_season, "
        "NULL::INTEGER AS last_stat_season, NULL::DOUBLE AS games, "
        f"NULL::VARCHAR[] AS teams{empty_headlines} WHERE FALSE"
    )
    if has_seasons:
        sums = "".join(
            f', sum(CAST("{column}" AS DOUBLE)) AS "h_{column}"' for _, column in headline_columns
        )
        games = (
            'sum(CAST("games" AS DOUBLE))' if "games" in columns else "NULL"
        )
        career_cte = f"""
            SELECT player_id AS gsis_id,
                   min(season) AS first_stat_season,
                   max(season) AS last_stat_season,
                   {games} AS games,
                   list(DISTINCT team) AS teams
                   {sums}
            FROM {SEASON_TABLE} WHERE player_id IS NOT NULL GROUP BY player_id
        """

    where: list[str] = ["p.gsis_id IS NOT NULL"]
    params: list[Any] = []
    cur = loader.cursor()

    if q:
        where.append("contains(lower(strip_accents(p.display_name)), lower(strip_accents(?)))")
        params.append(q.strip())
    if position:
        where.append("(upper(p.position_group) = upper(?) OR upper(p.position) = upper(?))")
        params.extend([position.strip(), position.strip()])
    if team:
        # Latest team, or any team he has a season row with: a player who moved on
        # is still part of the franchises he played for, and the index's team
        # filter is how a visitor looks for him there.
        where.append("(p.latest_team = ? OR list_contains(c.teams, ?))")
        params.extend([team.strip().upper(), team.strip().upper()])
    if season is not None:
        where.append(
            "(? BETWEEN coalesce(p.rookie_season, ?) AND coalesce(p.last_season, ?))"
        )
        params.extend([int(season), int(season), int(season)])
    if college:
        where.append("contains(lower(p.college_name), lower(?))")
        params.append(college.strip())
    if draft_year is not None:
        where.append("p.draft_year = ?")
        params.append(int(draft_year))

    newest = _newest_player_season(loader)
    if status and newest is not None:
        wanted = status.strip().lower()
        if wanted == "active":
            where.append("p.last_season >= ?")
            params.append(newest)
        elif wanted == "retired":
            where.append("(p.last_season IS NULL OR p.last_season < ?)")
            params.append(newest)

    order = {
        "name": "p.display_name",
        "recent": "p.last_season DESC NULLS LAST, p.display_name",
        "games": "c.games DESC NULLS LAST, p.display_name",
    }.get(sort, "p.last_season DESC NULLS LAST, p.display_name")

    base = f"""
        FROM players p
        LEFT JOIN ({career_cte}) c ON c.gsis_id = p.gsis_id
        WHERE {' AND '.join(where)}
    """
    total = cur.execute(f"SELECT count(*) {base}", params).fetchone()[0]
    select_headlines = "".join(f', c."h_{column}"' for _, column in headline_columns)
    rows = cur.execute(
        f"""
        SELECT p.gsis_id, p.display_name, p.position, p.position_group, p.latest_team,
               p.rookie_season, p.last_season, p.status, p.draft_year, p.draft_round,
               p.draft_pick, p.college_name, c.first_stat_season, c.last_stat_season,
               c.games, c.teams{select_headlines}
        {base}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        params + [page_size, (page - 1) * page_size],
    ).fetchall()

    headline_index = {column: 16 + i for i, (_, column) in enumerate(headline_columns)}
    latest_snap_shares = _latest_snap_shares(
        loader, [row[0] for row in rows]
    ) if snaps_available else {}

    out: list[dict[str, Any]] = []
    for row in rows:
        group = row[3]
        headline = _headline_for(group, columns)
        entry: dict[str, Any] = {
            "gsis_id": row[0],
            "display_name": row[1],
            "slug": slug_for(row[1]),
            "href": f"/players/{row[0]}/{slug_for(row[1]) or ''}".rstrip("/"),
            "position": row[2],
            "position_group": group,
            "latest_team": row[4],
            "first_season": row[12] if row[12] is not None else row[5],
            "last_season": row[13] if row[13] is not None else row[6],
            "status": row[7],
            "active": bool(newest is not None and row[6] is not None and row[6] >= newest),
            "college": row[11],
            "games": _as_float(row[14]),
            "teams": sorted(row[15]) if row[15] else [],
            "draft": (
                None if row[8] is None
                else {"season": int(row[8]), "round": row[9], "pick": row[10]}
            ),
            "headline": _index_headline(
                headline, row, headline_index, group, latest_snap_shares.get(row[0]), snaps_available
            ),
        }
        out.append(entry)

    return {
        "rows": out,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "filters": {
            "q": q, "position": position, "team": team, "season": season,
            "college": college, "draft_year": draft_year, "status": status,
        },
        "rules": {
            "active": (
                f"Active means a final season of {newest} — the newest season any player "
                "row on file claims — not a roster check."
                if newest is not None
                else "No player rows are loaded, so active and retired cannot be told apart."
            ),
            "season_filter": (
                "A season filter matches players whose rookie-to-final-season span covers "
                "it, so linemen and special-teamers with no statistical row that year are "
                "still found."
            ),
            "headline": (
                "One career stat per position group. Groups with no row in the season "
                "stats file — offensive line, long snappers, most special-teamers — show "
                "their latest snap share instead, or nothing at all before snap counts begin."
            ),
        },
        "snap_counts_first_season": sources.SNAP_COUNTS_FIRST_SEASON,
    }


def _index_headline(
    headline: tuple[Headline, str] | None,
    row: Sequence[Any],
    headline_index: dict[str, int],
    group: str | None,
    snap_share: dict[str, Any] | None,
    snaps_available: bool,
) -> dict[str, Any]:
    """One row's headline number, or an honest blank saying why there isn't one."""
    if headline is not None:
        option, column = headline
        value = _as_float(row[headline_index[column]])
        if value is not None:
            return {
                "id": option.id,
                "label": option.label,
                "value": value,
                "unit": option.unit,
                "source": "player_season_reg",
                "note": None,
            }
    if snap_share is not None:
        return {
            "id": "snap_share",
            "label": f"Snap share, {snap_share['season']}",
            "value": snap_share["share"],
            "unit": "percent",
            "source": "snap_counts",
            "note": (
                "No season stat line for this position group, so the headline is the "
                f"share of his team's snaps he played in {snap_share['season']}."
            ),
        }
    return {
        "id": None,
        "label": None,
        "value": None,
        "unit": None,
        "source": None,
        "note": (
            "No counting stat is published for this position group, and snap counts "
            f"(from {sources.SNAP_COUNTS_FIRST_SEASON}) "
            + ("do not cover this player." if snaps_available else "are not loaded.")
        ),
    }


# --- snap counts ----------------------------------------------------------------


def _snap_columns(loader: Any) -> dict[str, str] | None:
    """The snap-count column names this release actually uses, or None.

    Detected rather than assumed for the same reason the stat lines are, and
    because the join key is `pfr_player_id` here and `pfr_id` in `players` — the
    one join on this page that is not gsis_id to gsis_id (SPEC 0.3).
    """
    columns = table_columns(loader, "snap_counts")
    if not columns:
        return None
    key = first_present(columns, ("pfr_player_id", "pfr_id"))
    if key is None or "season" not in columns:
        return None
    resolved = {"key": key}
    for name, candidates in (
        ("offense_snaps", ("offense_snaps",)),
        ("offense_pct", ("offense_pct",)),
        ("defense_snaps", ("defense_snaps",)),
        ("defense_pct", ("defense_pct",)),
        ("st_snaps", ("st_snaps", "special_teams_snaps")),
        ("st_pct", ("st_pct", "special_teams_pct")),
        ("week", ("week",)),
        ("team", ("team",)),
        ("game_id", ("game_id",)),
    ):
        column = first_present(columns, candidates)
        if column is not None:
            resolved[name] = column
    return resolved if "offense_snaps" in resolved or "defense_snaps" in resolved else None


def _pct_sql(reference: str) -> str:
    """Snap share as a proportion, whatever units the file ships it in.

    nflverse publishes `offense_pct` as a 0-1 proportion. The rescale guard is
    here because a silent switch to whole percents would turn a 12% special-teamer
    into a starter under the 50% started-proxy, and nothing in the payload would
    look wrong.

    Takes an already-quoted SQL reference (`"offense_pct"` or `s."offense_pct"`)
    rather than a bare name: three of the four call sites need a table alias, and
    quoting here as well produced `"s."offense_pct""`, which DuckDB rejects as a
    zero-length identifier. Every call site was already passing a quoted string.
    """
    return f"CASE WHEN {reference} > 1 THEN {reference} / 100.0 ELSE {reference} END"


def _latest_snap_shares(loader: Any, gsis_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Each player's most recent season snap share, pooled over his games.

    The share is `SUM(snaps) / SUM(team snaps)`, with team snaps recovered from the
    per-game share — never the mean of the game percentages, which would weight a
    two-snap injury game the same as a full one.
    """
    resolved = _snap_columns(loader)
    if resolved is None or not gsis_ids:
        return {}
    columns = table_columns(loader, "players")
    if "pfr_id" not in columns:
        return {}
    offense = resolved.get("offense_snaps")
    pct = resolved.get("offense_pct")
    if offense is None or pct is None:
        return {}
    cur = loader.cursor()
    placeholders = ", ".join("?" for _ in gsis_ids)
    rows = cur.execute(
        f"""
        WITH mine AS (
            SELECT p.gsis_id, s.season,
                   sum(CAST(s."{offense}" AS DOUBLE)) AS snaps,
                   sum(CASE WHEN {_pct_sql('s."' + pct + '"')} > 0
                            THEN CAST(s."{offense}" AS DOUBLE) / {_pct_sql('s."' + pct + '"')}
                       END) AS team_snaps
            FROM players p
            JOIN snap_counts s ON s."{resolved['key']}" = p.pfr_id
            WHERE p.gsis_id IN ({placeholders}) AND p.pfr_id IS NOT NULL
            GROUP BY p.gsis_id, s.season
        )
        SELECT gsis_id, season, snaps, team_snaps FROM mine m
        WHERE season = (SELECT max(season) FROM mine m2 WHERE m2.gsis_id = m.gsis_id)
        """,
        list(gsis_ids),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for gsis_id, season, snaps, team_snaps in rows:
        share = _rate(_as_float(snaps), _as_float(team_snaps))
        if share is None:
            continue
        out[gsis_id] = {"season": int(season), "share": round(share * 100, 1), "snaps": _as_float(snaps)}
    return out


# --- the hub ---------------------------------------------------------------------


def player_hub(gsis_id: str, *, loader: Any = None) -> dict[str, Any] | None:
    """Everything the player hub renders, with every empty block left out."""
    loader = resolve_loader(loader)
    if not ensure_source(loader, "players"):
        return None
    identity = _identity_row(loader, gsis_id)
    if identity is None:
        return None

    has_reg = ensure_source(loader, "player_season_reg")
    has_post = ensure_source(loader, "player_season_post")
    has_week = ensure_source(loader, "player_week")
    snaps_available = ensure_source(loader, "snap_counts")

    group = position_group_for(loader, gsis_id) or identity.get("position_group")
    line = STAT_LINES.get((group or "").upper(), ())
    newest = _newest_player_season(loader)

    payload: dict[str, Any] = {
        "identity": {
            "gsis_id": gsis_id,
            "display_name": identity["display_name"],
            "slug": slug_for(identity["display_name"]),
            "first_name": identity["first_name"],
            "last_name": identity["last_name"],
            "position": identity["position"],
            "position_group": group,
            "jersey_number": identity["jersey_number"],
            "height": identity["height"],
            "weight": identity["weight"],
            "birth_date": _date(identity["birth_date"]).isoformat() if _date(identity["birth_date"]) else None,
            "age": _age(identity["birth_date"]),
            "headshot_url": identity["headshot"],
            "college": identity["college_name"],
            "college_conference": identity["college_conference"],
            "rookie_season": identity["rookie_season"],
            "last_season": identity["last_season"],
            "years_of_experience": identity["years_of_experience"],
            "status": identity["status"],
            "status_label": _status_label(identity, newest),
            "team": identity["latest_team"],
            "team_href": f"/teams/{identity['latest_team']}" if identity["latest_team"] else None,
        },
        "era": {
            "stats_first_season": sources.get("player_season_reg").first_season,
            "note": (
                "Season and game stats on this page run from "
                f"{sources.get('player_season_reg').first_season}. Blocks with a narrower "
                "window carry their own."
            ),
        },
    }

    draft = _draft_block(identity)
    if draft is not None:
        payload["draft"] = draft
        honors = _honors(loader, gsis_id, identity)
        if honors is not None:
            payload["honors"] = honors

    regular = _career_table(loader, gsis_id, SEASON_TABLE, line, with_leaders=True) if has_reg else None
    if regular is not None:
        payload["career_regular"] = regular
    postseason = (
        _career_table(loader, gsis_id, "player_season_post", line, with_leaders=False)
        if has_post else None
    )
    if postseason is not None:
        payload["career_postseason"] = postseason

    tiles = _tiles(loader, gsis_id, group, regular, postseason, snaps_available)
    if tiles:
        payload["tiles"] = tiles

    if has_week:
        recent = _last_games(loader, gsis_id, limit=5)
        if recent:
            payload["last_games"] = recent

    payload["coverage"] = _player_coverage(loader, gsis_id, identity)
    payload["available_tabs"] = {
        "gamelog": has_week,
        "splits": (group or "").upper() in OFFENSIVE_GROUPS,
        "splits_note": (
            None
            if (group or "").upper() in OFFENSIVE_GROUPS
            else (
                "Splits are built from the passer, rusher and receiver on each play, so "
                "there is nothing to credit a defensive or line player with."
            )
        ),
        "advanced": True,
    }
    return payload


def _status_label(identity: dict[str, Any], newest: int | None) -> str:
    last = identity.get("last_season")
    if last is None:
        return "No season on file"
    if newest is not None and last >= newest:
        return "Active"
    return f"Last played {last}"


def _honors(loader: Any, gsis_id: str, identity: dict[str, Any]) -> dict[str, Any] | None:
    """PFR's career honors, for drafted players only.

    `car_av` is NULL in every row of the draft file, so the AV shown here is
    `w_av`, PFR's weighted career figure, and it is labelled as such wherever it
    appears (SPEC 0.4). An undrafted player has no row and no honors block.
    """
    if not ensure_source(loader, "draft_picks"):
        return None
    columns = table_columns(loader, "draft_picks")
    key = first_present(columns, ("gsis_id",))
    if key is None:
        return None
    wanted = [c for c in ("hof", "probowls", "allpro", "w_av", "dr_av", "seasons_started") if c in columns]
    if not wanted:
        return None
    cur = loader.cursor()
    row = cur.execute(
        f"SELECT {', '.join(wanted)} FROM draft_picks WHERE {key} = ?", [gsis_id]
    ).fetchone()
    if row is None:
        return None
    values = dict(zip(wanted, row))
    if all(value is None for value in values.values()):
        return None
    return {
        "hof": bool(values.get("hof")) if values.get("hof") is not None else None,
        "pro_bowls": values.get("probowls"),
        "all_pros": values.get("allpro"),
        "weighted_career_av": values.get("w_av"),
        "draft_av": values.get("dr_av"),
        "seasons_started": values.get("seasons_started"),
        "av_label": "Weighted career AV (PFR, drafted players only)",
        "source_note": (
            "Pro-Football-Reference career totals, published in the draft file and "
            "therefore present for drafted players only. PFR's career AV column is "
            "empty in every row of that file; this is w_av, its weighted figure."
        ),
    }


def _tiles(
    loader: Any,
    gsis_id: str,
    group: str | None,
    regular: dict[str, Any] | None,
    postseason: dict[str, Any] | None,
    snaps_available: bool,
) -> list[dict[str, Any]]:
    """Up to four at-a-glance tiles. A tile with no honest context line is dropped.

    Up to four, not exactly four: a lineman has no season stat row and no career
    rate to rank, and three real tiles beat four with two of them empty (SPEC
    section 3, correction 2).
    """
    tiles: list[dict[str, Any]] = []
    reg_games = (regular or {}).get("total", {}).get("games")
    post_games = (postseason or {}).get("total", {}).get("games")
    if reg_games is not None or post_games is not None:
        tiles.append(
            {
                "id": "games",
                "label": "Games",
                "value": (reg_games or 0) + (post_games or 0),
                "unit": "count",
                "context": (
                    f"{int(reg_games or 0)} regular season"
                    + (f" · {int(post_games)} postseason" if post_games else "")
                ),
                "computed_by_us": False,
            }
        )

    columns = table_columns(loader, SEASON_TABLE)
    headline = _headline_for(group, columns)
    if headline is not None and regular is not None:
        option, column = headline
        value = regular["total"]["stats"].get(option.id)
        if value is None:
            # The career table keys on the stat line's id, which does not always
            # match the headline's; fall back to reading the column directly.
            value = _career_column_total(loader, gsis_id, column)
        if value is not None:
            rank = _career_rank(loader, gsis_id, group, column)
            tiles.append(
                {
                    "id": option.id,
                    "label": f"Career {option.label.lower()}",
                    "value": value,
                    "unit": option.unit,
                    "context": (
                        f"{_ordinal(rank['rank'])} of {rank['n']} {group or 'players'} "
                        f"since {sources.get('player_season_reg').first_season}"
                        if rank else
                        f"Regular season, from {sources.get('player_season_reg').first_season}"
                    ),
                    "computed_by_us": bool(rank),
                }
            )

    rate = percentiles.headline_rate(gsis_id, loader=loader)
    if rate is not None and rate["value"] is not None:
        context = f"{rate['label']} · cohort of {rate['cohort']['n']}"
        if rate["percentile"] is not None:
            context = (
                f"{_ordinal(int(round(rate['percentile'])))} percentile of "
                f"{rate['n']} qualified {group or 'players'}"
            )
        tiles.append(
            {
                "id": rate["id"],
                "label": rate["label"],
                "value": round(rate["value"], 3),
                "unit": rate["unit"],
                "context": context,
                "computed_by_us": True,
            }
        )

    if snaps_available:
        share = _latest_snap_shares(loader, [gsis_id]).get(gsis_id)
        if share is not None:
            tiles.append(
                {
                    "id": "snap_share",
                    "label": "Snap share",
                    "value": share["share"],
                    "unit": "percent",
                    "context": (
                        f"{share['season']} offence · snap counts from "
                        f"{sources.SNAP_COUNTS_FIRST_SEASON}"
                    ),
                    "computed_by_us": True,
                }
            )
    return tiles[:4]


def _career_column_total(loader: Any, gsis_id: str, column: str) -> float | None:
    cur = loader.cursor()
    row = cur.execute(
        f'SELECT sum(CAST("{column}" AS DOUBLE)) FROM {SEASON_TABLE} WHERE player_id = ?',
        [gsis_id],
    ).fetchone()
    return _as_float(row[0]) if row else None


def _career_rank(loader: Any, gsis_id: str, group: str | None, column: str) -> dict[str, int] | None:
    """Where this career total sits among the position group's, over our window.

    "Modern era" is not a flourish: the window is whatever the season file covers,
    which is why the tile's context line prints its first season rather than saying
    all-time.
    """
    columns = table_columns(loader, SEASON_TABLE)
    if "position_group" not in columns or not group:
        return None
    cur = loader.cursor()
    row = cur.execute(
        f"""
        WITH totals AS (
            SELECT player_id, sum(CAST("{column}" AS DOUBLE)) AS v
            FROM {SEASON_TABLE}
            WHERE player_id IS NOT NULL AND position_group = ?
            GROUP BY player_id HAVING sum(CAST("{column}" AS DOUBLE)) IS NOT NULL
        )
        SELECT
            (SELECT count(*) FROM totals) AS n,
            (SELECT count(*) FROM totals t2 WHERE t2.v > (SELECT v FROM totals WHERE player_id = ?)) + 1 AS rank
        """,
        [group, gsis_id],
    ).fetchone()
    if row is None or row[0] in (None, 0):
        return None
    own = cur.execute(
        f'SELECT sum(CAST("{column}" AS DOUBLE)) FROM {SEASON_TABLE} WHERE player_id = ?',
        [gsis_id],
    ).fetchone()
    if own is None or own[0] is None:
        return None
    return {"n": int(row[0]), "rank": int(row[1])}


def _ordinal(value: int | None) -> str:
    if value is None:
        return "—"
    suffix = "th"
    if value % 100 not in (11, 12, 13):
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


# --- coverage windows for one player ---------------------------------------------

#: Per-source id column candidates. `gsis` sources join straight through; the rest
#: reach the player by the cross-system id the file actually carries.
_COVERAGE_SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("player_season_reg", "gsis", ("player_id", "gsis_id")),
    ("player_season_post", "gsis", ("player_id", "gsis_id")),
    ("player_week", "gsis", ("player_id", "gsis_id")),
    ("snap_counts", "pfr", ("pfr_player_id", "pfr_id")),
    ("injuries", "gsis", ("gsis_id", "player_id")),
    ("ngs_passing", "gsis", ("player_gsis_id", "gsis_id", "player_id")),
    ("ngs_rushing", "gsis", ("player_gsis_id", "gsis_id", "player_id")),
    ("ngs_receiving", "gsis", ("player_gsis_id", "gsis_id", "player_id")),
    ("advstats_pass", "pfr", ("pfr_id", "pfr_player_id")),
    ("advstats_rush", "pfr", ("pfr_id", "pfr_player_id")),
    ("advstats_rec", "pfr", ("pfr_id", "pfr_player_id")),
    ("advstats_def", "pfr", ("pfr_id", "pfr_player_id")),
    ("qbr_season", "espn", ("player_id", "espn_id")),
)


def _source_window(
    loader: Any, source_id: str, id_kind: str, candidates: Sequence[str], identity: dict[str, Any]
) -> dict[str, Any]:
    """One source's window *for this player*, measured from his own rows.

    The registry's first season says when a dataset begins; it says nothing about
    when this player appears in it. A coverage banner built from the constant would
    tell a 2019 rookie that his Next Gen Stats run from 2016.
    """
    source = sources.get(source_id)
    entry: dict[str, Any] = {
        "source": source_id,
        "name": source.name,
        "declared_first_season": source.first_season,
        "available": False,
        "rows": 0,
        "first_season": None,
        "last_season": None,
        "note": None,
    }
    key = {"gsis": identity["gsis_id"], "pfr": identity["pfr_id"], "espn": identity["espn_id"]}[id_kind]
    if key is None:
        entry["note"] = f"This player has no {id_kind} id, which is how {source.name} is joined."
        return entry
    columns = table_columns(loader, source.table)
    if not columns:
        entry["note"] = "Not loaded in this deployment."
        return entry
    entry["available"] = True
    column = first_present(columns, candidates)
    if column is None:
        entry["note"] = "The loaded file carries no id column we can join a player on."
        return entry
    cur = loader.cursor()
    season_select = "min(season), max(season)" if "season" in columns else "NULL, NULL"
    row = cur.execute(
        f'SELECT count(*), {season_select} FROM {source.table} WHERE CAST("{column}" AS VARCHAR) = ?',
        [str(key)],
    ).fetchone()
    entry["rows"] = int(row[0])
    entry["first_season"] = row[1]
    entry["last_season"] = row[2]
    if entry["rows"] == 0:
        entry["note"] = "No rows for this player."
    return entry


def _player_coverage(loader: Any, gsis_id: str, identity: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for source_id, id_kind, candidates in _COVERAGE_SOURCES:
        ensure_source(loader, source_id)
        out.append(_source_window(loader, source_id, id_kind, candidates, identity))
    return out


# --- game log ---------------------------------------------------------------------

#: Standard fantasy scoring, and the two receptions variants. The coefficients are
#: the common public rules, not ours, and the payload names every component it
#: could actually find so a missing column shows up as a stated gap rather than as
#: a quietly smaller score.
_FANTASY: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("passing_yards", ("passing_yards",), 0.04),
    ("passing_tds", ("passing_tds",), 4.0),
    ("interceptions", ("passing_interceptions", "interceptions"), -2.0),
    ("rushing_yards", ("rushing_yards",), 0.1),
    ("rushing_tds", ("rushing_tds",), 6.0),
    ("receiving_yards", ("receiving_yards",), 0.1),
    ("receiving_tds", ("receiving_tds",), 6.0),
    ("fumbles_lost", ("rushing_fumbles_lost",), -2.0),
    ("fumbles_lost_receiving", ("receiving_fumbles_lost",), -2.0),
    ("fumbles_lost_sack", ("sack_fumbles_lost",), -2.0),
)

#: The share of his team's snaps above which we call a player a starter. Nothing in
#: any verified source marks who started (SPEC section 7), so this is ours and is
#: labelled a proxy everywhere it renders.
STARTED_PROXY_SHARE = 0.5


def _fantasy_sql(columns: Iterable[str]) -> tuple[str, list[str], list[str]]:
    terms: list[str] = []
    used: list[str] = []
    missing: list[str] = []
    for name, candidates, coefficient in _FANTASY:
        column = first_present(columns, candidates)
        if column is None:
            missing.append(name)
            continue
        used.append(column)
        terms.append(f'{coefficient} * COALESCE(CAST("{column}" AS DOUBLE), 0)')
    return (" + ".join(terms) if terms else "NULL"), used, missing


def player_gamelog(
    gsis_id: str,
    *,
    season: int | None = None,
    season_type: str = "all",
    loader: Any = None,
) -> dict[str, Any] | None:
    """One row per game: the box line, snaps, game EPA and fantasy points.

    The three optional joins — snap counts, the derived per-game EPA table, and
    the schedule — are fetched separately and merged in Python rather than bolted
    onto one wide LEFT JOIN. Each can be missing on its own (snaps start in 2012,
    the derived table may not be built yet), and merging lets each disappear from
    the payload independently instead of turning every column null at once.
    """
    loader = resolve_loader(loader)
    if not ensure_source(loader, "players"):
        return None
    identity = _identity_row(loader, gsis_id)
    if identity is None:
        return None
    if not ensure_source(loader, "player_week"):
        return {
            "gsis_id": gsis_id,
            "rows": [],
            "note": "Weekly player stats are not loaded in this deployment.",
        }

    columns = table_columns(loader, "player_week")
    fantasy_sql, used, missing = _fantasy_sql(columns)
    group = position_group_for(loader, gsis_id) or identity.get("position_group")
    line = STAT_LINES.get((group or "").upper(), ())
    stats, _ = _stat_selects(line, columns)
    stat_columns = [(s, first_present(columns, s.columns)) for s in stats]
    stat_columns = [(s, c) for s, c in stat_columns if c is not None and not s.is_rate]

    where = ["w.player_id = ?"]
    params: list[Any] = [gsis_id]
    if season is not None:
        where.append("w.season = ?")
        params.append(int(season))
    if season_type in ("reg", "post") and "season_type" in columns:
        where.append("w.season_type = ?")
        params.append("REG" if season_type == "reg" else "POST")

    has_games = ensure_source(loader, "games")
    stat_select = "".join(f', CAST(w."{c}" AS DOUBLE) AS "s_{s.id}"' for s, c in stat_columns)
    game_select = (
        """,
        g.game_id, g.gameday, g.game_type, g.roof, g.surface, g.div_game,
        CASE WHEN g.home_team = w.team THEN 'home' ELSE 'away' END AS home_away,
        CASE WHEN g.home_team = w.team THEN g.home_score ELSE g.away_score END AS team_score,
        CASE WHEN g.home_team = w.team THEN g.away_score ELSE g.home_score END AS opp_score
        """
        if has_games
        else ", NULL AS game_id, NULL AS gameday, NULL AS game_type, NULL AS roof, "
             "NULL AS surface, NULL AS div_game, NULL AS home_away, "
             "NULL AS team_score, NULL AS opp_score"
    )
    join = (
        """
        LEFT JOIN games g
          ON g.season = w.season AND g.week = w.week
         AND (g.home_team = w.team OR g.away_team = w.team)
         AND (g.home_team = w.opponent_team OR g.away_team = w.opponent_team)
        """
        if has_games
        else ""
    )
    # PPR is standard plus one point per reception, so the receptions column is
    # selected beside the standard score rather than folded into it — a file with
    # no receptions column then yields a standard score and an honest null for the
    # two reception formats, not three equal numbers.
    receptions_sql = (
        'COALESCE(CAST(w."receptions" AS DOUBLE), 0)' if "receptions" in columns else "NULL"
    )
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT w.season, w.week, w.season_type, w.team, w.opponent_team,
               ({fantasy_sql}) AS fantasy_std,
               {receptions_sql} AS receptions_for_ppr
               {stat_select}
               {game_select}
        FROM player_week w
        {join}
        WHERE {' AND '.join(where)}
        ORDER BY w.season, w.week
        """,
        params,
    ).fetchall()

    snaps = _snaps_by_week(loader, identity)
    epa = _epa_by_week(loader, gsis_id)
    birth_date = identity["birth_date"]

    out: list[dict[str, Any]] = []
    offset = 7
    for row in rows:
        season_v, week, stype, team, opponent = row[0], row[1], row[2], row[3], row[4]
        standard = _as_float(row[5])
        receptions = _as_float(row[6])
        stats_values = {
            stat.id: _as_float(row[offset + index]) for index, (stat, _) in enumerate(stat_columns)
        }
        tail = offset + len(stat_columns)
        game_id, gameday, game_type, roof, surface, div_game = row[tail:tail + 6]
        home_away, team_score, opp_score = row[tail + 6:tail + 9]
        snap = snaps.get((season_v, week))
        game_epa = epa.get((season_v, week))
        out.append(
            {
                "season": int(season_v),
                "week": int(week) if week is not None else None,
                "season_type": stype,
                "game_id": game_id,
                "game_href": f"/games/{game_id}" if game_id else None,
                "gameday": _date(gameday).isoformat() if _date(gameday) else None,
                "game_type": game_type,
                "team": team,
                "team_href": f"/teams/{team}/{int(season_v)}" if team else None,
                "opponent": opponent,
                "opponent_href": f"/teams/{opponent}/{int(season_v)}" if opponent else None,
                "home_away": home_away,
                "team_score": team_score,
                "opp_score": opp_score,
                "result": _result(team_score, opp_score),
                "roof": roof,
                "surface": surface,
                "div_game": bool(div_game) if div_game is not None else None,
                "age": _age(birth_date, gameday),
                "stats": stats_values,
                "offense_snaps": None if snap is None else snap["offense_snaps"],
                "offense_pct": None if snap is None else snap["offense_pct"],
                "defense_snaps": None if snap is None else snap["defense_snaps"],
                "st_snaps": None if snap is None else snap["st_snaps"],
                "started_proxy": None if snap is None else snap["started_proxy"],
                "epa": None if game_epa is None else game_epa["epa"],
                "plays": None if game_epa is None else game_epa["plays"],
                "success_rate": None if game_epa is None else game_epa["success_rate"],
                "fantasy_standard": standard,
                "fantasy_ppr": None if standard is None or receptions is None else standard + receptions,
                "fantasy_half": None if standard is None or receptions is None else standard + 0.5 * receptions,
            }
        )

    games = len(out)
    totals = {
        stat.id: _sum_optional(row["stats"].get(stat.id) for row in out)
        for stat, _ in stat_columns
    }
    for key in ("fantasy_standard", "fantasy_ppr", "fantasy_half"):
        totals[key] = _sum_optional(row[key] for row in out)
    averages = {
        key: (None if value is None or not games else round(value / games, 3))
        for key, value in totals.items()
    }

    payload: dict[str, Any] = {
        "gsis_id": gsis_id,
        "display_name": identity["display_name"],
        "position_group": group,
        "season": season,
        "season_type": season_type,
        "columns": [
            {"id": stat.id, "label": stat.label, "unit": stat.unit} for stat, _ in stat_columns
        ],
        "rows": out,
        "games": games,
        "totals": totals,
        "averages": averages,
        "splits_summary": _gamelog_summary(out),
        "started_proxy": {
            "rule": (
                f"Started is a proxy: at least {int(STARTED_PROXY_SHARE * 100)}% of his "
                "team's offensive snaps in that game."
            ),
            "why": (
                "Nothing in the verified data marks who started, so this is our "
                "approximation and is never presented as the official designation."
            ),
            "computed_by_us": True,
            "first_season": sources.SNAP_COUNTS_FIRST_SEASON,
        },
        "fantasy": {
            "computed_by_us": True,
            "formats": ["standard", "ppr", "half"],
            "columns_used": used,
            "components_missing": missing,
            "note": (
                "Computed in SQL from the box line, never stored. PPR adds one point "
                "per reception and half-PPR adds half of one."
            ),
        },
    }
    if not out:
        payload["note"] = "No game rows on file for this player in the requested scope."
    return payload


def _result(team_score: Any, opp_score: Any) -> str | None:
    if team_score is None or opp_score is None:
        return None
    if team_score > opp_score:
        return "W"
    if team_score < opp_score:
        return "L"
    return "T"


def _gamelog_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "games": len(rows),
        "home": sum(1 for r in rows if r["home_away"] == "home"),
        "away": sum(1 for r in rows if r["home_away"] == "away"),
        "wins": sum(1 for r in rows if r["result"] == "W"),
        "losses": sum(1 for r in rows if r["result"] == "L"),
        "ties": sum(1 for r in rows if r["result"] == "T"),
    }


def _snaps_by_week(loader: Any, identity: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    resolved = _snap_columns(loader)
    if resolved is None or identity.get("pfr_id") is None or "week" not in resolved:
        return {}
    offense = resolved.get("offense_snaps")
    pct = resolved.get("offense_pct")
    cur = loader.cursor()
    select = [f'"{resolved["week"]}"', "season"]
    select.append(f'CAST("{offense}" AS DOUBLE)' if offense else "NULL")
    select.append(_pct_sql(f'"{pct}"') if pct else "NULL")
    select.append(
        f'CAST("{resolved["defense_snaps"]}" AS DOUBLE)' if "defense_snaps" in resolved else "NULL"
    )
    select.append(f'CAST("{resolved["st_snaps"]}" AS DOUBLE)' if "st_snaps" in resolved else "NULL")
    rows = cur.execute(
        f'SELECT {", ".join(select)} FROM snap_counts WHERE "{resolved["key"]}" = ?',
        [identity["pfr_id"]],
    ).fetchall()
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for week, season, offense_snaps, offense_pct, defense_snaps, st_snaps in rows:
        out[(int(season), int(week))] = {
            "offense_snaps": _as_float(offense_snaps),
            "offense_pct": None if offense_pct is None else round(float(offense_pct) * 100, 1),
            "defense_snaps": _as_float(defense_snaps),
            "st_snaps": _as_float(st_snaps),
            "started_proxy": (
                None if offense_pct is None else bool(float(offense_pct) >= STARTED_PROXY_SHARE)
            ),
        }
    return out


def _epa_by_week(loader: Any, gsis_id: str) -> dict[tuple[int, int], dict[str, Any]]:
    """Per-game EPA, summed over the roles this player filled in that game.

    Roles do not overlap for one player on one play — a passer is not also the
    receiver — so summing them is a sum over his plays, not a double count.
    """
    if not _ensure_pbp_derived(loader, "derived_player_game_epa"):
        return {}
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT season, week, sum(plays), sum(epa_total), sum(successes)
        FROM derived_player_game_epa WHERE gsis_id = ?
        GROUP BY season, week
        """,
        [gsis_id],
    ).fetchall()
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for season, week, plays, epa_total, successes in rows:
        out[(int(season), int(week))] = {
            "plays": int(plays) if plays is not None else None,
            "epa": _as_float(epa_total),
            "success_rate": _rate(_as_float(successes), _as_float(plays)),
        }
    return out


def _ensure_pbp_derived(loader: Any, table: str) -> bool:
    """Build the play-derived tables if they are stale, and say if we have them.

    `loader.SeasonBusy` is deliberately not caught: two play-by-play seasons are
    already materialising and the honest answer to this request is "try again in a
    few seconds", which the router turns into a 503.
    """
    try:
        derived.ensure(loader, pbp_derive.DERIVED_NAME, table=table)
    except SeasonBusy:
        raise
    except Exception:  # noqa: BLE001 - availability, not failure; see ensure_source
        logger.warning("Play-derived tables are unavailable", exc_info=True)
    return loader.table_exists(table)


def _last_games(loader: Any, gsis_id: str, *, limit: int) -> list[dict[str, Any]]:
    """The most recent games, for the hub's five-row strip."""
    if not ensure_source(loader, "games"):
        return []
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT w.season, w.week, w.team, w.opponent_team, g.game_id, g.gameday,
               CASE WHEN g.home_team = w.team THEN 'home' ELSE 'away' END,
               CASE WHEN g.home_team = w.team THEN g.home_score ELSE g.away_score END,
               CASE WHEN g.home_team = w.team THEN g.away_score ELSE g.home_score END
        FROM player_week w
        JOIN games g
          ON g.season = w.season AND g.week = w.week
         AND (g.home_team = w.team OR g.away_team = w.team)
         AND (g.home_team = w.opponent_team OR g.away_team = w.opponent_team)
        WHERE w.player_id = ?
        ORDER BY g.gameday DESC, w.week DESC
        LIMIT ?
        """,
        [gsis_id, limit],
    ).fetchall()
    return [
        {
            "season": int(row[0]),
            "week": int(row[1]) if row[1] is not None else None,
            "team": row[2],
            "opponent": row[3],
            "game_id": row[4],
            "game_href": f"/games/{row[4]}" if row[4] else None,
            "gameday": _date(row[5]).isoformat() if _date(row[5]) else None,
            "home_away": row[6],
            "team_score": row[7],
            "opp_score": row[8],
            "result": _result(row[7], row[8]),
        }
        for row in rows
    ]


# --- splits -----------------------------------------------------------------------

SMALL_SAMPLE_PLAYS = 20


def player_splits(
    gsis_id: str,
    *,
    season: int | str | None = CAREER,
    season_type: str = "reg",
    loader: Any = None,
) -> dict[str, Any] | None:
    """Situational, game-context and opponent splits for one player.

    Career scope is a SUM over the stored season rows and every rate is pooled from
    those sums — the whole point of `derived_player_season_situational` is that a
    fifteen-season career split adds a few hundred narrow rows instead of scanning
    fifteen seasons of plays (SPEC 0.7).
    """
    loader = resolve_loader(loader)
    if not ensure_source(loader, "players"):
        return None
    identity = _identity_row(loader, gsis_id)
    if identity is None:
        return None
    group = (position_group_for(loader, gsis_id) or identity.get("position_group") or "").upper()

    scope_season = None if season in (None, CAREER) else int(season)
    payload: dict[str, Any] = {
        "gsis_id": gsis_id,
        "display_name": identity["display_name"],
        "position_group": group or None,
        "scope": CAREER if scope_season is None else "season",
        "season": scope_season,
        "season_type": season_type,
        "small_sample_plays": SMALL_SAMPLE_PLAYS,
        "method_note": (
            "Computed from play-level data over the window in the registry. Counts are "
            "summed and every rate is recomputed from the sums, never averaged across "
            "seasons."
        ),
        "computed_by_us": True,
    }

    if group not in OFFENSIVE_GROUPS:
        payload["unavailable"] = {
            "reason": (
                f"Splits are not available for {group or 'this'} players."
                if group else "Splits are not available for this position."
            ),
            "why": (
                "Every split is built from the passer, rusher and receiver credited on "
                "each play. Those are the only three roles the play-by-play data names, "
                "so a defensive or offensive-line player has no plays to split — the "
                "table would be empty rather than wrong."
            ),
            "roles": [role.key for role in buckets.ROLES],
        }
        return payload

    if not _ensure_pbp_derived(loader, "derived_player_season_situational"):
        payload["unavailable"] = {
            "reason": "The situational splits table has not been built in this deployment.",
            "why": "It is derived from play-by-play, which the build job produces season by season.",
            "roles": [role.key for role in buckets.ROLES],
        }
        return payload

    where = ["gsis_id = ?"]
    params: list[Any] = [gsis_id]
    if scope_season is not None:
        where.append("season = ?")
        params.append(scope_season)
    if season_type in ("reg", "post"):
        where.append("season_type = ?")
        params.append("REG" if season_type == "reg" else "POST")

    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT role, bucket, sum(plays), sum(epa_total), sum(successes),
               sum(yards), sum(touchdowns), sum(first_downs),
               min(season), max(season)
        FROM derived_player_season_situational
        WHERE {' AND '.join(where)}
        GROUP BY role, bucket
        """,
        params,
    ).fetchall()

    if rows:
        by_role: dict[str, list[dict[str, Any]]] = {}
        for role, bucket_key, plays, epa_total, successes, yards, tds, first_downs, first, last in rows:
            plays = int(plays or 0)
            by_role.setdefault(role, []).append(
                {
                    "bucket": bucket_key,
                    "label": buckets.bucket(bucket_key).label,
                    "plays": plays,
                    "yards": _as_float(yards),
                    "touchdowns": int(tds) if tds is not None else None,
                    "first_downs": int(first_downs) if first_downs is not None else None,
                    "epa": _as_float(epa_total),
                    "epa_per_play": _rate(_as_float(epa_total), plays),
                    "success_rate": _rate(_as_float(successes), plays),
                    "yards_per_play": _rate(_as_float(yards), plays),
                    "low_sample": plays < SMALL_SAMPLE_PLAYS,
                    "first_season": int(first),
                    "last_season": int(last),
                }
            )
        order = {bucket.key: index for index, bucket in enumerate(buckets.BUCKETS)}
        payload["situation"] = [
            {
                "role": role,
                "label": buckets.role(role).label,
                "buckets": sorted(entries, key=lambda e: order.get(e["bucket"], 99)),
            }
            for role, entries in sorted(by_role.items())
        ]
        payload["low_sample_note"] = (
            f"Buckets under {SMALL_SAMPLE_PLAYS} plays are flagged with their n. Nothing "
            "is hidden, but nothing pretends to be stable."
        )
        payload["buckets_overlap_note"] = (
            "The buckets overlap on purpose — one play can be third down, long, second "
            "half and trailing at once — so they never sum to a season total."
        )

    context = _game_context_splits(loader, gsis_id, scope_season, season_type)
    if context:
        payload["game_context"] = context
    opponents = _opponent_splits(loader, gsis_id, scope_season, season_type)
    if opponents:
        payload["opponents"] = opponents
    if "situation" not in payload and not context and not opponents:
        payload["note"] = "No plays on file for this player in the requested scope."
    return payload


def _context_rows(
    loader: Any, gsis_id: str, season: int | None, season_type: str, key_sql: str, label: str
) -> list[dict[str, Any]]:
    if not (loader.table_exists("player_week") and loader.table_exists("games")):
        return []
    columns = table_columns(loader, "player_week")
    fantasy_sql, _, _ = _fantasy_sql(columns)
    where = ["w.player_id = ?"]
    params: list[Any] = [gsis_id]
    if season is not None:
        where.append("w.season = ?")
        params.append(season)
    if season_type in ("reg", "post") and "season_type" in columns:
        where.append("w.season_type = ?")
        params.append("REG" if season_type == "reg" else "POST")
    yardage = [
        first_present(columns, (name,))
        for name in ("passing_yards", "rushing_yards", "receiving_yards")
    ]
    yardage_sql = ", ".join(
        f'sum(CAST(w."{column}" AS DOUBLE))' if column else "NULL"
        for column in yardage
    )
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT {key_sql} AS bucket, count(*) AS games,
               {yardage_sql},
               sum({fantasy_sql}) AS fantasy_standard
        FROM player_week w
        JOIN games g
          ON g.season = w.season AND g.week = w.week
         AND (g.home_team = w.team OR g.away_team = w.team)
         AND (g.home_team = w.opponent_team OR g.away_team = w.opponent_team)
        WHERE {' AND '.join(where)}
        GROUP BY bucket
        ORDER BY bucket
        """,
        params,
    ).fetchall()
    return [
        {
            "group": label,
            "bucket": str(row[0]) if row[0] is not None else None,
            "games": int(row[1]),
            "passing_yards": _as_float(row[2]),
            "rushing_yards": _as_float(row[3]),
            "receiving_yards": _as_float(row[4]),
            "fantasy_standard": _as_float(row[5]),
        }
        for row in rows
        if row[0] is not None
    ]


def _game_context_splits(
    loader: Any, gsis_id: str, season: int | None, season_type: str
) -> list[dict[str, Any]]:
    """Home/away, result, division game, roof and surface — from the schedule file.

    These are game-level, not play-level: `player_week` joined to `games`, so the
    counts here are games, and they are deliberately kept separate from the
    play-level situational table above rather than mixed into one list.
    """
    columns = table_columns(loader, "player_week")
    if not columns:
        return []
    out: list[dict[str, Any]] = []
    out += _context_rows(
        loader, gsis_id, season, season_type,
        "CASE WHEN g.home_team = w.team THEN 'Home' ELSE 'Away' END", "Venue",
    )
    out += _context_rows(
        loader, gsis_id, season, season_type,
        """CASE
             WHEN (CASE WHEN g.home_team = w.team THEN g.home_score ELSE g.away_score END)
                > (CASE WHEN g.home_team = w.team THEN g.away_score ELSE g.home_score END) THEN 'Win'
             WHEN (CASE WHEN g.home_team = w.team THEN g.home_score ELSE g.away_score END)
                < (CASE WHEN g.home_team = w.team THEN g.away_score ELSE g.home_score END) THEN 'Loss'
             WHEN g.home_score IS NULL THEN NULL ELSE 'Tie' END""",
        "Result",
    )
    out += _context_rows(
        loader, gsis_id, season, season_type,
        "CASE WHEN g.div_game = 1 THEN 'Division game' ELSE 'Non-division' END", "Opponent type",
    )
    out += _context_rows(loader, gsis_id, season, season_type, "g.roof", "Roof")
    out += _context_rows(loader, gsis_id, season, season_type, "g.surface", "Surface")
    return out


def _opponent_splits(
    loader: Any, gsis_id: str, season: int | None, season_type: str
) -> list[dict[str, Any]]:
    rows = _context_rows(loader, gsis_id, season, season_type, "w.opponent_team", "Opponent")
    for row in rows:
        row["opponent"] = row["bucket"]
        row["opponent_href"] = f"/teams/{row['bucket']}" if row["bucket"] else None
    return rows


# --- advanced ----------------------------------------------------------------------

#: Which advanced sources a position group actually has rows in. Listed rather than
#: fetched blindly so a defensive back's page does not carry four empty NGS blocks.
_NGS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "QB": ("ngs_passing",),
    "RB": ("ngs_rushing", "ngs_receiving"),
    "FB": ("ngs_rushing",),
    "WR": ("ngs_receiving",),
    "TE": ("ngs_receiving",),
}

_ADVSTATS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "QB": ("advstats_pass",),
    "RB": ("advstats_rush", "advstats_rec"),
    "FB": ("advstats_rush",),
    "WR": ("advstats_rec",),
    "TE": ("advstats_rec",),
    "DL": ("advstats_def",),
    "LB": ("advstats_def",),
    "DB": ("advstats_def",),
}


def _advanced_block(
    loader: Any,
    source_id: str,
    id_kind: str,
    candidates: Sequence[str],
    identity: dict[str, Any],
    season: int | None,
) -> dict[str, Any] | None:
    """One advanced source's rows for this player, or None if there are none.

    None, not an empty list: the caller drops the block from the payload and the
    coverage banner says why it is not there.
    """
    if not ensure_source(loader, source_id):
        return None
    source = sources.get(source_id)
    columns = table_columns(loader, source.table)
    key = {"gsis": identity["gsis_id"], "pfr": identity["pfr_id"], "espn": identity["espn_id"]}[id_kind]
    if key is None:
        return None
    column = first_present(columns, candidates)
    if column is None:
        return None
    where = [f'CAST("{column}" AS VARCHAR) = ?']
    params: list[Any] = [str(key)]
    if season is not None and "season" in columns:
        where.append("season = ?")
        params.append(season)
    cur = loader.cursor()
    rows = cur.execute(
        f"SELECT * FROM {source.table} WHERE {' AND '.join(where)}"
        + (" ORDER BY season" if "season" in columns else ""),
        params,
    ).fetchall()
    if not rows:
        return None
    names = [d[0] for d in cur.description]
    seasons = [r[names.index("season")] for r in rows] if "season" in names else []
    return {
        "source": source_id,
        "name": source.name,
        "declared_first_season": source.first_season,
        "first_season": min(seasons) if seasons else None,
        "last_season": max(seasons) if seasons else None,
        "columns": names,
        "rows": [dict(zip(names, row)) for row in rows],
    }


def player_advanced(
    gsis_id: str, *, season: int | None = None, loader: Any = None
) -> dict[str, Any] | None:
    """NGS, PFR charting, snaps and QBR — each with its window for this player.

    The coverage banner is built from the player's own rows. The registry's first
    season goes alongside it, so the page can say both "Next Gen Stats begin in
    2016" and "this player's begin in 2019" without either standing in for the other.
    """
    loader = resolve_loader(loader)
    if not ensure_source(loader, "players"):
        return None
    identity = _identity_row(loader, gsis_id)
    if identity is None:
        return None
    group = (position_group_for(loader, gsis_id) or identity.get("position_group") or "").upper()

    payload: dict[str, Any] = {
        "gsis_id": gsis_id,
        "display_name": identity["display_name"],
        "position_group": group or None,
        "season": season,
    }

    coverage: list[dict[str, Any]] = []
    blocks: dict[str, list[dict[str, Any]]] = {"ngs": [], "advstats": []}

    for kind, mapping, id_kind, candidates in (
        ("ngs", _NGS_BY_GROUP, "gsis", ("player_gsis_id", "gsis_id", "player_id")),
        ("advstats", _ADVSTATS_BY_GROUP, "pfr", ("pfr_id", "pfr_player_id")),
    ):
        for source_id in mapping.get(group, ()):
            block = _advanced_block(loader, source_id, id_kind, candidates, identity, season)
            entry = _source_window(loader, source_id, id_kind, candidates, identity)
            coverage.append(entry)
            if block is not None:
                blocks[kind].append(block)

    if blocks["ngs"]:
        payload["ngs"] = blocks["ngs"]
    if blocks["advstats"]:
        payload["advstats"] = blocks["advstats"]

    qbr = (
        _advanced_block(loader, "qbr_season", "espn", ("player_id", "espn_id"), identity, season)
        if group == "QB"
        else None
    )
    if group == "QB":
        coverage.append(
            _source_window(loader, "qbr_season", "espn", ("player_id", "espn_id"), identity)
        )
    if qbr is not None:
        payload["qbr"] = qbr

    snaps = _snap_seasons(loader, identity, season)
    coverage.append(
        _source_window(loader, "snap_counts", "pfr", ("pfr_player_id", "pfr_id"), identity)
    )
    if snaps:
        payload["snaps"] = snaps

    payload["coverage"] = coverage
    payload["coverage_note"] = (
        "Each window below is this player's own first and last season in that file, "
        "beside the season the dataset itself begins. A source with no rows for him is "
        "named here and has no block above."
    )
    if not any(key in payload for key in ("ngs", "advstats", "qbr", "snaps")):
        payload["note"] = (
            "None of the advanced sources cover this player. The windows below say which "
            "were checked and why each is empty."
        )
    return payload


def _snap_seasons(
    loader: Any, identity: dict[str, Any], season: int | None
) -> list[dict[str, Any]]:
    """Season snap totals and a pooled share, plus the weekly rows behind them."""
    resolved = _snap_columns(loader)
    if resolved is None or identity.get("pfr_id") is None:
        return []
    offense = resolved.get("offense_snaps")
    pct = resolved.get("offense_pct")
    if offense is None or pct is None:
        return []
    where = [f'"{resolved["key"]}" = ?']
    params: list[Any] = [identity["pfr_id"]]
    if season is not None:
        where.append("season = ?")
        params.append(season)
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT season,
               sum(CAST("{offense}" AS DOUBLE)) AS snaps,
               sum(CASE WHEN {_pct_sql('"' + pct + '"')} > 0
                        THEN CAST("{offense}" AS DOUBLE) / {_pct_sql('"' + pct + '"')} END) AS team_snaps,
               count(*) AS games
        FROM snap_counts WHERE {' AND '.join(where)}
        GROUP BY season ORDER BY season
        """,
        params,
    ).fetchall()
    return [
        {
            "season": int(row[0]),
            "games": int(row[3]),
            "offense_snaps": _as_float(row[1]),
            "offense_share": (
                None if _rate(_as_float(row[1]), _as_float(row[2])) is None
                else round(_rate(_as_float(row[1]), _as_float(row[2])) * 100, 1)
            ),
            "share_note": (
                "Share is his snaps over his team's, recovered from the per-game "
                "percentages — not the average of them."
            ),
        }
        for row in rows
    ]
