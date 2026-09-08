"""League structure, season by season.

The NFL our data covers is not one league — it is three. Between 1999 and 2001 it
had 31 teams in six divisions and sent six teams per conference to the playoffs.
Houston arrived in 2002 with the realignment to eight divisions, which also moved
Seattle from the AFC West to the NFC West and Arizona from the NFC East to the NFC
West. A seventh playoff seed per conference arrived in 2020.

`teams_colors_logos.csv` — the only machine-readable division source nflverse
publishes — carries *current* division only. Using it to group a 2001 season silently
produces standings that never existed. So membership is authored here, by season, and
every standings surface reads it rather than the CSV.

Three-letter codes follow the source files: a franchise's code changes when it moves
(STL -> LA in 2016, SD -> LAC in 2017, OAK -> LV in 2020), so a code identifies a
team *in a season*, and `current_code()` maps it forward to the franchise page.
"""

from __future__ import annotations

from functools import lru_cache

# The first season nflverse publishes play-level data for. Our floor everywhere
# except the draft, which reaches back to 1936.
FIRST_SEASON = 1999

# Eras of league structure. Each entry is (first_season, last_season_or_None,
# {conference: {division: (team codes...)}}).
_ERAS: list[tuple[int, int | None, dict[str, dict[str, tuple[str, ...]]]]] = [
    (
        1999,
        2001,
        {
            "AFC": {
                "East": ("BUF", "IND", "MIA", "NE", "NYJ"),
                "Central": ("BAL", "CIN", "CLE", "JAX", "PIT", "TEN"),
                "West": ("DEN", "KC", "OAK", "SD", "SEA"),
            },
            "NFC": {
                "East": ("ARI", "DAL", "NYG", "PHI", "WAS"),
                "Central": ("CHI", "DET", "GB", "MIN", "TB"),
                "West": ("ATL", "CAR", "NO", "SF", "STL"),
            },
        },
    ),
    (
        2002,
        None,
        {
            "AFC": {
                "East": ("BUF", "MIA", "NE", "NYJ"),
                "North": ("BAL", "CIN", "CLE", "PIT"),
                "South": ("HOU", "IND", "JAX", "TEN"),
                "West": ("DEN", "KC", "OAK", "SD"),
            },
            "NFC": {
                "East": ("DAL", "NYG", "PHI", "WAS"),
                "North": ("CHI", "DET", "GB", "MIN"),
                "South": ("ATL", "CAR", "NO", "TB"),
                "West": ("ARI", "SEA", "SF", "STL"),
            },
        },
    ),
]

# Relocations, as (old code, new code, first season the new code is used). The source
# files switch code the year the team plays under the new name, so these dates are
# what `games.csv` actually contains, not what the announcement said.
_RELOCATIONS: tuple[tuple[str, str, int], ...] = (
    ("STL", "LA", 2016),
    ("SD", "LAC", 2017),
    ("OAK", "LV", 2020),
)

# Every code that has ever meant this franchise, newest first. Used to stitch a
# franchise's history together across a move.
FRANCHISE_ALIASES: dict[str, tuple[str, ...]] = {
    "LA": ("LA", "LAR", "STL"),
    "LAC": ("LAC", "SD"),
    "LV": ("LV", "OAK"),
}

# nflverse files are not perfectly consistent: play-by-play uses LAR where games.csv
# uses LA. Normalise on read.
_SPELLING_FIXES = {"LAR": "LA"}

_ALIAS_TO_CURRENT: dict[str, str] = {
    alias: current for current, aliases in FRANCHISE_ALIASES.items() for alias in aliases
}

# Seasons in which each conference sent this many teams to the playoffs.
_PLAYOFF_SEEDS: tuple[tuple[int, int | None, int], ...] = (
    (1999, 2019, 6),
    (2020, None, 7),
)

# The regular season grew from 16 games to 17 in 2021, which moves the last week
# number and therefore every "latest week" calculation.
_REGULAR_SEASON_WEEKS: tuple[tuple[int, int | None, int], ...] = (
    (1999, 2020, 17),
    (2021, None, 18),
)


def _era_for(season: int) -> dict[str, dict[str, tuple[str, ...]]]:
    for start, end, alignment in _ERAS:
        if season >= start and (end is None or season <= end):
            return alignment
    raise ValueError(f"No alignment defined for season {season}")


def normalize_code(code: str | None) -> str | None:
    """Fix a spelling variant without moving the team through a relocation."""
    if not code:
        return None
    code = code.strip().upper()
    return _SPELLING_FIXES.get(code, code)


def current_code(code: str | None) -> str | None:
    """Map any historical code to the franchise's code today (STL -> LA)."""
    code = normalize_code(code)
    if code is None:
        return None
    return _ALIAS_TO_CURRENT.get(code, code)


def code_in_season(code: str, season: int) -> str:
    """Map a franchise to the code it actually played under in `season`.

    The inverse of `current_code`: a link to the Rams' 2013 season has to ask for
    STL, because that is the only code that season's rows carry.
    """
    code = current_code(code) or code
    for old, new, first_season in _RELOCATIONS:
        if code == new and season < first_season:
            return old
    return code


@lru_cache(maxsize=None)
def alignment(season: int) -> dict[str, dict[str, tuple[str, ...]]]:
    """{conference: {division: (team codes as used that season)}}."""
    era = _era_for(season)
    return {
        conference: {
            division: tuple(code_in_season(team, season) for team in teams)
            for division, teams in divisions.items()
        }
        for conference, divisions in era.items()
    }


@lru_cache(maxsize=None)
def _membership(season: int) -> dict[str, tuple[str, str]]:
    return {
        team: (conference, division)
        for conference, divisions in alignment(season).items()
        for division, teams in divisions.items()
        for team in teams
    }


def division_of(team: str, season: int) -> tuple[str, str]:
    """(conference, division) for a team in a season.

    Raises rather than guessing: a team-season with no alignment row is a data bug
    we want to see at build time, not a row quietly filed under the wrong division.
    """
    code = normalize_code(team)
    membership = _membership(season)
    if code not in membership:
        raise KeyError(f"{team!r} has no division in {season}")
    return membership[code]


def teams_in_season(season: int) -> tuple[str, ...]:
    return tuple(sorted(_membership(season)))


def divisions_in_season(season: int) -> list[tuple[str, str]]:
    """[(conference, division)] in display order — AFC before NFC."""
    return [
        (conference, division)
        for conference in ("AFC", "NFC")
        for division in alignment(season)[conference]
    ]


def playoff_seeds(season: int) -> int:
    for start, end, seeds in _PLAYOFF_SEEDS:
        if season >= start and (end is None or season <= end):
            return seeds
    raise ValueError(f"No playoff field size defined for season {season}")


def regular_season_weeks(season: int) -> int:
    for start, end, weeks in _REGULAR_SEASON_WEEKS:
        if season >= start and (end is None or season <= end):
            return weeks
    raise ValueError(f"No regular-season length defined for season {season}")


def alias_group(code: str) -> tuple[str, ...]:
    """Every code this franchise has used — for querying its whole history."""
    current = current_code(code) or code
    return FRANCHISE_ALIASES.get(current, (current,))
