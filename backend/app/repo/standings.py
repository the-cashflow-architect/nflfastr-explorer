"""Reading `team_standings` back out, as plain dicts.

No FastAPI here, and no HTML: these functions answer questions about a season or a
franchise and hand back dictionaries a router can serialise, a script can print, or
a test can assert on.

Two things this layer is responsible for.

**Every rate is computed here.** The table stores wins, losses, ties, points and the
league-solved ratings — counts and totals. Win percentage, margin of victory and the
formatted `9-7-1` splits are divisions and joins done at read time, so nothing
downstream is ever tempted to average a stored rate across seasons.

**Every computed number arrives with its label.** Each payload carries the
`FORMULAS` entries for the columns it contains and, where a season is still running,
the `projected` flag and the tiebreaker note that go with them. The page cannot
accidentally present our arithmetic as nflverse's.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Sequence

from ..deps import get_loader
from ..etl import alignment, standings as standings_etl
from ..etl.standings import (
    DIVISION_TIEBREAK_RULES,
    FORMULAS,
    TABLE,
    TIEBREAK_LADDERS,
    WILD_CARD_TIEBREAK_RULES,
)

Grouping = Literal["division", "conference", "league"]

#: Columns read back for every row. Kept explicit so a column added to the ETL for
#: one page does not silently widen every payload on the site.
_SELECT = """
    season, team, conference, division, games, wins, losses, ties,
    points_for, points_against, point_differential,
    home_wins, home_losses, home_ties, away_wins, away_losses, away_ties,
    neutral_wins, neutral_losses, neutral_ties,
    division_wins, division_losses, division_ties,
    conference_wins, conference_losses, conference_ties,
    streak_kind, streak_length, longest_win_streak,
    division_rank, won_division, division_title_basis,
    playoff_seed, seed_basis, projected,
    tiebreak_note, tiebreak_ladder, made_playoffs, playoff_round, playoff_result,
    playoff_wins, playoff_losses, srs, osrs, dsrs, sos, pythagorean_wins,
    season_completed
"""

#: Ratings and totals a season page ranks teams on, and the direction that counts
#: as first. Ranks are a read-time computation for exactly the reason rates are:
#: a stored rank is wrong the moment the season it came from gains a week.
_RANKED: tuple[tuple[str, bool], ...] = (
    ("pf", True),
    ("pa", False),
    ("diff", True),
    ("pct", True),
    ("srs", True),
    ("osrs", True),
    ("dsrs", True),
    ("sos", True),
    ("pythagorean_wins", True),
)

_FORMULA_KEYS: tuple[str, ...] = (
    "win_pct", "mov", "srs", "sos", "osrs", "dsrs", "pythagorean_wins",
    "division_rank", "playoff_seed", "point_differential", "longest_win_streak",
    "home_away_split",
)


def tiebreak_rules() -> dict[str, list[str]]:
    """Both ladders, named. The league uses two procedures and so do we."""
    return {
        "division": list(DIVISION_TIEBREAK_RULES),
        "wild_card": list(WILD_CARD_TIEBREAK_RULES),
    }


def formulas() -> dict[str, str]:
    """The formula for every number on this surface that we compute ourselves."""
    return {key: FORMULAS[key] for key in _FORMULA_KEYS if key in FORMULAS}


def _win_pct(wins: int, losses: int, ties: int) -> float | None:
    games = wins + losses + ties
    return None if games == 0 else (wins + 0.5 * ties) / games


def _split(wins: int, losses: int, ties: int) -> str:
    # Ties are shown even at zero: "11-6-0" is how a standings table reads, and
    # dropping the third number makes 2016's two tied clubs look like everyone else.
    return f"{wins}-{losses}-{ties}"


def _neutral_note(wins: int, losses: int, ties: int) -> str | None:
    """Why home and away do not add up, on the rows where they do not."""
    games = wins + losses + ties
    if not games:
        return None
    played, counts = ("game", "counts") if games == 1 else ("games", "count")
    return (
        f"{games} {played} at a neutral site ({_split(wins, losses, ties)}) "
        f"{counts} towards neither the home nor the away split."
    )


def _row_to_dict(row: Sequence[Any]) -> dict[str, Any]:
    (
        season, team, conference, division, games, wins, losses, ties,
        points_for, points_against, point_differential,
        home_wins, home_losses, home_ties, away_wins, away_losses, away_ties,
        neutral_wins, neutral_losses, neutral_ties,
        division_wins, division_losses, division_ties,
        conference_wins, conference_losses, conference_ties,
        streak_kind, streak_length, longest_win_streak,
        division_rank, won_division, division_title_basis,
        playoff_seed, seed_basis, projected,
        tiebreak_note, tiebreak_ladder, made_playoffs, playoff_round, playoff_result,
        playoff_wins, playoff_losses, srs, osrs, dsrs, sos, pythagorean_wins,
        season_completed,
    ) = row
    return {
        "season": season,
        # `team` is the current franchise code, which is what every link keys on;
        # `code_in_season` is what the club actually played under, which is what a
        # 2013 page should print. `abbr` is the API's spelling of the same key.
        "team": team,
        "abbr": team,
        "code_in_season": alignment.code_in_season(team, season),
        "conference": conference,
        "division": division,
        "division_label": f"{conference} {division}",
        "games": games,
        "w": wins,
        "l": losses,
        "t": ties,
        "pct": _win_pct(wins, losses, ties),
        "pf": points_for,
        "pa": points_against,
        "diff": point_differential,
        "mov": None if not games else point_differential / games,
        "home": _split(home_wins, home_losses, home_ties),
        "away": _split(away_wins, away_losses, away_ties),
        "neutral": _split(neutral_wins, neutral_losses, neutral_ties),
        "neutral_games": neutral_wins + neutral_losses + neutral_ties,
        "neutral_note": _neutral_note(neutral_wins, neutral_losses, neutral_ties),
        "div": _split(division_wins, division_losses, division_ties),
        "conf": _split(conference_wins, conference_losses, conference_ties),
        "home_pct": _win_pct(home_wins, home_losses, home_ties),
        "away_pct": _win_pct(away_wins, away_losses, away_ties),
        "div_pct": _win_pct(division_wins, division_losses, division_ties),
        "conf_pct": _win_pct(conference_wins, conference_losses, conference_ties),
        "streak": None if not streak_kind else f"{streak_kind}{streak_length}",
        "streak_kind": streak_kind,
        "streak_length": streak_length,
        "longest_win_streak": longest_win_streak,
        "division_rank": division_rank,
        "won_division": bool(won_division),
        "division_title_basis": division_title_basis,
        "seed": playoff_seed,
        "seed_basis": seed_basis,
        "projected": bool(projected),
        "tiebreak_note": tiebreak_note,
        # Which of the league's two procedures produced the note above, and the
        # ladder itself, so a row that says "conference record" is not read as the
        # division rule of the same name.
        "tiebreak_ladder": tiebreak_ladder,
        "tiebreak_rules_applied": (
            None if tiebreak_ladder is None else list(TIEBREAK_LADDERS[tiebreak_ladder])
        ),
        "made_playoffs": bool(made_playoffs),
        "playoff_round": playoff_round,
        "playoff_result": playoff_result,
        "playoff_wins": playoff_wins,
        "playoff_losses": playoff_losses,
        "srs": srs,
        "osrs": osrs,
        "dsrs": dsrs,
        "sos": sos,
        "pythagorean_wins": pythagorean_wins,
        "season_completed": bool(season_completed),
    }


def _fetch(loader, where: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    loader = loader or get_loader()
    standings_etl.ensure(loader)
    cur = loader.cursor()
    rows = cur.execute(
        f"SELECT {_SELECT} FROM {TABLE} {where}", list(params)
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _add_ranks(rows: Iterable[dict[str, Any]]) -> None:
    """Rank each team against the rest of its league-season, ties sharing a rank."""
    rows = list(rows)
    for key, high_is_first in _RANKED:
        values = sorted(
            {row[key] for row in rows if row.get(key) is not None},
            reverse=high_is_first,
        )
        position = {value: index + 1 for index, value in enumerate(values)}
        for row in rows:
            row.setdefault("ranks", {})[key] = position.get(row.get(key))


def _order(rows: Sequence[dict[str, Any]], *, by_seed: bool) -> list[dict[str, Any]]:
    if by_seed:
        # Seeded clubs first in seed order, then everyone else by record. A club
        # with no seed is not "seed 99": it sorts after, but the field stays None.
        return sorted(
            rows,
            key=lambda r: (
                r["seed"] is None,
                r["seed"] or 0,
                -(r["pct"] or 0.0),
                -r["diff"],
                r["team"],
            ),
        )
    return sorted(rows, key=lambda r: (r["division_rank"], r["team"]))


def season_standings(
    season: int, *, grouping: Grouping = "division", loader: Any = None
) -> dict[str, Any]:
    """One season's standings, grouped the way the page asks for.

    `division` gives the eight (or, before 2002, six) division tables in AFC-then-NFC
    order; `conference` gives two tables ordered by playoff seed; `league` gives one.
    Divisions with no rows are dropped rather than rendered empty — that only happens
    on a partial database, and an empty table is a worse lie than a missing one.
    """
    if grouping not in ("division", "conference", "league"):
        raise ValueError(f"Unknown grouping {grouping!r}")
    rows = _fetch(loader, "WHERE season = ?", [season])
    if not rows:
        return {
            "season": season,
            "grouping": grouping,
            "groups": [],
            "projected": False,
            "season_completed": False,
            "playoff_seeds": alignment.playoff_seeds(season),
            "tiebreak_rules_implemented": tiebreak_rules(),
            "formulas": formulas(),
            "note": "No games have been played in this season yet.",
        }
    _add_ranks(rows)
    by_team = {row["team"]: row for row in rows}

    groups: list[dict[str, Any]] = []
    if grouping == "division":
        for conference, division in alignment.divisions_in_season(season):
            members = [
                row for row in rows
                if row["conference"] == conference and row["division"] == division
            ]
            if members:
                groups.append({
                    "label": f"{conference} {division}",
                    "conference": conference,
                    "division": division,
                    "teams": _order(members, by_seed=False),
                })
    elif grouping == "conference":
        for conference in ("AFC", "NFC"):
            members = [row for row in rows if row["conference"] == conference]
            if members:
                groups.append({
                    "label": conference,
                    "conference": conference,
                    "division": None,
                    "teams": _order(members, by_seed=True),
                })
    else:
        groups.append({
            "label": "NFL",
            "conference": None,
            "division": None,
            "teams": _order(rows, by_seed=True),
        })

    projected = any(row["projected"] for row in rows)
    completed = all(row["season_completed"] for row in rows)
    seeded = any(row["seed"] is not None for row in rows)
    return {
        "season": season,
        "grouping": grouping,
        "groups": groups,
        "teams": len(by_team),
        "projected": projected,
        "season_completed": completed,
        "playoff_seeds": alignment.playoff_seeds(season),
        "tiebreak_rules_implemented": tiebreak_rules(),
        "formulas": formulas(),
        "note": _notes(rows, completed=completed, projected=projected, seeded=seeded),
    }


def _notes(
    rows: Sequence[dict[str, Any]], *, completed: bool, projected: bool, seeded: bool
) -> str:
    """The page's standing caveats: where the seeds came from, and what is missing
    from the home and away columns."""
    note = _seeding_note(completed, projected, seeded)
    neutral = sum(row["neutral_games"] for row in rows)
    if neutral:
        # Halved because a neutral-site game is one game and two rows.
        games = neutral // 2
        played, counts = ("game was", "counts") if games == 1 else ("games were", "count")
        note += (
            f" {games} {played} played at a neutral site and {counts} towards "
            "neither the home nor the away split, so those two columns do not add "
            "up to the season."
        )
    return note


def _seeding_note(completed: bool, projected: bool, seeded: bool) -> str:
    if projected:
        return (
            "This season is still being played. Seeds are projected: each division "
            "is ordered by win percentage, then head-to-head, division record, "
            "common games and conference record, and the winners and wild-card "
            "contenders by the conference ladder — one club per division at a time, "
            "then head-to-head sweep, conference record, common games and strength "
            "of victory. Ties our implemented rules cannot break are marked and "
            "left in alphabetical order."
        )
    if completed and seeded:
        return (
            "Seeds are read off the postseason bracket — who hosted whom in which "
            "round — not recomputed from tiebreakers."
        )
    if completed:
        return (
            "The postseason games on file do not describe a full bracket, so no "
            "seeds are shown for this season."
        )
    return "No postseason games have been played, so no seeds are shown."


def team_season_record(team: str, season: int, *, loader: Any = None) -> dict[str, Any] | None:
    """One club's season, with its rank in the league for every ranked column.

    Accepts any historical spelling of the code — a request for STL in 2013 and one
    for LA in 2013 are the same team-season, because the table is keyed on the
    franchise's present-day code.
    """
    code = alignment.current_code(team)
    if code is None:
        return None
    season_rows = _fetch(loader, "WHERE season = ?", [season])
    if not season_rows:
        return None
    _add_ranks(season_rows)
    for row in season_rows:
        if row["team"] == code:
            row["formulas"] = formulas()
            row["tiebreak_rules_implemented"] = tiebreak_rules()
            return row
    return None


def franchise_history(team: str, *, loader: Any = None) -> dict[str, Any]:
    """Every season one franchise has played in our window, newest first.

    Rows are stitched across relocations because the loader has already rewritten
    every historical code to the current one: the 2015 St. Louis season and the 2016
    Los Angeles season are the same franchise, and each row still carries the code
    and the name the club played under at the time.
    """
    code = alignment.current_code(team)
    if code is None:
        raise ValueError(f"Unknown team {team!r}")
    rows = _fetch(loader, "WHERE team = ? ORDER BY season DESC", [code])

    played = sum(row["games"] for row in rows)
    wins = sum(row["w"] for row in rows)
    losses = sum(row["l"] for row in rows)
    ties = sum(row["t"] for row in rows)
    playoff_seasons = [row for row in rows if row["made_playoffs"]]
    best = max(rows, key=lambda r: r["diff"], default=None)
    worst = min(rows, key=lambda r: r["diff"], default=None)
    return {
        "team": code,
        "abbr": code,
        "aliases": list(alignment.alias_group(code)),
        "first_season": alignment.FIRST_SEASON,
        "seasons": rows,
        "summary": {
            "seasons": len(rows),
            "games": played,
            "w": wins,
            "l": losses,
            "t": ties,
            "pct": _win_pct(wins, losses, ties),
            "points_for": sum(row["pf"] for row in rows),
            "points_against": sum(row["pa"] for row in rows),
            "playoff_appearances": len(playoff_seasons),
            "division_titles": sum(1 for row in rows if row["won_division"]),
            "postseason_w": sum(row["playoff_wins"] for row in rows),
            "postseason_l": sum(row["playoff_losses"] for row in rows),
            "super_bowls": sum(
                1 for row in rows if row["playoff_result"] == "Won Super Bowl"
            ),
            "best_season": None if best is None else best["season"],
            "worst_season": None if worst is None else worst["season"],
        },
        "formulas": formulas(),
    }


def league_ratings(season: int, *, loader: Any = None) -> dict[str, Any]:
    """Every club's ratings for one season, strongest first.

    This is the ratings view rather than the standings view: the same rows, ordered
    by SRS and carrying only what a rating table shows, so the caller does not have
    to know which of these numbers we read and which we solved for. All of them we
    solved for.
    """
    rows = _fetch(loader, "WHERE season = ?", [season])
    if not rows:
        return {
            "season": season,
            "teams": [],
            "formulas": formulas(),
            "note": "No games have been played in this season yet.",
        }
    _add_ranks(rows)
    ordered = sorted(rows, key=lambda r: (r["srs"] is None, -(r["srs"] or 0.0), r["team"]))
    teams = [
        {
            "team": row["team"],
            "abbr": row["team"],
            "code_in_season": row["code_in_season"],
            "season": row["season"],
            "conference": row["conference"],
            "division": row["division"],
            "games": row["games"],
            "w": row["w"],
            "l": row["l"],
            "t": row["t"],
            "pct": row["pct"],
            "pf": row["pf"],
            "pa": row["pa"],
            "diff": row["diff"],
            "mov": row["mov"],
            "srs": row["srs"],
            "osrs": row["osrs"],
            "dsrs": row["dsrs"],
            "sos": row["sos"],
            "pythagorean_wins": row["pythagorean_wins"],
            "pythagorean_delta": (
                None
                if row["pythagorean_wins"] is None
                else row["w"] + 0.5 * row["t"] - row["pythagorean_wins"]
            ),
            "ranks": row["ranks"],
        }
        for row in ordered
    ]
    return {
        "season": season,
        "teams": teams,
        "computed_by_us": [
            "srs", "osrs", "dsrs", "sos", "mov", "pythagorean_wins",
        ],
        "formulas": formulas(),
        "note": (
            "Every column here is our own calculation from final scores, not a "
            "figure published by nflverse."
        ),
    }
