"""The four questions the team cockpit asks: which teams, which franchise, which
season, which roster.

Four rules do most of the work here, and all four are about not lying.

**Structure comes from the alignment table, never from `teams_meta`.** The team
index groups a season into the divisions that season actually had — six in
1999-2001, eight from 2002 — and `teams_colors_logos.csv` carries present-day
membership only. So `teams_meta` is read for colours, logos and names and for
nothing else; grouping reads `etl/alignment.py`.

**The allowed side is ours, and says so.** `stats_team_reg`'s `def_*` columns are a
defence's own production — sacks, interceptions, passes defended — not what it gave
up (SPEC 0.5). Every allowed-side figure on this surface is a self-join of
`stats_team_week` over the opponents a club actually faced, points allowed comes
from `games.csv`, and every such column ships with `computed_by_us` set and the
method spelled out in the payload.

**Rates are computed at read time.** EPA per play is `SUM(epa_total) / SUM(plays)`,
snap share is `SUM(snaps) / SUM(team snaps)`, drives per game is a division. Nothing
here averages a stored rate (SPEC 0.7).

**A block with no data is absent.** Snap counts start in 2012 and injuries in 2009;
a 2001 roster does not carry an empty snap column, it carries no snap columns and a
note saying why. A source this deployment has not loaded yet takes its blocks with
it rather than rendering as zeros.

Historical codes resolve throughout: `/api/teams/STL` is the Rams, because every
loaded table is already keyed on the present-day franchise code. What a season's
rows are *keyed* on and what a season's page should *print* are different questions,
so a 2013 row reads "St. Louis Rams" via `alignment.label_in_season`.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from .. import sources
from ..config import latest_season
from ..deps import get_loader
from ..etl import alignment, derived, franchises
from ..etl.pbp_derive import DERIVED_NAME as PBP_DERIVED
from ..etl.standings import FORMULAS
from . import standings as standings_repo

logger = logging.getLogger(__name__)

#: Points kept in a schedule row's win-probability sparkline. The chart is a 40px
#: strip in a table cell; a 17-game schedule ships ~680 points instead of the
#: ~2,000 `derived_wp_series` holds for those games, and the sampler keeps the
#: first and last point so the curve still starts and ends where the game did.
WP_SPARKLINE_POINTS = 40

#: How many franchise leaders each board carries.
LEADER_ROWS = 10


class UnknownTeam(LookupError):
    """No franchise answers to this code, in any season we cover."""


class SeasonOutOfWindow(ValueError):
    """A season outside the window the registry declares."""


class SourceUnavailable(RuntimeError):
    """A source this page is built on has not been loaded into this deployment.

    Distinct from "there is no data for this team-season", which is answered with
    the block absent from the payload. This one means the file itself is missing,
    which is a deployment state and not an answer about football.
    """


# --- small shared helpers ----------------------------------------------------


def _loader(loader: Any) -> Any:
    return loader or get_loader()


def _columns(cur: Any, table: str) -> set[str]:
    return {row[0] for row in cur.execute(f"DESCRIBE {table}").fetchall()}


def _have(loader: Any, source_id: str) -> bool:
    """Is this source loaded? Never raises — an absent source removes a block.

    `Loader.ensure` raises for a single-grain file that 404s, and logs-and-skips
    for a season-grained one. Both mean the same thing to a page: we do not have
    it, so the block that needs it is not rendered rather than rendered empty.
    """
    table = sources.get(source_id).table
    if loader.table_exists(table):
        return True
    try:
        loader.ensure(source_id)
    except Exception:  # noqa: BLE001 - any download failure is "we don't have it"
        logger.warning(
            "Source %s is unavailable; blocks that need it are omitted", source_id,
            exc_info=True,
        )
        return False
    return loader.table_exists(table)


def _require_season(season: int) -> int:
    first, last = sources.FIRST_SEASON, latest_season()
    if not first <= season <= last:
        raise SeasonOutOfWindow(
            f"We hold seasons {first} through {last}; {season} is outside that window."
        )
    return season


def _all_franchises() -> frozenset[str]:
    """Every code that names a franchise in some season we cover.

    The union of the two eras, so Houston (2002 onward) is a franchise even though
    it is absent from 1999-2001, and no code is invented for a team that never was.
    """
    return frozenset(alignment.teams_in_season(sources.FIRST_SEASON)) | frozenset(
        alignment.teams_in_season(latest_season())
    )


def resolve_team(abbr: str) -> str:
    """Any historical spelling to the present-day franchise code. STL -> LA."""
    code = alignment.current_code(abbr)
    if code is None or code not in _all_franchises():
        raise UnknownTeam(f"No franchise answers to {abbr!r}.")
    return code


def _branding(loader: Any) -> dict[str, dict[str, Any]]:
    """Colours, logos and names, keyed by current franchise code.

    `team_conf` and `team_division` are deliberately not read: that file carries
    present-day membership only, and using it to group a historical season
    silently produces divisions that never existed (SPEC 0.1).
    """
    if not _have(loader, "teams_meta"):
        return {}
    cur = loader.cursor()
    rows = cur.execute(
        "SELECT team_abbr, team_name, team_nick, team_color, team_color2, "
        "team_logo_espn, team_logo_squared, team_wordmark FROM teams_meta"
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for abbr, name, nick, color, color2, logo_espn, logo_sq, wordmark in rows:
        code = alignment.current_code(abbr)
        if code is None:
            continue
        out[code] = {
            "name": name,
            "nick": nick,
            "logo": logo_sq or logo_espn,
            "logo_espn": logo_espn,
            "wordmark": wordmark,
            "colors": {"primary": color, "secondary": color2},
        }
    return out


def _brand_for(branding: Mapping[str, dict[str, Any]], code: str) -> dict[str, Any]:
    brand = branding.get(code)
    if brand is None:
        # A franchise the branding file does not carry keeps its identity — the
        # code is real — and renders without a logo rather than with a fake name.
        return {
            "name": None,
            "nick": None,
            "logo": None,
            "logo_espn": None,
            "wordmark": None,
            "colors": {"primary": None, "secondary": None},
        }
    return dict(brand)


def _rank_map(
    values: Mapping[str, float | None], *, high_is_first: bool
) -> tuple[dict[str, int | None], int]:
    """1-of-N rank per team, ties sharing a rank, plus the N.

    N is the number of clubs that actually have a value, not the size of the
    league: "6th of 32" when only eight clubs are loaded would be a rank against
    a field that is not there. On a complete season the two are the same number.
    """
    present = [v for v in values.values() if v is not None]
    ordered = sorted(set(present), reverse=high_is_first)
    position = {value: index + 1 for index, value in enumerate(ordered)}
    return (
        {
            team: (None if value is None else position[value])
            for team, value in values.items()
        },
        len(present),
    )


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    """SUM/SUM, or None. Never 0 for "we could not divide" (SPEC 0.7)."""
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _default_season(loader: Any) -> int:
    """The newest season whose Super Bowl has been played.

    The same definition `etl/standings.py` uses, and for the same reason: "no
    unplayed games remain" would leave 2022 permanently in progress, because the
    cancelled Bills-Bengals game was never played and never will be (SPEC 0.8).
    """
    if not _have(loader, "games"):
        return latest_season()
    cur = loader.cursor()
    row = cur.execute(
        "SELECT max(season) FROM games "
        "WHERE game_type = 'SB' AND home_score IS NOT NULL"
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else latest_season()


def _seasons_played(code: str) -> list[int]:
    """Seasons in our window in which this franchise was a member of the league."""
    return [
        season
        for season in range(sources.FIRST_SEASON, latest_season() + 1)
        if code in alignment.teams_in_season(season)
    ]


def _sum_by_team(
    cur: Any, sql: str, params: Sequence[Any]
) -> dict[str, dict[str, float | None]]:
    """(team -> {column: total}) from a query whose first column is the team."""
    result = cur.execute(sql, list(params))
    names = [d[0] for d in result.description]
    out: dict[str, dict[str, float | None]] = {}
    for row in result.fetchall():
        out[row[0]] = {name: row[i] for i, name in enumerate(names) if i > 0}
    return out


# --- GET /api/teams ----------------------------------------------------------


def team_index(season: int | None = None, *, loader: Any = None) -> dict[str, Any]:
    """One season's teams, grouped by that season's real divisions.

    Three division panels per conference in 1999-2001 and four from 2002, driven
    entirely by the alignment table — which is also why a 1999 index has 31 cards
    and not 32.
    """
    loader = _loader(loader)
    season = _default_season(loader) if season is None else season
    _require_season(season)

    branding = _branding(loader)
    standings = standings_repo.season_standings(season, grouping="league", loader=loader)
    by_team = {
        row["team"]: row
        for group in standings["groups"]
        for row in group["teams"]
    }

    conferences: list[dict[str, Any]] = []
    missing: list[str] = []
    total = 0
    for conference in ("AFC", "NFC"):
        divisions: list[dict[str, Any]] = []
        for division, members in alignment.alignment(season)[conference].items():
            cards = []
            for code in sorted(members):
                card = _team_card(code, season, branding, by_team.get(code))
                if card["record"] is None:
                    missing.append(code)
                cards.append(card)
                total += 1
            divisions.append(
                {
                    "division": division,
                    "label": f"{conference} {division}",
                    "teams": sorted(
                        cards,
                        key=lambda c: (
                            c["division_finish"] is None,
                            c["division_finish"] or 0,
                            c["abbr"],
                        ),
                    ),
                }
            )
        conferences.append({"conference": conference, "divisions": divisions})

    payload: dict[str, Any] = {
        "season": season,
        "teams": total,
        "divisions": len(alignment.divisions_in_season(season)),
        "season_completed": bool(standings.get("season_completed")),
        "window": {"first_season": sources.FIRST_SEASON, "last_season": latest_season()},
        "structure_note": (
            f"{total} clubs in {len(alignment.divisions_in_season(season))} divisions — "
            f"the {season} alignment, not today's."
        ),
        "conferences": conferences,
    }
    if missing:
        payload["note"] = (
            "No standings row was found for "
            + ", ".join(sorted(set(missing)))
            + "; those cards carry no record rather than a zero one."
        )
    return payload


def _team_card(
    code: str,
    season: int,
    branding: Mapping[str, dict[str, Any]],
    row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    brand = _brand_for(branding, code)
    return {
        "abbr": code,
        "code_in_season": alignment.code_in_season(code, season),
        "name": (
            None
            if brand["name"] is None
            else alignment.label_in_season(code, season, brand["name"])
        ),
        "nick": brand["nick"],
        "logo": brand["logo"],
        "logo_espn": brand["logo_espn"],
        "wordmark": brand["wordmark"],
        "colors": brand["colors"],
        "href": f"/teams/{code}/{season}",
        "franchise_href": f"/teams/{code}",
        "record": None
        if row is None
        else {
            "w": row["w"],
            "l": row["l"],
            "t": row["t"],
            "pct": _round(row["pct"], 4),
            "pf": row["pf"],
            "pa": row["pa"],
            "diff": row["diff"],
        },
        "division_finish": None if row is None else row["division_rank"],
        "won_division": None if row is None else row["won_division"],
        "made_playoffs": None if row is None else row["made_playoffs"],
        "playoff_result": None if row is None else row["playoff_result"],
        "seed": None if row is None else row["seed"],
    }


# --- GET /api/teams/{abbr} ---------------------------------------------------


def franchise(abbr: str, *, loader: Any = None) -> dict[str, Any]:
    """The franchise hub: summary, year by year, leaders, draft, coaches."""
    loader = _loader(loader)
    code = resolve_team(abbr)
    branding = _branding(loader)
    brand = _brand_for(branding, code)

    history = standings_repo.franchise_history(code, loader=loader)
    coaches_by_season, coach_records = _coaches(loader, code)

    seasons = []
    for row in history["seasons"]:
        season = row["season"]
        seasons.append(
            {
                "season": season,
                "href": f"/teams/{code}/{season}",
                "label": (
                    None
                    if brand["name"] is None
                    else alignment.label_in_season(code, season, brand["name"])
                ),
                "code_in_season": row["code_in_season"],
                "conference": row["conference"],
                "division": row["division"],
                "w": row["w"],
                "l": row["l"],
                "t": row["t"],
                "pct": _round(row["pct"], 4),
                "pf": row["pf"],
                "pa": row["pa"],
                "diff": row["diff"],
                "srs": _round(row["srs"], 3),
                "sos": _round(row["sos"], 3),
                "division_finish": row["division_rank"],
                "won_division": row["won_division"],
                "made_playoffs": row["made_playoffs"],
                "playoff_result": row["playoff_result"],
                "seed": row["seed"],
                "coach": coaches_by_season.get(season, {}).get("coach"),
                "coaches": coaches_by_season.get(season, {}).get("coaches", []),
            }
        )

    payload: dict[str, Any] = {
        "team": {
            "abbr": code,
            "aliases": history["aliases"],
            "name": brand["name"],
            "nick": brand["nick"],
            "logo": brand["logo"],
            "logo_espn": brand["logo_espn"],
            "wordmark": brand["wordmark"],
            "colors": brand["colors"],
            "href": f"/teams/{code}",
        },
        "era": {
            "seasons_from": sources.FIRST_SEASON,
            "draft_from": sources.DRAFT_FIRST_SEASON,
            "note": (
                f"Season records shown from {sources.FIRST_SEASON}. "
                f"Draft history from {sources.DRAFT_FIRST_SEASON}."
            ),
        },
        "summary": history["summary"],
        "seasons": seasons,
        "formulas": history["formulas"],
    }

    if coach_records:
        payload["coaches"] = coach_records
        payload["coaches_note"] = (
            "Head coach is the free-text name on each game in games.csv; a season "
            "with more than one names them all. There are no coach ids in the "
            "source, so nothing here is a coaching-career database."
        )

    leaders = _franchise_leaders(loader, code)
    if leaders:
        payload["leaders"] = leaders
        payload["leaders_note"] = (
            f"Since {sources.FIRST_SEASON} only — these are not franchise all-time "
            "records, and the seasons before our floor are not in this data."
        )

    draft = _draft_history(loader, code)
    if draft is not None:
        payload["draft"] = draft

    return payload


def _coaches(
    loader: Any, code: str
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Per-season head coach, and each coach's record with this franchise.

    Read from `games.csv`, which is the only place a coach's name appears. Played
    games only: a scheduled game names a coach but has not happened.
    """
    if not _have(loader, "games"):
        return {}, []
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT season, game_type, coach, won, tied FROM (
          SELECT season, game_type, home_coach AS coach,
                 CASE WHEN home_score > away_score THEN 1 ELSE 0 END AS won,
                 CASE WHEN home_score = away_score THEN 1 ELSE 0 END AS tied
          FROM games
          WHERE home_team = ? AND home_score IS NOT NULL AND away_score IS NOT NULL
          UNION ALL
          SELECT season, game_type, away_coach AS coach,
                 CASE WHEN away_score > home_score THEN 1 ELSE 0 END AS won,
                 CASE WHEN away_score = home_score THEN 1 ELSE 0 END AS tied
          FROM games
          WHERE away_team = ? AND home_score IS NOT NULL AND away_score IS NOT NULL
        ) WHERE coach IS NOT NULL
        ORDER BY season
        """,
        [code, code],
    ).fetchall()

    per_season: dict[int, dict[str, int]] = {}
    tallies: dict[str, dict[str, Any]] = {}
    for season, game_type, coach, won, tied in rows:
        regular = game_type == "REG"
        if regular:
            per_season.setdefault(season, {})
            per_season[season][coach] = per_season[season].get(coach, 0) + 1
        tally = tallies.setdefault(
            coach,
            {
                "coach": coach,
                "seasons": set(),
                "w": 0, "l": 0, "t": 0,
                "playoff_w": 0, "playoff_l": 0,
            },
        )
        tally["seasons"].add(season)
        if regular:
            if tied:
                tally["t"] += 1
            elif won:
                tally["w"] += 1
            else:
                tally["l"] += 1
        else:
            if won:
                tally["playoff_w"] += 1
            elif not tied:
                tally["playoff_l"] += 1

    season_coaches: dict[int, dict[str, Any]] = {}
    for season, counts in per_season.items():
        ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        season_coaches[season] = {
            # The coach of record is whoever coached the most games; an interim
            # takeover leaves both names on the row rather than silently one.
            "coach": ordered[0][0],
            "coaches": [name for name, _ in ordered],
        }

    records = []
    for tally in tallies.values():
        seasons = sorted(tally.pop("seasons"))
        tally["seasons"] = seasons
        tally["first_season"] = seasons[0]
        tally["last_season"] = seasons[-1]
        tally["seasons_count"] = len(seasons)
        records.append(tally)
    records.sort(key=lambda t: (-t["first_season"], t["coach"]))
    return season_coaches, records


#: Franchise-leader boards, by category. Only the columns a loaded
#: `stats_player_reg` actually carries are used; a category left with no columns
#: is dropped rather than shown with empty tables.
_LEADER_CATEGORIES: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("passing", (
        ("passing_yards", "Passing yards"),
        ("passing_tds", "Passing touchdowns"),
        ("completions", "Completions"),
        ("attempts", "Attempts"),
        ("passing_epa", "Passing EPA"),
    )),
    ("rushing", (
        ("rushing_yards", "Rushing yards"),
        ("rushing_tds", "Rushing touchdowns"),
        ("carries", "Carries"),
        ("rushing_epa", "Rushing EPA"),
    )),
    ("receiving", (
        ("receiving_yards", "Receiving yards"),
        ("receptions", "Receptions"),
        ("receiving_tds", "Receiving touchdowns"),
        ("targets", "Targets"),
        ("receiving_epa", "Receiving EPA"),
    )),
    ("defense", (
        ("def_sacks", "Sacks"),
        ("def_interceptions", "Interceptions"),
        ("def_tackles_solo", "Solo tackles"),
        ("def_tds", "Defensive touchdowns"),
    )),
    ("scoring", (
        ("fg_made", "Field goals made"),
        ("pat_made", "Extra points made"),
        ("special_teams_tds", "Special-teams touchdowns"),
    )),
)


def _franchise_leaders(loader: Any, code: str) -> dict[str, Any] | None:
    if not _have(loader, "player_season_reg"):
        return None
    cur = loader.cursor()
    available = _columns(cur, "player_season_reg")
    if "player_id" not in available or "team" not in available:
        return None
    regular = " AND season_type = 'REG'" if "season_type" in available else ""
    name_col = (
        "player_display_name" if "player_display_name" in available else "player_id"
    )

    categories: dict[str, Any] = {}
    for category, stats in _LEADER_CATEGORIES:
        boards = []
        for column, label in stats:
            if column not in available:
                continue
            career = cur.execute(
                f"""
                SELECT player_id, any_value({name_col}) AS name, sum("{column}") AS value,
                       min(season) AS first_season, max(season) AS last_season,
                       count(DISTINCT season) AS seasons
                FROM player_season_reg
                WHERE team = ? AND "{column}" IS NOT NULL{regular}
                GROUP BY player_id
                HAVING sum("{column}") IS NOT NULL
                ORDER BY value DESC, name
                LIMIT {LEADER_ROWS}
                """,
                [code],
            ).fetchall()
            single = cur.execute(
                f"""
                SELECT player_id, any_value({name_col}) AS name, season,
                       sum("{column}") AS value
                FROM player_season_reg
                WHERE team = ? AND "{column}" IS NOT NULL{regular}
                GROUP BY player_id, season
                HAVING sum("{column}") IS NOT NULL
                ORDER BY value DESC, name
                LIMIT {LEADER_ROWS}
                """,
                [code],
            ).fetchall()
            if not career and not single:
                continue
            boards.append(
                {
                    "stat": column,
                    "label": label,
                    "career": [
                        {
                            "rank": i + 1,
                            "gsis_id": pid,
                            "player": name,
                            "href": f"/players/{pid}",
                            "value": _round(value, 3),
                            "first_season": first,
                            "last_season": last,
                            "seasons": seasons,
                        }
                        for i, (pid, name, value, first, last, seasons)
                        in enumerate(career)
                    ],
                    "single_season": [
                        {
                            "rank": i + 1,
                            "gsis_id": pid,
                            "player": name,
                            "href": f"/players/{pid}",
                            "season": season,
                            "value": _round(value, 3),
                        }
                        for i, (pid, name, season, value) in enumerate(single)
                    ],
                }
            )
        if boards:
            categories[category] = boards
    if not categories:
        return None
    return {
        "since_1999": True,
        "first_season": sources.FIRST_SEASON,
        "categories": categories,
    }


def _draft_history(loader: Any, code: str) -> dict[str, Any] | None:
    """Every pick this franchise has made since the draft file's first season.

    Draft team codes are Pro-Football-Reference's, and three of them mean
    different franchises in different decades, so they resolve by (code, season)
    through `franchises.franchise_from_draft_code` — the one table on the site
    whose team codes are *not* already canonical.
    """
    if not _have(loader, "draft_picks"):
        return None
    cur = loader.cursor()
    available = _columns(cur, "draft_picks")
    if "team" not in available or "season" not in available:
        return None

    codes = [
        row[0]
        for row in cur.execute(
            "SELECT DISTINCT team FROM draft_picks WHERE team IS NOT NULL"
        ).fetchall()
    ]
    seasons = range(sources.DRAFT_FIRST_SEASON, latest_season() + 1)
    candidates = [
        raw
        for raw in codes
        if any(franchises.franchise_from_draft_code(raw, s) == code for s in seasons)
    ]
    if not candidates:
        return {
            "first_season": sources.DRAFT_FIRST_SEASON,
            "picks": [],
            "av_note": _AV_NOTE,
            "note": "No draft pick in the file resolves to this franchise.",
        }

    wanted = [
        c for c in (
            "season", "round", "pick", "team", "gsis_id", "pfr_player_name",
            "position", "college", "w_av", "dr_av", "seasons_started", "probowls",
            "allpro", "hof", "games", "to",
        )
        if c in available
    ]
    placeholders = ", ".join("?" * len(candidates))
    rows = cur.execute(
        f"SELECT {', '.join(chr(34) + c + chr(34) for c in wanted)} FROM draft_picks "
        f"WHERE team IN ({placeholders}) AND season >= ? "
        f"ORDER BY season DESC, pick",
        [*candidates, sources.DRAFT_FIRST_SEASON],
    ).fetchall()

    picks = []
    for row in rows:
        record = dict(zip(wanted, row))
        if franchises.franchise_from_draft_code(record["team"], record["season"]) != code:
            continue
        gsis_id = record.get("gsis_id")
        picks.append(
            {
                "season": record["season"],
                "round": record.get("round"),
                "pick": record.get("pick"),
                "player": record.get("pfr_player_name"),
                "gsis_id": gsis_id,
                "href": f"/players/{gsis_id}" if gsis_id else None,
                "class_href": f"/draft/{record['season']}",
                "position": record.get("position"),
                "college": record.get("college"),
                "w_av": record.get("w_av"),
                "dr_av": record.get("dr_av"),
                "seasons_started": record.get("seasons_started"),
                "probowls": record.get("probowls"),
                "allpro": record.get("allpro"),
                "hof": bool(record.get("hof")) if record.get("hof") is not None else None,
                "games": record.get("games"),
                "last_season": record.get("to"),
            }
        )
    return {
        "first_season": sources.DRAFT_FIRST_SEASON,
        "picks": picks,
        "av_note": _AV_NOTE,
    }


_AV_NOTE = (
    "w_av is Pro-Football-Reference's weighted career Approximate Value and dr_av "
    "the share earned with the drafting club; both exist for drafted players only. "
    "PFR's car_av column is empty in every row nflverse ships, so it is not shown."
)


# --- GET /api/teams/{abbr}/{season} ------------------------------------------


#: The standings columns a team-season page shows. Declared here rather than
#: passing the standings row through whole, so a column added to `team_standings`
#: for another page does not silently widen this endpoint's contract — and so the
#: response model can name every field it returns.
_RECORD_FIELDS: tuple[str, ...] = (
    "games", "w", "l", "t", "pct", "pf", "pa", "diff", "mov",
    "home", "away", "div", "conf", "streak",
    "division_rank", "won_division", "made_playoffs", "playoff_result",
    "playoff_wins", "playoff_losses", "seed", "seed_basis", "projected",
    "srs", "osrs", "dsrs", "sos", "pythagorean_wins",
)


def _season_record(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    record = {field: row.get(field) for field in _RECORD_FIELDS}
    record["ranks"] = dict(row.get("ranks") or {})
    return record


def team_season(abbr: str, season: int, *, loader: Any = None) -> dict[str, Any] | None:
    """The team-season cockpit. `None` when the club did not exist that season."""
    loader = _loader(loader)
    code = resolve_team(abbr)
    _require_season(season)
    if code not in alignment.teams_in_season(season):
        # Houston in 2001 is not an empty page; it is not a page.
        return None

    branding = _branding(loader)
    brand = _brand_for(branding, code)
    conference, division = alignment.division_of(code, season)
    # One standings read for the whole season: the club's own row carries its
    # ranks, and the rest of the league is what those ranks are against.
    standings = standings_repo.season_standings(season, grouping="league", loader=loader)
    standings_rows = {
        row["team"]: row for group in standings["groups"] for row in group["teams"]
    }
    record = standings_rows.get(code)
    coaches_by_season, _ = _coaches(loader, code)

    played = _seasons_played(code)

    label = (
        None
        if brand["name"] is None
        else alignment.label_in_season(code, season, brand["name"])
    )
    payload: dict[str, Any] = {
        "team": {
            "abbr": code,
            "code_in_season": alignment.code_in_season(code, season),
            "name": brand["name"],
            "nick": brand["nick"],
            "logo": brand["logo"],
            "logo_espn": brand["logo_espn"],
            "wordmark": brand["wordmark"],
            "colors": brand["colors"],
            "href": f"/teams/{code}",
        },
        "season": season,
        "label": None if label is None else f"{season} {label}",
        "conference": conference,
        "division": division,
        "division_label": f"{conference} {division}",
        "record": _season_record(record),
        "division_finish": None if record is None else record["division_rank"],
        "playoff_result": None if record is None else record["playoff_result"],
        "coach": coaches_by_season.get(season, {}).get("coach"),
        "coaches": coaches_by_season.get(season, {}).get("coaches", []),
        "prev_season": max((s for s in played if s < season), default=None),
        "next_season": min((s for s in played if s > season), default=None),
        "roster_href": f"/teams/{code}/{season}/roster",
        "season_completed": bool(standings.get("season_completed")),
        "formulas": standings["formulas"],
        "windows": {
            "stats_from": sources.FIRST_SEASON,
            "charting_from": sources.CHARTING_FIRST_SEASON,
            "snap_counts_from": sources.SNAP_COUNTS_FIRST_SEASON,
            "injuries_from": sources.INJURIES_FIRST_SEASON,
        },
        "allowed_side_method": _ALLOWED_METHOD,
    }

    game_stats = _game_team_stats(loader, season)
    ratings = _ratings(season, code, record, game_stats, standings_rows)
    if ratings:
        payload["ratings"] = ratings

    schedule = _schedule(loader, code, season, game_stats)
    if schedule:
        payload["schedule"] = schedule

    team_stats = _team_stats(loader, code, season, record, standings_rows)
    if team_stats:
        payload["team_stats"] = team_stats

    drive_profile = _drive_profile(loader, code, season)
    if drive_profile:
        payload["drive_profile"] = drive_profile

    drive_log = _drive_log(loader, code, season)
    if drive_log:
        payload["drive_log"] = drive_log

    leaders = _roster_leaders(loader, code, season)
    if leaders:
        payload["roster_leaders"] = leaders

    special = _special_teams(loader, code, season)
    if special:
        payload["special_teams"] = special

    injuries = _injury_summary(loader, code, season)
    if injuries:
        payload["injuries"] = injuries

    return payload


_ALLOWED_METHOD = (
    "Allowed-side figures are computed by us, not read: for each game this club "
    "played we take its opponent's own offensive row in stats_team_week and sum "
    "those. Points allowed comes from the final scores in games.csv. The def_* "
    "columns in the team stats file are a defence's own production — sacks, "
    "interceptions, tackles — and are never used as an allowed figure."
)

_EPA_METHOD = (
    "EPA per play is SUM(EPA) / SUM(plays) over the regular season from our "
    "per-game derived table, computed at read time; defensive EPA per play is the "
    "same sum over the plays this club's opponents ran against it."
)


def _game_team_stats(loader: Any, season: int) -> dict[str, dict[str, Any]] | None:
    """Per-game team production for one season, keyed by (game_id, team).

    Built from `derived_game_team_stats`, which is the play-derived table — this
    is the only place a play-level number reaches this surface, and it never
    scans plays at request time.
    """
    derived.ensure(loader, PBP_DERIVED, table="derived_game_team_stats")
    if not loader.table_exists("derived_game_team_stats"):
        return None
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT d.game_id, d.team, d.opponent, g.game_type,
               d.plays, d.yards, d.epa_total, d.successes, d.dropbacks,
               d.first_downs, d.turnovers, d.penalties, d.penalty_yards,
               d.top_seconds, d.drives
        FROM derived_game_team_stats d
        JOIN games g ON g.game_id = d.game_id
        WHERE d.season = ?
        """,
        [season],
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        (
            game_id, team, opponent, game_type, plays, yards, epa_total, successes,
            dropbacks, first_downs, turnovers, penalties, penalty_yards,
            top_seconds, drives,
        ) = row
        out[f"{game_id}|{team}"] = {
            "game_id": game_id,
            "team": team,
            "opponent": opponent,
            "game_type": game_type,
            "plays": plays,
            "yards": yards,
            "epa_total": epa_total,
            "successes": successes,
            "dropbacks": dropbacks,
            "first_downs": first_downs,
            "turnovers": turnovers,
            "penalties": penalties,
            "penalty_yards": penalty_yards,
            "top_seconds": top_seconds,
            "drives": drives,
        }
    return out or None


def _ratings(
    season: int,
    code: str,
    record: Mapping[str, Any] | None,
    game_stats: Mapping[str, dict[str, Any]] | None,
    standings_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rating tiles, each with its 1-of-N rank and the N it was ranked against.

    N is never hardcoded to 32: 1999-2001 had 31 clubs, and a tile ranks against
    the clubs that actually have the number, which on a complete season is the
    whole league.
    """
    league_size = len(alignment.teams_in_season(season))
    tiles: list[dict[str, Any]] = []

    if game_stats:
        offense: dict[str, float | None] = {}
        defense: dict[str, float | None] = {}
        off_totals: dict[str, list[float]] = {}
        def_totals: dict[str, list[float]] = {}
        for entry in game_stats.values():
            if entry["game_type"] != "REG":
                continue  # ratings are a regular-season statement, as PFR's are
            if entry["epa_total"] is None or not entry["plays"]:
                continue
            off_totals.setdefault(entry["team"], [0.0, 0.0])
            off_totals[entry["team"]][0] += float(entry["epa_total"])
            off_totals[entry["team"]][1] += float(entry["plays"])
            def_totals.setdefault(entry["opponent"], [0.0, 0.0])
            def_totals[entry["opponent"]][0] += float(entry["epa_total"])
            def_totals[entry["opponent"]][1] += float(entry["plays"])
        for team, (epa, plays) in off_totals.items():
            offense[team] = _ratio(epa, plays)
        for team, (epa, plays) in def_totals.items():
            defense[team] = _ratio(epa, plays)

        if code in offense:
            ranks, of = _rank_map(offense, high_is_first=True)
            tiles.append({
                "id": "offense_epa_per_play",
                "label": "Offense EPA/play",
                "value": _round(offense[code]),
                "rank": ranks[code],
                "of": of,
                "league_teams": league_size,
                "higher_is_better": True,
                "computed_by_us": True,
                "allowed_side": False,
                "formula": _EPA_METHOD,
            })
        if code in defense:
            ranks, of = _rank_map(defense, high_is_first=False)
            tiles.append({
                "id": "defense_epa_per_play",
                "label": "Defense EPA/play allowed",
                "value": _round(defense[code]),
                "rank": ranks[code],
                "of": of,
                "league_teams": league_size,
                "higher_is_better": False,
                "computed_by_us": True,
                "allowed_side": True,
                "formula": _EPA_METHOD + " " + _ALLOWED_METHOD,
            })

    if record is not None:
        ranks = record.get("ranks", {})
        for key, label, higher, digits, formula in (
            ("pf", "Points for", True, 0, _POINTS_FORMULA),
            ("pa", "Points against", False, 0, _POINTS_ALLOWED_FORMULA),
            ("diff", "Point differential", True, 0, FORMULAS.get("point_differential")),
            ("srs", "SRS", True, 3, FORMULAS.get("srs")),
            ("sos", "SOS", True, 3, FORMULAS.get("sos")),
            ("pythagorean_wins", "Pythagorean wins", True, 2,
             FORMULAS.get("pythagorean_wins")),
        ):
            if record.get(key) is None:
                continue
            of = sum(1 for row in standings_rows.values() if row.get(key) is not None)
            tiles.append({
                "id": key,
                "label": label,
                "value": _round(record[key], digits),
                "rank": ranks.get(key),
                "of": of,
                "league_teams": league_size,
                "higher_is_better": higher,
                # Points for and against are sums of final scores in games.csv;
                # SRS, SOS and Pythagorean wins are solved by us. Both are our
                # arithmetic rather than a published nflverse column, so both
                # carry the marker and the formula.
                "computed_by_us": True,
                "allowed_side": key == "pa",
                "formula": formula,
            })
    return tiles


_POINTS_FORMULA = "Sum of this club's final scores in games.csv, regular season."
_POINTS_ALLOWED_FORMULA = (
    "Sum of its opponents' final scores in games.csv, regular season — points "
    "allowed comes from the scoreboard, never from the team file's def_* columns."
)


def _schedule(
    loader: Any,
    code: str,
    season: int,
    game_stats: Mapping[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not _have(loader, "games"):
        return []
    cur = loader.cursor()
    available = _columns(cur, "games")
    optional = [
        c for c in ("gameday", "weekday", "gametime", "location", "roof", "surface", "div_game")
        if c in available
    ]
    rows = cur.execute(
        f"""
        SELECT game_id, game_type, week, home_team, away_team, home_score, away_score
               {''.join(', "' + c + '"' for c in optional)}
        FROM games
        WHERE season = ? AND (home_team = ? OR away_team = ?)
        ORDER BY week, game_id
        """,
        [season, code, code],
    ).fetchall()
    if not rows:
        return []

    sparklines = _wp_sparklines(loader, season, [r[0] for r in rows])
    wins = losses = ties = 0
    schedule: list[dict[str, Any]] = []
    for row in rows:
        game_id, game_type, week, home, away, home_score, away_score = row[:7]
        extras = dict(zip(optional, row[7:]))
        at_home = home == code
        opponent = away if at_home else home
        points_for = home_score if at_home else away_score
        points_against = away_score if at_home else home_score

        result: str | None = None
        if points_for is not None and points_against is not None:
            result = "W" if points_for > points_against else "L" if points_for < points_against else "T"
            if game_type == "REG":
                wins += result == "W"
                losses += result == "L"
                ties += result == "T"

        stats = (game_stats or {}).get(f"{game_id}|{code}")
        # The stored series is the *home* team's win probability. A schedule row
        # is read from this club's side, so an away row is mirrored — otherwise
        # half the sparklines on the page would be somebody else's game.
        home_curve = sparklines.get(game_id)
        curve = (
            None
            if home_curve is None
            else [
                [seconds, round(wp if at_home else 1.0 - wp, 4)]
                for seconds, wp in home_curve
            ]
        )
        schedule.append({
            "game_id": game_id,
            "game_href": f"/games/{game_id}",
            "game_type": game_type,
            "week": week,
            # gameday and gametime are typed by whatever the CSV reader inferred
            # (a DATE and a TIME here, plain strings in some builds), so they are
            # stringified once rather than leaking two shapes into the API.
            "gameday": None if extras.get("gameday") is None else str(extras["gameday"]),
            "weekday": extras.get("weekday"),
            "gametime": None if extras.get("gametime") is None else str(extras["gametime"]),
            "roof": extras.get("roof"),
            "surface": extras.get("surface"),
            "div_game": None if extras.get("div_game") is None else bool(extras["div_game"]),
            "home_away": "home" if at_home else "away",
            "opponent": opponent,
            "opponent_code_in_season": alignment.code_in_season(opponent, season),
            "opponent_href": f"/teams/{opponent}/{season}",
            "result": result,
            "points_for": points_for,
            "points_against": points_against,
            # Regular-season running record only. A postseason row carries no
            # running record rather than one that silently mixes the two.
            "running_record": (
                f"{wins}-{losses}-{ties}" if game_type == "REG" and result else None
            ),
            "plays": None if stats is None else stats["plays"],
            "yards": None if stats is None else stats["yards"],
            "turnovers": None if stats is None else stats["turnovers"],
            "first_downs": None if stats is None else stats["first_downs"],
            "epa_per_play": None
            if stats is None
            else _round(_ratio(stats["epa_total"], stats["plays"])),
            "success_rate": None
            if stats is None
            else _round(_ratio(stats["successes"], stats["plays"])),
            "wp_sparkline": curve,
            "wp_sparkline_points": None if curve is None else len(curve),
            "wp_sparkline_side": None if curve is None else code,
        })
    return schedule


def _wp_sparklines(
    loader: Any, season: int, game_ids: Sequence[str]
) -> dict[str, list[list[float]]]:
    """One ~40-point win-probability curve per game, downsampled in SQL.

    `floor(rn * T / n) > floor((rn - 1) * T / n)` steps up exactly T times across
    a game, so the sample is even rather than "every nth row", and the first and
    last plays are kept so the curve starts and ends where the game did. The
    stored series is ~120 points per game; shipping all of them for a 17-row
    schedule would be ~2,000 points nobody can see in a 40px strip.
    """
    if not game_ids:
        return {}
    derived.ensure(loader, PBP_DERIVED, table="derived_wp_series")
    if not loader.table_exists("derived_wp_series"):
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
           OR floor(rn * {WP_SPARKLINE_POINTS} / n)
              > floor((rn - 1) * {WP_SPARKLINE_POINTS} / n)
        ORDER BY game_id, play_id
        """,
        [season, *game_ids],
    ).fetchall()
    out: dict[str, list[list[float]]] = {}
    for game_id, seconds, home_wp in rows:
        if home_wp is None:
            continue
        out.setdefault(game_id, []).append(
            [None if seconds is None else int(seconds), round(float(home_wp), 4)]
        )
    return out


#: Team stats shown side by side with what the opponents did. Only the columns a
#: loaded `stats_team_reg` / `stats_team_week` actually carries appear; nothing
#: here is invented, and `def_*` columns are deliberately absent because they are
#: production, not allowance (SPEC 0.5).
_TEAM_STATS: tuple[tuple[str, str, bool], ...] = (
    ("passing_yards", "Passing yards", True),
    ("rushing_yards", "Rushing yards", True),
    ("passing_tds", "Passing touchdowns", True),
    ("rushing_tds", "Rushing touchdowns", True),
    ("passing_interceptions", "Interceptions thrown", False),
    ("sacks_suffered", "Sacks taken", False),
    ("passing_first_downs", "Passing first downs", True),
    ("rushing_first_downs", "Rushing first downs", True),
    ("receiving_first_downs", "Receiving first downs", True),
    ("passing_epa", "Passing EPA", True),
    ("rushing_epa", "Rushing EPA", True),
    ("receiving_epa", "Receiving EPA", True),
    ("passing_air_yards", "Passing air yards", True),
    ("passing_yards_after_catch", "Yards after catch", True),
)


def _team_stats(
    loader: Any,
    code: str,
    season: int,
    record: Mapping[str, Any] | None,
    standings_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Produced versus allowed, each with a 1-of-N rank for the season.

    The offence side is read from `stats_team_reg` — never summed from player box
    scores. The allowed side is the self-join described in `_ALLOWED_METHOD`, and
    every allowed cell carries `computed_by_us`.
    """
    if not _have(loader, "team_season") or not _have(loader, "team_week"):
        return None
    cur = loader.cursor()
    season_cols = _columns(cur, "team_season")
    week_cols = _columns(cur, "team_week")
    if "team" not in season_cols or "opponent_team" not in week_cols:
        return None

    stats = [
        (column, label, higher)
        for column, label, higher in _TEAM_STATS
        if column in season_cols and column in week_cols
    ]
    league_size = len(alignment.teams_in_season(season))

    rows: list[dict[str, Any]] = []
    if record is not None and record.get("pf") is not None:
        ranks = record.get("ranks", {})
        rows.append({
            "stat": "points",
            "label": "Points",
            "offense": record["pf"],
            "offense_rank": ranks.get("pf"),
            "allowed": record["pa"],
            "allowed_rank": ranks.get("pa"),
            "of": sum(1 for row in standings_rows.values() if row.get("pf") is not None),
            "higher_is_better": True,
            "offense_source": "games.csv final scores",
            "allowed_source": "games.csv final scores",
            "allowed_computed_by_us": True,
        })

    matched: int | None = None
    played: int | None = None
    if stats:
        regular_season = " AND season_type = 'REG'" if "season_type" in season_cols else ""
        offense_sql = (
            "SELECT team, "
            + ", ".join(f'sum("{c}") AS "{c}"' for c, _, _ in stats)
            + f" FROM team_season WHERE season = ?{regular_season} AND team IS NOT NULL"
            " GROUP BY team"
        )
        offense = _sum_by_team(cur, offense_sql, [season])

        regular_t = " AND t.season_type = 'REG'" if "season_type" in week_cols else ""
        regular_o = " AND o.season_type = 'REG'" if "season_type" in week_cols else ""
        regular_week = regular_t + regular_o
        allowed_sql = (
            "SELECT t.team AS team, "
            + ", ".join(f'sum(o."{c}") AS "{c}"' for c, _, _ in stats)
            + " FROM team_week t JOIN team_week o"
            "   ON o.season = t.season AND o.week = t.week"
            "  AND o.team = t.opponent_team AND o.opponent_team = t.team"
            f" WHERE t.season = ?{regular_week} GROUP BY t.team"
        )
        allowed = _sum_by_team(cur, allowed_sql, [season])

        # How many of this club's weekly rows actually found their opponent's
        # row. Reported rather than assumed: a null allowed column with no count
        # beside it looks like "they allowed nothing".
        played = cur.execute(
            "SELECT count(*) FROM team_week t WHERE t.season = ? AND t.team = ?"
            + regular_t,
            [season, code],
        ).fetchone()[0]
        matched = cur.execute(
            "SELECT count(*) FROM team_week t JOIN team_week o"
            "  ON o.season = t.season AND o.week = t.week"
            " AND o.team = t.opponent_team AND o.opponent_team = t.team"
            f" WHERE t.season = ? AND t.team = ?{regular_week}",
            [season, code],
        ).fetchone()[0]

        for column, label, higher in stats:
            offense_values = {t: v.get(column) for t, v in offense.items()}
            allowed_values = {t: v.get(column) for t, v in allowed.items()}
            if code not in offense_values and code not in allowed_values:
                continue
            offense_ranks, offense_of = _rank_map(offense_values, high_is_first=higher)
            # A stat that is good to produce is good to prevent, so the allowed
            # column ranks in the opposite direction.
            allowed_ranks, allowed_of = _rank_map(
                allowed_values, high_is_first=not higher
            )
            rows.append({
                "stat": column,
                "label": label,
                "offense": _round(offense_values.get(code), 3),
                "offense_rank": offense_ranks.get(code),
                "allowed": _round(allowed_values.get(code), 3),
                "allowed_rank": allowed_ranks.get(code),
                "of": max(offense_of, allowed_of),
                "higher_is_better": higher,
                "offense_source": "stats_team_reg",
                "allowed_source": "stats_team_week self-join over opponents",
                "allowed_computed_by_us": True,
            })

    if not rows:
        return None
    block: dict[str, Any] = {
        "rows": rows,
        "computed_by_us": ["allowed"],
        "method": _ALLOWED_METHOD,
        "league_teams": league_size,
    }
    if matched is not None:
        block["allowed_coverage"] = {
            "team_weeks": played,
            "opponent_rows_matched": matched,
            "complete": played == matched,
            "note": (
                "Every game this club played found its opponent's weekly row."
                if played == matched
                else f"{matched} of {played} weekly rows found the opponent's own "
                     "row, so the allowed column covers only those games."
            ),
        }
    return block


def _drive_profile(loader: Any, code: str, season: int) -> dict[str, Any] | None:
    derived.ensure(loader, PBP_DERIVED, table="derived_drives")
    if not loader.table_exists("derived_drives") or not loader.table_exists("games"):
        return None
    cur = loader.cursor()

    def side(column: str) -> dict[str, Any] | None:
        rows = cur.execute(
            f"""
            SELECT d.result, count(*) AS drives
            FROM derived_drives d
            JOIN games g ON g.game_id = d.game_id
            WHERE d.season = ? AND d.{column} = ? AND g.game_type = 'REG'
            GROUP BY d.result
            """,
            [season, code],
        ).fetchall()
        if not rows:
            return None
        drives = sum(r[1] for r in rows)
        game_row = cur.execute(
            f"""
            SELECT count(DISTINCT d.game_id), sum(d.plays), sum(d.top_seconds),
                   sum(d.start_yardline_100), count(d.start_yardline_100)
            FROM derived_drives d
            JOIN games g ON g.game_id = d.game_id
            WHERE d.season = ? AND d.{column} = ? AND g.game_type = 'REG'
            """,
            [season, code],
        ).fetchone()
        games, plays, top_seconds, start_total, start_count = game_row
        return {
            "drives": drives,
            "games": games,
            "drives_per_game": _round(_ratio(drives, games), 3),
            "plays_per_drive": _round(_ratio(plays, drives), 3),
            "seconds_per_drive": _round(_ratio(top_seconds, drives), 2),
            # Yards from the opponent's goal line, the nflfastR convention: a
            # drive starting on its own 25 reads 75.
            "avg_start_yardline_100": _round(_ratio(start_total, start_count), 2),
            "result_mix": {
                (result or "unknown"): count
                for result, count in sorted(rows, key=lambda r: (r[0] or ""))
            },
        }

    team = side("posteam")
    opponent = side("defteam")
    if team is None and opponent is None:
        return None
    profile: dict[str, Any] = {
        "computed_by_us": True,
        "method": (
            "Drives are aggregated from play-by-play into derived_drives; the "
            "opponent side is every drive run against this club in the games it "
            "played. Averages are SUM over SUM, never an average of per-game rates."
        ),
        "regular_season_only": True,
    }
    if team is not None:
        profile["team"] = team
    if opponent is not None:
        profile["opponent"] = opponent
        profile["opponent_computed_by_us"] = True
    return profile


def _drive_log(loader: Any, code: str, season: int) -> list[dict[str, Any]]:
    derived.ensure(loader, PBP_DERIVED, table="derived_drives")
    if not loader.table_exists("derived_drives"):
        return []
    cur = loader.cursor()
    rows = cur.execute(
        """
        SELECT game_id, week, drive, defteam, plays, time_of_possession,
               top_seconds, first_downs, result, scored,
               start_yard_line, end_yard_line, start_yardline_100, end_yardline_100
        FROM derived_drives
        WHERE season = ? AND posteam = ?
        ORDER BY week, game_id, drive
        """,
        [season, code],
    ).fetchall()
    return [
        {
            "game_id": game_id,
            "game_href": f"/games/{game_id}",
            "week": week,
            "drive": drive,
            "opponent": opponent,
            "plays": plays,
            "time_of_possession": top,
            "top_seconds": top_seconds,
            "first_downs": first_downs,
            "result": result,
            "scored": None if scored is None else bool(scored),
            "start_yard_line": start_text,
            "end_yard_line": end_text,
            "start_yardline_100": start_100,
            "end_yardline_100": end_100,
        }
        for (
            game_id, week, drive, opponent, plays, top, top_seconds, first_downs,
            result, scored, start_text, end_text, start_100, end_100,
        ) in rows
    ]


#: Headline stats a team-season page names a leader in. Availability-filtered, so
#: a narrower `stats_player_reg` simply produces a shorter list.
_HEADLINE_STATS: tuple[tuple[str, str], ...] = (
    ("passing_yards", "Passing yards"),
    ("rushing_yards", "Rushing yards"),
    ("receiving_yards", "Receiving yards"),
    ("passing_tds", "Passing touchdowns"),
    ("receptions", "Receptions"),
    ("def_sacks", "Sacks"),
    ("def_interceptions", "Interceptions"),
    ("def_tackles_solo", "Solo tackles"),
)


def _roster_leaders(loader: Any, code: str, season: int) -> dict[str, Any] | None:
    block: dict[str, Any] = {}

    if _have(loader, "player_season_reg"):
        cur = loader.cursor()
        available = _columns(cur, "player_season_reg")
        if "player_id" in available and "team" in available:
            regular = " AND season_type = 'REG'" if "season_type" in available else ""
            name_col = (
                "player_display_name"
                if "player_display_name" in available
                else "player_id"
            )
            by_stat = []
            for column, label in _HEADLINE_STATS:
                if column not in available:
                    continue
                # `> 0`, not `IS NOT NULL`: a club whose leading rusher gained
                # nothing has no leading rusher, and naming one would read as a
                # fact about him rather than about the stat.
                row = cur.execute(
                    f"""
                    SELECT player_id, any_value({name_col}) AS name,
                           any_value(position) AS position, sum("{column}") AS value
                    FROM player_season_reg
                    WHERE season = ? AND team = ? AND "{column}" IS NOT NULL{regular}
                    GROUP BY player_id
                    HAVING sum("{column}") > 0
                    ORDER BY value DESC, name
                    LIMIT 1
                    """,
                    [season, code],
                ).fetchone()
                if row is None:
                    continue
                pid, name, position, value = row
                by_stat.append({
                    "stat": column,
                    "label": label,
                    "gsis_id": pid,
                    "player": name,
                    "position": position,
                    "href": f"/players/{pid}",
                    "value": _round(value, 3),
                })
            if by_stat:
                block["by_stat"] = by_stat

    snaps = _snap_shares(loader, code, season)
    if snaps is None:
        block["snap_share_coverage"] = {
            "first_season": sources.SNAP_COUNTS_FIRST_SEASON,
            "available": False,
            "note": (
                f"Snap counts begin in {sources.SNAP_COUNTS_FIRST_SEASON}."
                if season < sources.SNAP_COUNTS_FIRST_SEASON
                else "Snap counts have not been loaded into this deployment."
            ),
        }
    else:
        ranked = [s for s in snaps.values() if s["offense_share"] is not None]
        ranked.sort(key=lambda s: s["offense_share"], reverse=True)
        if ranked:
            block["by_snap_share"] = ranked[:5]
            block["snap_share_coverage"] = {
                "first_season": sources.SNAP_COUNTS_FIRST_SEASON,
                "available": True,
                "note": _SNAP_METHOD,
            }
    return block or None


_SNAP_METHOD = (
    "Snap share is SUM(player snaps) / SUM(team snaps) across the games in the "
    "season, with a team's snaps in a game taken as the highest snap count any of "
    "its players recorded in it. Players are matched to snap counts through "
    "pfr_id, which resolves about 99.8% of rows; a player we cannot match carries "
    "no share rather than a zero one."
)


def _snap_shares(
    loader: Any, code: str, season: int
) -> dict[str, dict[str, Any]] | None:
    """Season snap totals and shares per `pfr_id`, or None if there are none.

    Returns totals as well as shares so the caller never has to average a rate:
    the share is one division of two sums (SPEC 0.7).
    """
    if season < sources.SNAP_COUNTS_FIRST_SEASON or not _have(loader, "snap_counts"):
        return None
    cur = loader.cursor()
    available = _columns(cur, "snap_counts")
    needed = {"season", "team", "game_id", "pfr_player_id"}
    if not needed <= available:
        return None
    sides = [
        (side, f"{side}_snaps")
        for side in ("offense", "defense", "st")
        if f"{side}_snaps" in available
    ]
    if not sides:
        return None

    # The team's snaps in a game, taken as the highest count any of its players
    # recorded — the lineman or quarterback who was out there for all of them.
    # `offense_pct` would be the alternative denominator, but a season share built
    # by averaging per-game percentages is exactly the mistake SPEC 0.7 forbids.
    totals = ", ".join(f'max("{col}") AS {side}_total' for side, col in sides)
    sums = ", ".join(
        f'sum(s."{col}") AS {side}_snaps, sum(t.{side}_total) AS {side}_team'
        for side, col in sides
    )
    player_expr = "any_value(s.player)" if "player" in available else "NULL"
    rows = cur.execute(
        f"""
        WITH s AS (
          SELECT * FROM snap_counts WHERE season = ? AND team = ?
        ),
        t AS (
          SELECT game_id, {totals} FROM s GROUP BY game_id
        )
        SELECT s.pfr_player_id, {player_expr} AS player,
               count(*) AS games, {sums}
        FROM s JOIN t USING (game_id)
        WHERE s.pfr_player_id IS NOT NULL
        GROUP BY s.pfr_player_id
        """,
        [season, code],
    )
    names = [d[0] for d in rows.description]
    out: dict[str, dict[str, Any]] = {}
    for row in rows.fetchall():
        record = dict(zip(names, row))
        entry: dict[str, Any] = {
            "pfr_id": record["pfr_player_id"],
            "player": record.get("player"),
            "games": record["games"],
        }
        for side, _ in sides:
            snaps = record.get(f"{side}_snaps")
            team_snaps = record.get(f"{side}_team")
            entry[f"{side}_snaps"] = snaps
            entry[f"{side}_share"] = _round(_ratio(snaps, team_snaps), 4)
        for side in ("offense", "defense", "st"):
            entry.setdefault(f"{side}_snaps", None)
            entry.setdefault(f"{side}_share", None)
        out[record["pfr_player_id"]] = entry
    return out or None


#: Special-teams columns `stats_team_reg` may carry. Field goals by distance are
#: deliberately not here: nothing we keep records a kick's distance, and a bucket
#: chart built from data that does not exist is worse than a stated gap.
_SPECIAL_TEAMS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fg_made", "Field goals made"),
    ("fg_att", "Field goals attempted"),
    ("fg_long", "Longest field goal"),
    ("fg_blocked", "Field goals blocked"),
    ("pat_made", "Extra points made"),
    ("pat_att", "Extra points attempted"),
    ("punts", "Punts"),
    ("punt_yards", "Punt yards"),
    ("punt_net_yards", "Net punt yards"),
    ("punt_blocked", "Punts blocked"),
    ("special_teams_tds", "Special-teams touchdowns"),
)


def _special_teams(loader: Any, code: str, season: int) -> dict[str, Any] | None:
    if not _have(loader, "team_season"):
        return None
    cur = loader.cursor()
    available = _columns(cur, "team_season")
    columns = [(c, label) for c, label in _SPECIAL_TEAMS_COLUMNS if c in available]
    if not columns:
        return None
    regular = " AND season_type = 'REG'" if "season_type" in available else ""
    row = cur.execute(
        "SELECT "
        + ", ".join(f'sum("{c}")' for c, _ in columns)
        + f" FROM team_season WHERE season = ? AND team = ?{regular}",
        [season, code],
    ).fetchone()
    if row is None or all(value is None for value in row):
        return None
    return {
        "rows": [
            {"stat": column, "label": label, "value": _round(value, 3)}
            for (column, label), value in zip(columns, row)
            if value is not None
        ],
        "not_available": [
            "Field goals by distance bucket — no kick distance is kept in any "
            "table we hold, so the bucket chart is not built rather than guessed.",
            "Return averages — no return dataset is loaded.",
        ],
    }


def _injury_summary(loader: Any, code: str, season: int) -> dict[str, Any] | None:
    coverage = {
        "first_season": sources.INJURIES_FIRST_SEASON,
        "available": False,
        "note": f"Injury reports begin in {sources.INJURIES_FIRST_SEASON}.",
    }
    if season < sources.INJURIES_FIRST_SEASON:
        return {"coverage": coverage}
    if not _have(loader, "injuries"):
        coverage["note"] = "Injury reports have not been loaded into this deployment."
        return {"coverage": coverage}

    cur = loader.cursor()
    available = _columns(cur, "injuries")
    if not {"season", "team", "week"} <= available:
        return {"coverage": coverage}
    name_col = (
        "full_name" if "full_name" in available
        else "player_name" if "player_name" in available
        else None
    )
    id_col = "gsis_id" if "gsis_id" in available else None
    status_col = "report_status" if "report_status" in available else None
    if name_col is None or status_col is None:
        return {"coverage": coverage}

    rows = cur.execute(
        f"""
        SELECT {id_col or "NULL"} AS gsis_id, {name_col} AS player,
               count(*) AS weeks_listed,
               count(*) FILTER (WHERE {status_col} = 'Out') AS weeks_out,
               count(*) FILTER (WHERE {status_col} = 'Doubtful') AS weeks_doubtful,
               count(*) FILTER (WHERE {status_col} = 'Questionable') AS weeks_questionable
        FROM injuries
        WHERE season = ? AND team = ? AND {status_col} IS NOT NULL
        GROUP BY 1, 2
        ORDER BY weeks_out DESC, weeks_listed DESC, player
        """,
        [season, code],
    ).fetchall()
    if not rows:
        return {"coverage": {**coverage, "available": True,
                             "note": "No player on this club drew a game-status "
                                     "designation this season."}}
    return {
        "coverage": {
            "first_season": sources.INJURIES_FIRST_SEASON,
            "available": True,
            "note": "Weekly game-status designations as reported, counted by week.",
        },
        "rows": [
            {
                "gsis_id": gsis_id,
                "player": player,
                "href": f"/players/{gsis_id}" if gsis_id else None,
                "weeks_listed": listed,
                "weeks_out": out,
                "weeks_doubtful": doubtful,
                "weeks_questionable": questionable,
            }
            for gsis_id, player, listed, out, doubtful, questionable in rows
        ],
    }


# --- GET /api/teams/{abbr}/{season}/roster -----------------------------------

_OFFENSE_POSITIONS = frozenset(
    {"QB", "RB", "FB", "HB", "WR", "TE", "T", "OT", "G", "OG", "C", "OL"}
)
_DEFENSE_POSITIONS = frozenset(
    {"DE", "DT", "NT", "DL", "EDGE", "LB", "ILB", "OLB", "MLB", "CB", "DB", "S", "FS", "SS"}
)
_SPECIAL_POSITIONS = frozenset({"K", "P", "LS", "PK", "KR", "PR"})

POSITION_GROUPS: tuple[str, ...] = ("offense", "defense", "special_teams", "all")


def _position_group(position: str | None) -> str | None:
    if not position:
        return None
    code = position.strip().upper()
    if code in _OFFENSE_POSITIONS:
        return "offense"
    if code in _DEFENSE_POSITIONS:
        return "defense"
    if code in _SPECIAL_POSITIONS:
        return "special_teams"
    return None


def team_roster(
    abbr: str,
    season: int,
    *,
    position_group: str | None = None,
    loader: Any = None,
) -> dict[str, Any]:
    """The roster, with snap shares where snap counts exist.

    Sorting is by offensive snap share. A player whose `pfr_id` does not match a
    snap-count row is not sorted as if he took zero snaps — he is excluded from
    the ranked block, keeps a null share and a note saying why, and appears after
    the ranked players in name order.
    """
    loader = _loader(loader)
    code = resolve_team(abbr)
    _require_season(season)
    if position_group not in (None, *POSITION_GROUPS):
        raise ValueError(
            f"Unknown position group {position_group!r}; "
            f"expected one of {', '.join(POSITION_GROUPS)}."
        )
    if not _have(loader, "rosters"):
        raise SourceUnavailable(
            "Roster data has not been loaded into this deployment yet."
        )

    cur = loader.cursor()
    available = _columns(cur, "rosters")
    wanted = [
        c for c in (
            "gsis_id", "pfr_id", "full_name", "position", "depth_chart_position",
            "jersey_number", "status", "birth_date", "height", "weight", "college",
            "years_exp", "entry_year", "draft_club", "draft_number", "headshot_url",
        )
        if c in available
    ]
    if "gsis_id" not in wanted:
        raise SourceUnavailable("The loaded roster file carries no player ids.")

    age_sql = (
        # Age at the season's kickoff, not today's age: a 2003 roster row should
        # not get older every year this page is loaded.
        f", date_diff('year', birth_date, DATE '{season}-09-01') AS age"
        if "birth_date" in available
        else ", NULL AS age"
    )
    rows = cur.execute(
        f"SELECT {', '.join(chr(34) + c + chr(34) for c in wanted)}{age_sql} "
        f"FROM rosters WHERE season = ? AND team = ?",
        [season, code],
    ).fetchall()

    snaps = _snap_shares(loader, code, season)
    stat_lines = _roster_stat_lines(loader, code, season)
    injuries = _roster_injury_status(loader, code, season)

    unmatched = 0
    entries: list[dict[str, Any]] = []
    for row in rows:
        record = dict(zip([*wanted, "age"], row))
        gsis_id = record.get("gsis_id")
        position = record.get("position")
        group = _position_group(position)
        entry: dict[str, Any] = {
            "gsis_id": gsis_id,
            "href": f"/players/{gsis_id}" if gsis_id else None,
            "number": record.get("jersey_number"),
            "name": record.get("full_name"),
            "position": position,
            "position_group": group,
            "depth_chart_position": record.get("depth_chart_position"),
            "status": record.get("status"),
            "age": record.get("age"),
            "age_computed_by_us": "birth_date" in available,
            "height": record.get("height"),
            "weight": record.get("weight"),
            "college": record.get("college"),
            "years_exp": record.get("years_exp"),
            "entry_year": record.get("entry_year"),
            "draft_club": record.get("draft_club"),
            "draft_number": record.get("draft_number"),
            "headshot_url": record.get("headshot_url"),
            "stat_line": stat_lines.get(gsis_id) if gsis_id else None,
            "injury_status": injuries.get(gsis_id) if gsis_id else None,
        }
        if snaps is not None:
            pfr_id = record.get("pfr_id")
            share = snaps.get(pfr_id) if pfr_id else None
            if share is None:
                unmatched += 1
                entry.update({
                    "snap_games": None,
                    "offense_snaps": None,
                    "offense_share": None,
                    "defense_snaps": None,
                    "defense_share": None,
                    "st_snaps": None,
                    "st_share": None,
                    "snap_note": (
                        "No snap-count row matched this player's pfr_id, so his "
                        "share is unknown — not zero."
                    ),
                })
            else:
                entry.update({
                    "snap_games": share["games"],
                    "offense_snaps": share["offense_snaps"],
                    "offense_share": share["offense_share"],
                    "defense_snaps": share["defense_snaps"],
                    "defense_share": share["defense_share"],
                    "st_snaps": share["st_snaps"],
                    "st_share": share["st_share"],
                    "snap_note": None,
                })
        entries.append(entry)

    counts = {
        group: sum(1 for e in entries if e["position_group"] == group)
        for group in ("offense", "defense", "special_teams")
    }
    counts["unclassified"] = sum(1 for e in entries if e["position_group"] is None)
    counts["all"] = len(entries)

    if position_group and position_group != "all":
        entries = [e for e in entries if e["position_group"] == position_group]

    if snaps is not None:
        # Ranked players first, in snap order; everyone else after, by name. The
        # unmatched are not sorted to the bottom as if they had played nothing —
        # they are simply not in the ranking.
        ranked = [e for e in entries if e.get("offense_share") is not None]
        rest = [e for e in entries if e.get("offense_share") is None]
        ranked.sort(key=lambda e: e["offense_share"], reverse=True)
        rest.sort(key=lambda e: (e["name"] or ""))
        entries = ranked + rest
        for index, entry in enumerate(ranked):
            entry["snap_rank"] = index + 1
    else:
        entries.sort(key=lambda e: (e["name"] or ""))

    coverage: dict[str, Any] = {
        "snaps_from": sources.SNAP_COUNTS_FIRST_SEASON,
        "snaps_available": snaps is not None,
        "injuries_from": sources.INJURIES_FIRST_SEASON,
        "injuries_available": bool(injuries),
    }
    if snaps is None:
        coverage["note"] = (
            f"Snap counts are available from {sources.SNAP_COUNTS_FIRST_SEASON}; "
            "the snap columns are absent from this payload rather than blank."
            if season < sources.SNAP_COUNTS_FIRST_SEASON
            else "Snap counts have not been loaded into this deployment, so the "
                 "snap columns are absent from this payload rather than blank."
        )
    else:
        coverage["note"] = _SNAP_METHOD

    branding = _branding(loader)
    brand = _brand_for(branding, code)
    label = (
        None
        if brand["name"] is None
        else alignment.label_in_season(code, season, brand["name"])
    )
    payload: dict[str, Any] = {
        "team": {
            "abbr": code,
            "code_in_season": alignment.code_in_season(code, season),
            "name": brand["name"],
            "logo": brand["logo"],
            "colors": brand["colors"],
            "href": f"/teams/{code}",
        },
        "season": season,
        "label": None if label is None else f"{season} {label}",
        "season_href": f"/teams/{code}/{season}",
        "position_group": position_group or "all",
        "position_groups": list(POSITION_GROUPS),
        "counts": counts,
        "coverage": coverage,
        "rows": entries,
    }
    if snaps is not None and unmatched:
        payload["unmatched_snap_players"] = unmatched
    return payload


def _roster_stat_lines(
    loader: Any, code: str, season: int
) -> dict[str, dict[str, Any]]:
    """That season's headline box line per player, keyed on gsis_id."""
    if not _have(loader, "player_season_reg"):
        return {}
    cur = loader.cursor()
    available = _columns(cur, "player_season_reg")
    if "player_id" not in available:
        return {}
    columns = [c for c, _ in _HEADLINE_STATS if c in available]
    if "games" in available:
        columns = ["games", *columns]
    if not columns:
        return {}
    regular = " AND season_type = 'REG'" if "season_type" in available else ""
    result = cur.execute(
        "SELECT player_id, "
        + ", ".join(f'sum("{c}") AS "{c}"' for c in columns)
        + f" FROM player_season_reg WHERE season = ? AND team = ?{regular} "
        "GROUP BY player_id",
        [season, code],
    )
    names = [d[0] for d in result.description]
    lines: dict[str, dict[str, Any]] = {}
    for row in result.fetchall():
        record = dict(zip(names, row))
        player_id = record.pop("player_id")
        line = {k: _round(v, 3) for k, v in record.items() if v is not None}
        if line:
            lines[player_id] = line
    return lines


def _roster_injury_status(loader: Any, code: str, season: int) -> dict[str, str]:
    """The latest week's game-status designation per player, where reported."""
    if season < sources.INJURIES_FIRST_SEASON or not _have(loader, "injuries"):
        return {}
    cur = loader.cursor()
    available = _columns(cur, "injuries")
    if not {"season", "team", "week", "gsis_id", "report_status"} <= available:
        return {}
    rows = cur.execute(
        """
        SELECT gsis_id, report_status FROM (
          SELECT gsis_id, report_status,
                 row_number() OVER (PARTITION BY gsis_id ORDER BY week DESC) AS rn
          FROM injuries
          WHERE season = ? AND team = ? AND gsis_id IS NOT NULL
            AND report_status IS NOT NULL
        ) WHERE rn = 1
        """,
        [season, code],
    ).fetchall()
    return {gsis_id: status for gsis_id, status in rows}
