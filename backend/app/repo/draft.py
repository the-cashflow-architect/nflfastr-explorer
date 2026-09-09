"""The draft index and one class board: `draft_picks` plus the `combine` join.

This is the one block on the site with history before the 1999 stat floor —
`draft_picks` starts in 1980 (`sources.DRAFT_FIRST_SEASON`), not at the first NFL
draft in 1936. An earlier draft of this product's spec said 1936; it was wrong, and
`sources.py` — not this file, not the prose in SPEC.md — is the number of record.

Two joins here have sharp edges, both documented at length in `sources.py` and
`etl/franchises.py`:

**The drafting team.** `draft_picks.team` is a Pro-Football-Reference code, a third
vocabulary next to the "current" codes every other table uses and the "period"
codes `games.csv` uses. Three PFR codes (`STL`, `HOU`, `BAL`) name a different
franchise depending on the season, so resolution is `franchise_from_draft_code(code,
season)`, which returns `None` for a genuinely ambiguous (code, season) pair — a
pick that renders as text, never a link to the wrong club.

**The combine.** Joined on `pfr_id` only, never on name + college + year: college
strings differ systematically between files, and the combine's own `season` is the
combine year, not necessarily the draft year for a player who declares late. About
83% of combine rows carry `pfr_id` (measured; see `sources.py`'s `combine`
`coverage_note`). A `pfr_id` that appears more than once in `combine` (17 of them,
measured) is an ambiguous match and is treated exactly like no match — this is why
`combine_match_confidence` only ever comes back `"exact"` or `None`: there is no
fuzzy tier to be `"probable"`, by design.

**Approximate Value.** `draft_picks.car_av` — PFR's career AV — is 100% NULL in
every row nflverse ships (SPEC 0.4). It is not in this module's payload at all;
showing a column that can never hold a value is worse than not having the column.
`w_av` (weighted career AV) and `dr_av` (AV earned with the drafting club) are the
real figures, and are absent for a pick with no NFL career, never coerced to 0.

**Best value by round.** Ranks each class's own `w_av` against the median `w_av`
for that *round*, computed from a cohort of classes at least five seasons old as of
`config.latest_season()` — a median across every class ever, recent ones included,
would be dragged down by players whose careers have barely started and rank every
recent pick a bust. The cohort's own boundary (which seasons went in) is returned
alongside the ranking so the page can print it, per SPEC 0.4.
"""

from __future__ import annotations

from typing import Any

from .. import sources
from ..config import latest_season
from ..deps import get_loader
from ..etl import alignment
from ..etl.franchises import franchise_from_draft_code

_COVERAGE_NOTE = (
    f"Draft results {sources.DRAFT_FIRST_SEASON}–present. Career outcome "
    f"columns (games, seasons started, Pro Bowls, All-Pros, Hall of Fame, "
    f"Approximate Value) reflect the player's full career as PFR recorded it, "
    f"not our {alignment.FIRST_SEASON} stat window."
)

_AV_NOTE = (
    "PFR's own career-total column (car_av) is empty for every drafted player in "
    "this data. w_av (weighted career AV) is the usable figure and is shown "
    "labelled 'Weighted career AV (PFR, drafted players only)'; dr_av is the same "
    "player's AV earned with the club that drafted him. Both are absent, not "
    "zero, for a pick with no recorded NFL career."
)

_COMBINE_NOTE = (
    "Combine measurables are matched to a pick by pfr_id only, never by name and "
    "college, because college spellings differ between files and a combine year "
    "is not always a player's draft year. A pfr_id combine can't resolve to "
    "exactly one row — no match, or more than one — renders blank rather than a "
    "guess, which is why combine_match_confidence is always \"exact\" or null; "
    "there is no fuzzy tier."
)

# Every column `draft_class` needs, read once per request rather than once per row.
_PICK_COLUMNS = """
    d.season, d.round, d.pick, d.team, d.gsis_id, d.pfr_player_id,
    d.pfr_player_name, d.hof, d.position, d.college, d.age, d."to", d.games,
    d.seasons_started, d.allpro, d.probowls, d.w_av, d.dr_av,
    cu.pfr_id IS NOT NULL AS combine_matched,
    cu.forty, cu.bench, cu.vertical, cu.broad_jump, cu.cone, cu.shuttle
"""

# Combine rows whose pfr_id is unique in the table — an id that appears twice
# (17 of them, measured) cannot be resolved to one player and is excluded here
# rather than joined to both draft rows that share the coincidence.
_PICK_JOIN = """
    FROM draft_picks d
    LEFT JOIN (
        SELECT pfr_id, forty, bench, vertical, broad_jump, cone, shuttle
        FROM combine
        WHERE pfr_id IN (
            SELECT pfr_id FROM combine WHERE pfr_id IS NOT NULL
            GROUP BY pfr_id HAVING count(*) = 1
        )
    ) cu ON cu.pfr_id = d.pfr_player_id
"""


def _player_href(gsis_id: str | None) -> str | None:
    return f"/players/{gsis_id}" if gsis_id else None


def _team_href(code: str | None) -> str | None:
    return f"/teams/{code}" if code else None


def _row_to_pick(row: tuple) -> dict[str, Any]:
    (
        season, round_, pick, pfr_team_code, gsis_id, pfr_player_id,
        player, hof, position, college, age, last_season_played, games,
        seasons_started, allpro, probowls, w_av, dr_av,
        combine_matched, forty, bench, vertical, broad_jump, cone, shuttle,
    ) = row
    team = franchise_from_draft_code(pfr_team_code, season)
    combine = None
    confidence = None
    if combine_matched:
        confidence = "exact"
        combine = {
            "forty": forty,
            "bench": bench,
            "vertical": vertical,
            "broad": broad_jump,
            "cone": cone,
            "shuttle": shuttle,
        }
    return {
        "round": round_,
        "pick": pick,
        "team": team,
        "team_href": _team_href(team),
        "pfr_team_code": pfr_team_code,
        "gsis_id": gsis_id,
        "pfr_player_id": pfr_player_id,
        "player": player,
        "player_href": _player_href(gsis_id),
        "position": position,
        "college": college,
        "age": age,
        "last_season_played": last_season_played,
        "games": games,
        "seasons_started": seasons_started,
        "allpro": allpro,
        "probowls": probowls,
        "hof": bool(hof),
        "w_av": w_av,
        "dr_av": dr_av,
        "combine": combine,
        "combine_match_confidence": confidence,
    }


def _fetch_class(loader: Any, year: int) -> list[dict[str, Any]]:
    loader.ensure("draft_picks")
    loader.ensure("combine")
    cur = loader.cursor()
    rows = cur.execute(
        f"SELECT {_PICK_COLUMNS} {_PICK_JOIN} WHERE d.season = ? ORDER BY d.pick",
        [year],
    ).fetchall()
    return [_row_to_pick(row) for row in rows]


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _summary(picks: list[dict[str, Any]]) -> dict[str, Any]:
    games = [p["games"] for p in picks if p["games"] is not None]
    return {
        "picks": len(picks),
        # A tile counts a *player*, not appearances: a five-time Pro Bowler is
        # one Pro Bowler on this tile, which is what draft_picks.probowls > 0
        # (already a per-player career count) answers.
        "pro_bowlers": sum(1 for p in picks if (p["probowls"] or 0) > 0),
        "all_pros": sum(1 for p in picks if (p["allpro"] or 0) > 0),
        "hof": sum(1 for p in picks if p["hof"]),
        # Median over picks with a known games count; a pick with none (never
        # made a roster, or a draft class not yet played) is excluded rather
        # than counted as a zero it was never confirmed to be.
        "median_games": _median(games),
    }


def _round_medians(cur: Any, cutoff: int) -> dict[int, float]:
    rows = cur.execute(
        'SELECT round, median(w_av) FROM draft_picks WHERE season <= ? AND w_av IS NOT NULL GROUP BY round',
        [cutoff],
    ).fetchall()
    return {round_: median for round_, median in rows}


def _best_value_by_round(loader: Any, picks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cutoff = latest_season() - 5
    medians = _round_medians(loader.cursor(), cutoff)
    best: dict[int, dict[str, Any]] = {}
    for pick in picks:
        if pick["w_av"] is None:
            continue
        median = medians.get(pick["round"])
        if median is None:
            continue
        delta = pick["w_av"] - median
        current = best.get(pick["round"])
        if current is None or delta > current["delta"]:
            best[pick["round"]] = {
                "round": pick["round"],
                "pick": pick["pick"],
                "gsis_id": pick["gsis_id"],
                "player": pick["player"],
                "player_href": pick["player_href"],
                "w_av": pick["w_av"],
                "slot_median_av": median,
                "delta": delta,
            }
    ordered = [best[r] for r in sorted(best)]
    cohort = {
        "first_season": sources.DRAFT_FIRST_SEASON,
        "last_season": cutoff,
        "as_of_season": latest_season(),
        "note": (
            f"Median w_av per round, over every class from {sources.DRAFT_FIRST_SEASON} "
            f"through {cutoff} — classes at least five seasons old as of the "
            f"{latest_season()} season. A younger class is still ranked against this "
            f"cohort, so a very recent pick's delta reflects an unfinished career, "
            f"not a final verdict."
        ),
    }
    return ordered, cohort


def draft_index(*, loader: Any = None) -> dict[str, Any]:
    """Every draft class on file, newest first, with its first overall pick."""
    loader = loader or get_loader()
    loader.ensure("draft_picks")
    cur = loader.cursor()
    counts = cur.execute(
        "SELECT season, count(*) FROM draft_picks WHERE season >= ? "
        "GROUP BY season ORDER BY season DESC",
        [sources.DRAFT_FIRST_SEASON],
    ).fetchall()
    firsts = {
        season: (player, gsis_id, code)
        for season, player, gsis_id, code in cur.execute(
            'SELECT season, pfr_player_name, gsis_id, team FROM draft_picks '
            "WHERE round = 1 AND pick = 1 AND season >= ?",
            [sources.DRAFT_FIRST_SEASON],
        ).fetchall()
    }

    years = []
    for season, picks in counts:
        entry: dict[str, Any] = {"year": season, "href": f"/draft/{season}", "picks": picks}
        first = firsts.get(season)
        if first is None:
            entry["first_overall"] = None
        else:
            player, gsis_id, code = first
            team = franchise_from_draft_code(code, season)
            entry["first_overall"] = {
                "player": player,
                "gsis_id": gsis_id,
                "player_href": _player_href(gsis_id),
                "team": team,
                "team_href": _team_href(team),
            }
        years.append(entry)

    return {
        "years": years,
        "first_season": sources.DRAFT_FIRST_SEASON,
        "coverage_note": _COVERAGE_NOTE,
    }


def draft_class(
    year: int, *, team: str | None = None, round: int | None = None, loader: Any = None
) -> dict[str, Any] | None:
    """One draft class: every pick, the class's own summary, and best value by round.

    `team` and `round` filter only the `picks` list — the summary tiles, the round
    list and the best-value block always describe the whole class, so a filtered
    table never quietly changes what the header tiles say. Returns `None` for a
    year with no picks on file at all, so the router can answer 404 rather than an
    empty class that looks like a real, winless draft.
    """
    loader = loader or get_loader()
    all_picks = _fetch_class(loader, year)
    if not all_picks:
        return None

    rounds = sorted({p["round"] for p in all_picks})
    team_filters = sorted(
        {(p["team"], p["team_href"]) for p in all_picks if p["team"]},
        key=lambda pair: pair[0],
    )

    picks = all_picks
    if team is not None:
        wanted = alignment.current_code(team) or team.strip().upper()
        picks = [p for p in picks if p["team"] == wanted]
    if round is not None:
        picks = [p for p in picks if p["round"] == round]

    best_value, cohort = _best_value_by_round(loader, all_picks)

    counts_cur = loader.cursor()
    prev_row = counts_cur.execute(
        "SELECT max(season) FROM draft_picks WHERE season < ? AND season >= ?",
        [year, sources.DRAFT_FIRST_SEASON],
    ).fetchone()
    next_row = counts_cur.execute(
        "SELECT min(season) FROM draft_picks WHERE season > ?", [year]
    ).fetchone()

    return {
        "year": year,
        "prev_year": prev_row[0] if prev_row else None,
        "next_year": next_row[0] if next_row else None,
        "rounds": rounds,
        "team_filters": [{"team": code, "team_href": href} for code, href in team_filters],
        "summary": _summary(all_picks),
        "picks": picks,
        "best_value": best_value,
        "best_value_cohort": cohort,
        "coverage_note": _COVERAGE_NOTE,
        "av_note": _AV_NOTE,
        "combine_note": _COMBINE_NOTE,
    }
