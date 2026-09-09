"""The four questions the season cockpit asks: which season, which season's story,
which season's standings, which week.

Three rules carry the module.

**Structure comes from `alignment.py`, never invented.** Six divisions before 2002,
eight from 2002; six playoff seeds before 2020, seven from 2020; the regular season
runs 17 weeks through 2020 and 18 from 2021. Every one of those facts is read from
`etl/alignment.py`, never hardcoded here (SPEC 0.1).

**Standings and seeding are read, not recomputed here.** `etl/standings.py` already
builds `team_standings` from `games.csv` alone — record, division finish, seed,
tiebreak provenance, SRS-family ratings — and `repo/standings.py` already turns a
season's rows into division/conference/league groupings with formulas attached.
This module calls that layer rather than re-deriving any of it; the playoff bracket
is the one new shape, and it is built from the same seeds, read off `games` for who
actually played whom.

**A leader board with no matching column is missing, not zero.** The six league
leader categories on the season hub each name the columns they need in
`player_season_reg`; a category whose columns are not in this deployment's table is
left out of the `leaders` payload entirely (SPEC: honesty is the product). "Scoring"
is the one computed category — total touchdowns is not a published column — and its
row carries a note naming exactly which touchdown columns were summed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from .. import sources
from ..config import latest_season
from ..deps import get_loader
from ..etl import alignment, derived
from ..etl.pbp_derive import DERIVED_NAME as PBP_DERIVED
from ..etl.standings import ROUND_NAMES, ROUND_ORDER
from . import standings as standings_repo
from .percentiles import ensure_source, first_present, table_columns

logger = logging.getLogger(__name__)

#: Points kept per game in a week scoreboard's win-probability sparkline. The card
#: is a strip a few hundred pixels wide, not the ~120-point full curve the derived
#: table holds for every game since 1999.
WP_SPARKLINE_POINTS = 40

#: League leader boards per season, capped the same way a "snapshot" implies —
#: the full, qualified leaderboard lives at /api/leaders.
LEADER_ROWS = 10

#: Touchdown-type columns that make up "scoring" when they exist. Not every one is
#: in every deployment's `player_season_reg`, so the leader is a sum over whichever
#: of these are actually present, and the row says which.
_SCORING_TD_COLUMNS: tuple[str, ...] = (
    "passing_tds", "rushing_tds", "receiving_tds", "special_teams_tds",
    "def_tds", "fumble_recovery_tds",
)


class SeasonOutOfWindow(ValueError):
    """A season outside the window `sources.FIRST_SEASON`..`latest_season()`."""


# --- small shared helpers ----------------------------------------------------


def _loader(loader: Any) -> Any:
    return loader if loader is not None else get_loader()


#: Whether a source is loaded, never raising — see `percentiles.ensure_source`.
#: An absent source (a season-grained 404, or a deployment that has not reached
#: this dataset yet) drops the blocks that need it; it is never a 500.
_have = ensure_source


def _require_season(season: int) -> int:
    first, last = sources.FIRST_SEASON, latest_season()
    if not first <= season <= last:
        raise SeasonOutOfWindow(
            f"We hold seasons {first} through {last}; {season} is outside that window."
        )
    return season


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _num(value: Any) -> float | int | None:
    """A totalled stat as an int when it is whole, else a rounded float.

    Every leader value here is a SUM of a DOUBLE-typed nflverse column, so a
    touchdown count that landed on `7.0` should read `7`, not `7.0`.
    """
    if value is None:
        return None
    value = float(value)
    whole = round(value)
    return whole if abs(value - whole) < 1e-9 else round(value, 1)


def _branding(loader: Any) -> dict[str, dict[str, Any]]:
    """Colours, logos and names, keyed by current franchise code.

    `team_conf`/`team_division` are never read here: that file carries present-day
    membership only, and grouping a historical season by it silently produces
    divisions that never existed (SPEC 0.1) — `alignment.py` is the only source of
    structure on this surface.
    """
    if not _have(loader, "teams_meta"):
        return {}
    cur = loader.cursor()
    rows = cur.execute(
        "SELECT team_abbr, team_name, team_color, team_color2, "
        "team_logo_espn, team_logo_squared FROM teams_meta"
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for abbr, name, color, color2, logo_espn, logo_sq in rows:
        code = alignment.current_code(abbr)
        if code is None:
            continue
        # The branding file ships the pre-relocation clubs too — STL beside LA,
        # SD beside LAC, OAK beside LV — and they canonicalise onto the same
        # franchise. Last write wins takes whichever the file lists later, which
        # is the historical one, so a present-tense page ends up calling the Rams
        # "St. Louis". A row whose own abbreviation is already the current code
        # wins; historical names come from `alignment.label_in_season`, which has
        # a season to make them right.
        if code in out and abbr != code:
            continue
        out[code] = {
            "name": name,
            "logo": logo_sq or logo_espn,
            "colors": {"primary": color, "secondary": color2},
        }
    return out


def _brand_for(branding: dict[str, dict[str, Any]], code: str) -> dict[str, Any]:
    brand = branding.get(code)
    if brand is None:
        # A code the branding file does not carry keeps its identity — the team is
        # real — and renders without a logo rather than with a fake one.
        return {"name": None, "logo": None, "colors": {"primary": None, "secondary": None}}
    return dict(brand)


def _player_bios(loader: Any) -> dict[str, dict[str, str | None]]:
    if not _have(loader, "players"):
        return {}
    cur = loader.cursor()
    rows = cur.execute("SELECT gsis_id, display_name, position FROM players").fetchall()
    return {gsis: {"display_name": name, "position": position} for gsis, name, position in rows}


def _ensure_pbp_derived(loader: Any, table: str) -> bool:
    """Build the six pbp-derived tables if this deployment has not yet, and
    report whether `table` is there afterwards."""
    derived.ensure(loader, PBP_DERIVED, table=table)
    return loader.table_exists(table)


# --- GET /api/seasons ----------------------------------------------------------


def season_index(*, loader: Any = None) -> dict[str, Any]:
    """Every season 1999 through the current one, newest first.

    Champion and top-scoring team both read straight off `team_standings`, which
    is itself a pure function of `games.csv` (SPEC 0.8: a season counts as
    complete only once its Super Bowl has been played, not merely "nothing left
    unplayed" — the 2022 Bills-Bengals cancellation would otherwise strand 2022 as
    permanently in progress).
    """
    loader = _loader(loader)
    from ..etl import standings as standings_etl

    standings_etl.ensure(loader)
    cur = loader.cursor()
    rows = cur.execute(
        "SELECT season, team, points_for, playoff_result, season_completed "
        "FROM team_standings ORDER BY season, team"
    ).fetchall()

    by_season: dict[int, list[tuple]] = {}
    for row in rows:
        by_season.setdefault(row[0], []).append(row)

    seasons_out: list[dict[str, Any]] = []
    for season in range(sources.FIRST_SEASON, latest_season() + 1):
        entries = by_season.get(season, [])
        completed = bool(entries) and all(e[4] for e in entries)
        champion = next((e[1] for e in entries if e[3] == "Won Super Bowl"), None)
        top = max(entries, key=lambda e: e[2], default=None)
        seasons_out.append({
            "season": season,
            "href": f"/seasons/{season}",
            "champion": champion,
            "champion_href": None if champion is None else f"/teams/{champion}/{season}",
            "top_scoring_team": None if top is None else top[1],
            "top_scoring_team_href": None if top is None else f"/teams/{top[1]}/{season}",
            "complete": completed,
        })
    seasons_out.sort(key=lambda s: s["season"], reverse=True)
    return {"seasons": seasons_out, "coverage_href": "/about/data"}


# --- playoff bracket -----------------------------------------------------------


def _bracket_team(
    code: str, season: int, seeds: dict[str, int | None], branding: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    brand = _brand_for(branding, code)
    return {
        "abbr": code,
        "code_in_season": alignment.code_in_season(code, season),
        "name": brand["name"],
        "logo": brand["logo"],
        "seed": seeds.get(code),
    }


def _bracket(
    loader: Any, season: int, seeds: dict[str, int | None], branding: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """A seeded tree, wild card through Super Bowl, or None when none was played.

    Rendered only when postseason games exist — never as an empty shell (SPEC 3,
    Season Hub). Team codes come straight off `games`, already canonicalised at
    load, so they key directly into `seeds` without another lookup.
    """
    if not _have(loader, "games"):
        return None
    cur = loader.cursor()
    rows = cur.execute(
        "SELECT game_id, game_type, home_team, away_team, home_score, away_score "
        "FROM games WHERE season = ? AND game_type IN ('WC','DIV','CON','SB') "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY game_type, game_id",
        [season],
    ).fetchall()
    if not rows:
        return None

    by_round: dict[str, list[dict[str, Any]]] = {}
    for game_id, game_type, home, away, home_score, away_score in rows:
        winner = None
        if home_score > away_score:
            winner = home
        elif away_score > home_score:
            winner = away
        by_round.setdefault(game_type, []).append({
            "game_id": game_id,
            "href": f"/games/{game_id}",
            "home": _bracket_team(home, season, seeds, branding),
            "away": _bracket_team(away, season, seeds, branding),
            "home_score": home_score,
            "away_score": away_score,
            "winner": winner,
        })
    rounds = [
        {"round": code, "round_label": ROUND_NAMES[code], "games": by_round[code]}
        for code in sorted(by_round, key=lambda c: ROUND_ORDER[c])
    ]
    return {"rounds": rounds}


# --- EPA quadrant ----------------------------------------------------------


def _epa_quadrant(
    loader: Any, season: int, branding: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Offence and defence EPA/play, one point per team, from `derived_game_team_stats`.

    Defence is the self-join SPEC 0.5 prescribes: `derived_game_team_stats` already
    carries both sides of every game as separate rows, so a team's allowed-side
    total is the *other* team's own offensive row in the same game, summed the
    same way (SUM/SUM, never an averaged rate — SPEC 0.7).
    """
    if not _ensure_pbp_derived(loader, "derived_game_team_stats"):
        return []
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT t.team,
               sum(t.epa_total) AS off_epa_total, sum(t.plays) AS off_plays,
               sum(o.epa_total) AS def_epa_total, sum(o.plays) AS def_plays
        FROM derived_game_team_stats t
        JOIN derived_game_team_stats o
          ON o.game_id = t.game_id AND o.team = t.opponent
        WHERE t.season = ?
        GROUP BY t.team
        """,
        [season],
    ).fetchall()
    out = []
    for team, off_total, off_plays, def_total, def_plays in rows:
        brand = _brand_for(branding, team)
        out.append({
            "team": team,
            "logo": brand["logo"],
            "off_epa": _round(None if not off_plays else off_total / off_plays),
            # Allowed EPA/play, not negated: a *lower* number here is a better
            # defence, same convention nflfastR itself uses.
            "def_epa": _round(None if not def_plays else def_total / def_plays),
            "href": f"/teams/{team}/{season}",
        })
    out.sort(key=lambda r: r["team"])
    return out


# --- league leaders --------------------------------------------------------


@dataclass(frozen=True)
class _LeaderCategory:
    id: str
    value_candidates: tuple[str, ...]
    support: tuple[tuple[str, tuple[str, ...], str], ...]


_LEADER_CATEGORIES: tuple[_LeaderCategory, ...] = (
    _LeaderCategory(
        "passing", ("passing_yards",),
        (("touchdowns", ("passing_tds",), "TD"), ("attempts", ("attempts",), "Att")),
    ),
    _LeaderCategory(
        "rushing", ("rushing_yards",),
        (("touchdowns", ("rushing_tds",), "TD"), ("carries", ("carries", "rushing_attempts"), "Att")),
    ),
    _LeaderCategory(
        "receiving", ("receiving_yards",),
        (("touchdowns", ("receiving_tds",), "TD"), ("receptions", ("receptions",), "Rec")),
    ),
    _LeaderCategory(
        "defense", ("def_sacks",),
        (("interceptions", ("def_interceptions",), "INT"), ("tackles", ("def_tackles_solo",), "Tkl")),
    ),
)


def _team_expr(columns: frozenset[str], team_col: str | None) -> str:
    if team_col is None:
        return "NULL"
    # `player_season_reg` has no `week` column in production — it is already a
    # season rollup — but the test fixture reuses the weekly generator, which
    # does carry one, so a multi-row player-season is resolved to the most
    # recent team on whichever shape actually loaded.
    if "week" in columns:
        return f'arg_max("{team_col}", week)'
    return f'any_value("{team_col}")'


def _counting_leaders(
    loader: Any,
    table: str,
    season: int,
    category: _LeaderCategory,
    bios: dict[str, dict[str, str | None]],
) -> list[dict[str, Any]] | None:
    columns = table_columns(loader, table)
    if not columns:
        return None
    value_col = first_present(columns, category.value_candidates)
    player_col = first_present(columns, ("player_id", "gsis_id"))
    if value_col is None or player_col is None:
        return None
    team_col = first_present(columns, ("team", "recent_team"))
    support = [
        (sid, first_present(columns, candidates), label)
        for sid, candidates, label in category.support
    ]
    support = [(sid, col, label) for sid, col, label in support if col]

    select = [f'sum(CAST("{value_col}" AS DOUBLE)) AS value']
    select.extend(f'sum(CAST("{col}" AS DOUBLE)) AS "{sid}"' for sid, col, _ in support)
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT "{player_col}" AS pid, {_team_expr(columns, team_col)} AS team,
               {', '.join(select)}
        FROM {table}
        WHERE season = ? AND "{player_col}" IS NOT NULL
        GROUP BY "{player_col}"
        HAVING sum(CAST("{value_col}" AS DOUBLE)) IS NOT NULL
        ORDER BY value DESC
        LIMIT ?
        """,
        [season, LEADER_ROWS],
    ).fetchall()
    return [
        _leader_row(rank, row, [sid for sid, _, _ in support], bios)
        for rank, row in enumerate(rows, start=1)
    ]


def _scoring_leaders(
    loader: Any, table: str, season: int, bios: dict[str, dict[str, str | None]]
) -> list[dict[str, Any]] | None:
    """Total touchdowns — not a published column, so this is ours, and the note says
    exactly which of the touchdown columns this deployment actually had to sum."""
    columns = table_columns(loader, table)
    td_cols = [c for c in _SCORING_TD_COLUMNS if c in columns]
    player_col = first_present(columns, ("player_id", "gsis_id"))
    if not td_cols or player_col is None:
        return None
    team_col = first_present(columns, ("team", "recent_team"))
    value_expr = " + ".join(f'COALESCE(CAST("{c}" AS DOUBLE), 0)' for c in td_cols)
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT "{player_col}" AS pid, {_team_expr(columns, team_col)} AS team,
               sum({value_expr}) AS value
        FROM {table}
        WHERE season = ? AND "{player_col}" IS NOT NULL
        GROUP BY "{player_col}"
        HAVING sum({value_expr}) > 0
        ORDER BY value DESC
        LIMIT ?
        """,
        [season, LEADER_ROWS],
    ).fetchall()
    leaders = [_leader_row(rank, row, [], bios) for rank, row in enumerate(rows, start=1)]
    for row in leaders:
        row["note"] = "Total touchdowns, computed by us as the sum of: " + ", ".join(td_cols)
        row["computed_by_us"] = True
    return leaders


def _leader_row(
    rank: int, row: Sequence[Any], support_ids: list[str], bios: dict[str, dict[str, str | None]]
) -> dict[str, Any]:
    pid, team, value, *support_values = row
    bio = bios.get(pid, {})
    return {
        "rank": rank,
        "gsis_id": pid,
        "href": f"/players/{pid}",
        "player": bio.get("display_name") or pid,
        "position": bio.get("position"),
        "team": team,
        "value": _num(value),
        "support": {sid: _num(v) for sid, v in zip(support_ids, support_values)},
    }


def _epa_leaders(
    loader: Any, season: int, bios: dict[str, dict[str, str | None]]
) -> list[dict[str, Any]] | None:
    """Total single-season EPA across every offensive role a player carried.

    A counting stat, deliberately: the qualified *rate* leader (EPA per play) needs
    a volume threshold, and that lives on the full leaderboard, not this snapshot
    (mirrors `repo/players.py::_league_leaders`'s reasoning exactly).
    """
    if not _ensure_pbp_derived(loader, "derived_player_game_epa"):
        return None
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT gsis_id, arg_max(team, week) AS team,
               sum(epa_total) AS value, sum(plays) AS plays
        FROM derived_player_game_epa
        WHERE season = ? AND gsis_id IS NOT NULL
        GROUP BY gsis_id
        HAVING sum(plays) > 0 AND sum(epa_total) IS NOT NULL
        ORDER BY value DESC
        LIMIT ?
        """,
        [season, LEADER_ROWS],
    ).fetchall()
    leaders = []
    for rank, (gsis_id, team, value, plays) in enumerate(rows, start=1):
        bio = bios.get(gsis_id, {})
        leaders.append({
            "rank": rank,
            "gsis_id": gsis_id,
            "href": f"/players/{gsis_id}",
            "player": bio.get("display_name") or gsis_id,
            "position": bio.get("position"),
            "team": team,
            "value": _num(value),
            "support": {"plays": plays, "epa_per_play": _round(value / plays)},
        })
    return leaders


def _leaders(loader: Any, season: int) -> dict[str, list[dict[str, Any]]]:
    bios = _player_bios(loader)
    result: dict[str, list[dict[str, Any]]] = {}
    if _have(loader, "player_season_reg"):
        table = sources.get("player_season_reg").table
        for category in _LEADER_CATEGORIES:
            rows = _counting_leaders(loader, table, season, category, bios)
            if rows:
                result[category.id] = rows
        scoring = _scoring_leaders(loader, table, season, bios)
        if scoring:
            result["scoring"] = scoring
    epa_rows = _epa_leaders(loader, season, bios)
    if epa_rows:
        result["epa"] = epa_rows
    return result


# --- GET /api/seasons/{season} --------------------------------------------


def season_hub(season: int, *, loader: Any = None) -> dict[str, Any]:
    """The season's story: standings, leaders, the EPA quadrant, the bracket."""
    _require_season(season)
    loader = _loader(loader)

    weeks: list[int] = []
    if _have(loader, "games"):
        cur = loader.cursor()
        weeks = [
            int(row[0]) for row in cur.execute(
                "SELECT DISTINCT week FROM games WHERE season = ? ORDER BY week", [season]
            ).fetchall()
        ]

    standings = standings_repo.season_standings(season, grouping="division", loader=loader)
    seeds = {
        team["team"]: team["seed"]
        for group in standings.get("groups", [])
        for team in group["teams"]
    }
    branding = _branding(loader)

    return {
        "season": season,
        "weeks": weeks,
        "standings": standings,
        "bracket": _bracket(loader, season, seeds, branding),
        "leaders": _leaders(loader, season),
        "epa_quadrant": _epa_quadrant(loader, season, branding),
        "draft_href": f"/draft/{season}",
    }


# --- GET /api/seasons/{season}/standings ------------------------------------


def full_standings(season: int, *, view: str = "division", loader: Any = None) -> dict[str, Any]:
    """Full standings with seeding. Thin: `repo/standings.py` does the work.

    `view` is this endpoint's own query-parameter spelling; the payload carries it
    back alongside `standings.py`'s native `grouping` key so neither name is a
    trap for whichever caller expects the other.
    """
    _require_season(season)
    if view not in ("division", "conference"):
        raise ValueError("view must be 'division' or 'conference'.")
    loader = _loader(loader)
    payload = standings_repo.season_standings(season, grouping=view, loader=loader)
    payload["view"] = view
    return payload


# --- GET /api/seasons/{season}/week/{week} ----------------------------------


def _game_columns(loader: Any) -> frozenset[str]:
    return table_columns(loader, "games")


def _wp_sparklines(
    loader: Any, season: int, game_ids: Sequence[str]
) -> dict[str, list[list[Any]]]:
    """One ~40-point win-probability curve per game, downsampled in SQL. Mirrors
    `repo/teams.py::_wp_sparklines`; kept local rather than imported because that
    one is private to its own package."""
    if not game_ids or not _ensure_pbp_derived(loader, "derived_wp_series"):
        return {}
    cur = loader.cursor()
    placeholders = ", ".join("?" * len(game_ids))
    rows = cur.execute(
        f"""
        WITH s AS (
          SELECT game_id, play_id, game_seconds_remaining, home_wp,
                 row_number() OVER (PARTITION BY game_id ORDER BY play_id) AS rn,
                 count(*) OVER (PARTITION BY game_id) AS n
          FROM derived_wp_series
          WHERE season = ? AND game_id IN ({placeholders}) AND home_wp IS NOT NULL
        )
        SELECT game_id, game_seconds_remaining, home_wp
        FROM s
        WHERE rn = 1 OR rn = n
           OR floor(rn * {WP_SPARKLINE_POINTS} / n) > floor((rn - 1) * {WP_SPARKLINE_POINTS} / n)
        ORDER BY game_id, play_id
        """,
        [season, *game_ids],
    ).fetchall()
    out: dict[str, list[list[Any]]] = {}
    for game_id, seconds, home_wp in rows:
        if home_wp is None:
            continue
        out.setdefault(game_id, []).append(
            [None if seconds is None else int(seconds), round(float(home_wp), 4)]
        )
    return out


def _biggest_swings(
    loader: Any, season: int, game_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """The largest win-probability swing stored for each game, read entirely from
    `derived_wp_series` and `derived_scoring_plays` — never the raw play log, so
    this carries none of `pbp_relation`'s `SeasonBusy` risk.

    This is our own measurement across the ~120 points per game the derived table
    keeps plus every scoring play, not certainly the single largest WPA swing
    nflfastR's own play-by-play would show for that game — the same caveat
    `repo/games.py`'s game-page swing carries, for the same reason.
    """
    if not game_ids or not _ensure_pbp_derived(loader, "derived_wp_series"):
        return {}
    cur = loader.cursor()
    placeholders = ", ".join("?" * len(game_ids))
    rows = cur.execute(
        f"""
        WITH s AS (
          SELECT game_id, play_id, home_wp,
                 lag(home_wp) OVER (PARTITION BY game_id ORDER BY play_id) AS prev_wp
          FROM derived_wp_series
          WHERE season = ? AND game_id IN ({placeholders}) AND home_wp IS NOT NULL
        ),
        d AS (
          SELECT game_id, play_id, home_wp - prev_wp AS delta
          FROM s WHERE prev_wp IS NOT NULL
        ),
        ranked AS (
          SELECT *, row_number() OVER (PARTITION BY game_id ORDER BY abs(delta) DESC) AS rn
          FROM d
        )
        SELECT r.game_id, r.delta, sp.description
        FROM ranked r
        LEFT JOIN derived_scoring_plays sp
          ON sp.game_id = r.game_id AND sp.play_id = r.play_id AND sp.season = ?
        WHERE r.rn = 1
        """,
        [season, *game_ids, season],
    ).fetchall()
    return {
        game_id: {"description": description, "wpa": _round(delta), "computed_by_us": True}
        for game_id, delta, description in rows
        if delta is not None
    }


_FANTASY_TERMS: tuple[tuple[tuple[str, ...], float], ...] = (
    (("passing_yards",), 1 / 25),
    (("passing_tds",), 4.0),
    (("passing_interceptions", "interceptions"), -2.0),
    (("rushing_yards",), 1 / 10),
    (("rushing_tds",), 6.0),
    (("receiving_yards",), 1 / 10),
    (("receiving_tds",), 6.0),
)

_FANTASY_NOTE = (
    "Standard (non-PPR) scoring, computed by us from raw counting stats: 1 point "
    "per 25 passing yards, 4 per passing touchdown, -2 per interception, 1 point "
    "per 10 rushing or receiving yards, 6 per rushing or receiving touchdown."
)


def _week_leaders(loader: Any, season: int, week: int) -> dict[str, list[dict[str, Any]]]:
    """Best single-game performances of the week, by EPA and by (our) fantasy points."""
    result: dict[str, list[dict[str, Any]]] = {}
    bios = _player_bios(loader)

    if _ensure_pbp_derived(loader, "derived_player_game_epa"):
        cur = loader.cursor()
        rows = cur.execute(
            """
            SELECT gsis_id, any_value(team) AS team,
                   sum(epa_total) AS value, sum(plays) AS plays
            FROM derived_player_game_epa
            WHERE season = ? AND week = ? AND gsis_id IS NOT NULL
            GROUP BY gsis_id
            HAVING sum(plays) > 0 AND sum(epa_total) IS NOT NULL
            ORDER BY value DESC
            LIMIT ?
            """,
            [season, week, LEADER_ROWS],
        ).fetchall()
        by_epa = []
        for rank, (gsis_id, team, value, plays) in enumerate(rows, start=1):
            bio = bios.get(gsis_id, {})
            by_epa.append({
                "rank": rank,
                "gsis_id": gsis_id,
                "href": f"/players/{gsis_id}",
                "player": bio.get("display_name") or gsis_id,
                "position": bio.get("position"),
                "team": team,
                "value": _num(value),
                "support": {"plays": plays, "epa_per_play": _round(value / plays)},
            })
        if by_epa:
            result["by_epa"] = by_epa

    if _have(loader, "player_week"):
        table = sources.get("player_week").table
        columns = table_columns(loader, table)
        player_col = first_present(columns, ("player_id", "gsis_id"))
        team_col = first_present(columns, ("team", "recent_team"))
        parts = []
        for candidates, weight in _FANTASY_TERMS:
            col = first_present(columns, candidates)
            if col:
                parts.append(f'COALESCE(CAST("{col}" AS DOUBLE), 0) * {weight}')
        if player_col and parts:
            value_expr = " + ".join(parts)
            cur = loader.cursor()
            rows = cur.execute(
                f"""
                SELECT "{player_col}" AS pid, {_team_expr(columns, team_col)} AS team,
                       sum({value_expr}) AS value
                FROM {table}
                WHERE season = ? AND week = ? AND "{player_col}" IS NOT NULL
                GROUP BY "{player_col}"
                ORDER BY value DESC
                LIMIT ?
                """,
                [season, week, LEADER_ROWS],
            ).fetchall()
            by_fantasy = []
            for rank, (pid, team, value) in enumerate(rows, start=1):
                bio = bios.get(pid, {})
                by_fantasy.append({
                    "rank": rank,
                    "gsis_id": pid,
                    "href": f"/players/{pid}",
                    "player": bio.get("display_name") or pid,
                    "position": bio.get("position"),
                    "team": team,
                    "value": _round(value, 2),
                    "support": {},
                    "note": _FANTASY_NOTE,
                    "computed_by_us": True,
                })
            if by_fantasy:
                result["by_fantasy"] = by_fantasy
    return result


def week_scoreboard(season: int, week: int, *, loader: Any = None) -> dict[str, Any]:
    """Every game of one week, with a result where the week has been played.

    Unplayed fixtures are returned, not filtered out — an in-progress or future
    week's slate renders with `played: false` and every score-dependent field
    `None` rather than an empty games list, which would read as a bye week for
    everyone (SPEC 3, Week Scoreboard: "honestly marked").
    """
    _require_season(season)
    loader = _loader(loader)
    if not _have(loader, "games"):
        return {
            "season": season, "week": week, "week_type": None, "week_label": f"Week {week}",
            "games": [], "bye_teams": [], "week_leaders": {},
            "note": "Games are not loaded in this deployment.",
        }
    columns = _game_columns(loader)
    optional = [c for c in ("overtime", "div_game", "spread_line") if c in columns]
    cur = loader.cursor()
    rows = cur.execute(
        f"""
        SELECT game_id, game_type, home_team, away_team, home_score, away_score
               {''.join(', "' + c + '"' for c in optional)}
        FROM games WHERE season = ? AND week = ? ORDER BY game_id
        """,
        [season, week],
    ).fetchall()
    if not rows:
        return {
            "season": season, "week": week, "week_type": None, "week_label": f"Week {week}",
            "games": [], "bye_teams": [], "week_leaders": {},
            "note": f"No games are scheduled for week {week} of the {season} season.",
        }

    branding = _branding(loader)
    played_ids = [row[0] for row in rows if row[4] is not None and row[5] is not None]
    sparklines = _wp_sparklines(loader, season, played_ids)
    swings = _biggest_swings(loader, season, played_ids)

    games: list[dict[str, Any]] = []
    playing: set[str] = set()
    week_type: str | None = None
    for row in rows:
        game_id, game_type, home, away, home_score, away_score = row[:6]
        extras = dict(zip(optional, row[6:]))
        playing.add(home)
        playing.add(away)
        week_type = week_type or game_type
        played = home_score is not None and away_score is not None
        spread = extras.get("spread_line")
        ats_result = None
        if played and spread is not None:
            margin = (home_score - away_score) + float(spread)
            ats_result = "push" if margin == 0 else ("home" if margin > 0 else "away")
        home_brand, away_brand = _brand_for(branding, home), _brand_for(branding, away)
        games.append({
            "game_id": game_id,
            "href": f"/games/{game_id}",
            "game_type": game_type,
            "played": played,
            "home": {"abbr": home, "name": home_brand["name"], "logo": home_brand["logo"]},
            "away": {"abbr": away, "name": away_brand["name"], "logo": away_brand["logo"]},
            "home_score": home_score,
            "away_score": away_score,
            "overtime": None if "overtime" not in extras else bool(extras["overtime"]),
            "div_game": None if "div_game" not in extras else bool(extras["div_game"]),
            "spread_line": _round(spread),
            "ats_result": ats_result,
            "wp_sparkline": sparklines.get(game_id),
            "biggest_play": swings.get(game_id),
        })

    bye_teams = sorted(set(alignment.teams_in_season(season)) - playing)
    return {
        "season": season,
        "week": week,
        "week_type": week_type,
        "week_label": f"Week {week}" if week_type == "REG" else ROUND_NAMES.get(week_type, f"Week {week}"),
        "games": games,
        "bye_teams": bye_teams,
        "week_leaders": _week_leaders(loader, season, week),
        "note": None,
    }
