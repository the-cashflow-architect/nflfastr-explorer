"""Turning the three team-code vocabularies in our sources into one.

nflverse speaks three dialects:

* **Current codes** — play-by-play, player and team stats, snap counts. A 1999 row
  says `LA`, `LAC`, `LV` even though those franchises were in St. Louis, San Diego
  and Oakland at the time.
* **Period codes** — `games.csv` and the roster files. A 1999 row says `STL`, `SD`,
  `OAK`.
* **PFR codes** — `draft_picks` and the combine, which use Pro-Football-Reference's
  own abbreviations: `GNB`, `KAN`, `NWE`, `SFO`, `TAM`, `RAM`, `RAI`, `SDG`.

Everything in this application is keyed on the current code. The first two dialects
convert with a lookup. The third does not, because three PFR codes mean different
franchises in different decades:

* `STL` is the Cardinals until 1987 and the Rams from 1995.
* `HOU` is the Oilers until 1996 and the Texans from 2002.
* `BAL` is the Colts until 1983 and the Ravens from 1996.

Draft rows therefore resolve by (code, season), and a row that falls in a gap
resolves to nothing and renders as plain text rather than a link to the wrong team.
"""

from __future__ import annotations

from .alignment import current_code

#: PFR draft/combine codes that map cleanly, regardless of season.
_PFR_CODES: dict[str, str] = {
    "ARI": "ARI", "ATL": "ATL", "BUF": "BUF", "CAR": "CAR", "CHI": "CHI",
    "CIN": "CIN", "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET",
    "GNB": "GB", "JAX": "JAX", "KAN": "KC", "MIA": "MIA", "MIN": "MIN",
    "NOR": "NO", "NWE": "NE", "NYG": "NYG", "NYJ": "NYJ", "PHI": "PHI",
    "PIT": "PIT", "SEA": "SEA", "SFO": "SF", "TAM": "TB", "WAS": "WAS",
    "IND": "IND", "TEN": "TEN", "JAC": "JAX",
    # Relocations with no code reuse.
    "PHO": "ARI",           # Phoenix Cardinals, 1988-1993
    "RAM": "LA",            # Los Angeles Rams, through 1994
    "LAR": "LA",
    "RAI": "LV",            # Los Angeles Raiders, 1982-1994
    "OAK": "LV",
    "LVR": "LV",
    "SDG": "LAC",           # San Diego Chargers
    "LAC": "LAC",
}

#: Codes PFR reuses for a different franchise in a different era, as
#: (code, first_season, last_season_inclusive_or_None, franchise).
_ERA_CODES: tuple[tuple[str, int, int | None, str], ...] = (
    ("STL", 1980, 1987, "ARI"),   # St. Louis Cardinals
    ("STL", 1995, 2015, "LA"),    # St. Louis Rams
    ("HOU", 1980, 1996, "TEN"),   # Houston Oilers
    ("HOU", 2002, None, "HOU"),   # Houston Texans
    ("BAL", 1980, 1983, "IND"),   # Baltimore Colts
    ("BAL", 1996, None, "BAL"),   # Baltimore Ravens
)


def franchise_from_draft_code(code: str | None, season: int | None) -> str | None:
    """Resolve a draft or combine team code to a current franchise, or None.

    Returning None is a real answer: it means the code is ambiguous or belongs to
    a franchise outside our window, and the caller should render text rather than
    a link that would point at the wrong team.
    """
    if not code:
        return None
    code = code.strip().upper()
    if season is not None:
        for era_code, first, last, franchise in _ERA_CODES:
            if code == era_code and season >= first and (last is None or season <= last):
                return franchise
    if code in _ERA_CODES_SET:
        return None  # An era code in a gap year — genuinely unknown.
    return _PFR_CODES.get(code) or current_code(code)


_ERA_CODES_SET = {code for code, *_ in _ERA_CODES}
