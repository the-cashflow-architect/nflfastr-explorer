"""The one global search the whole product navigates through.

Every group below answers from a table that is already small or already indexed by
the thing being searched — a two-character query has to be fast, and the way to keep
it fast is never to fetch a wide table and filter it in Python. The one deliberate
exception is `teams_meta`, which is a fixed 32-row catalogue (franchises do not
appear or disappear inside a request), so matching it in Python — where the
alignment table's alias and era logic actually lives — costs nothing a LIMIT would
have saved.

Team codes in every loaded table are already the *current* franchise code (see
`etl/alignment.py`); a visitor typing a historical code or name ("OAK", "Oakland
Raiders") has to resolve to that same current code before it can be used to query
anything, which is what `_team_tokens` and `_historical_label` are for.

Rankings never depend on a stored score. Players rank prefix matches above
substring matches and active players above retired ones by reading `last_season`
against the table's own max, both computed at query time; nothing here stores a
"relevance" number that could go stale.
"""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from typing import Any

from .. import sources
from ..config import latest_season
from ..deps import get_loader
from ..etl import alignment
from ..etl import derived

#: Derived once per database, not once per keystroke — the whole reason a
#: precomputed search column exists rather than `lower(strip_accents(...))` on
#: every row of every request. Built lazily, the same way `team_standings` is:
#: see `_ensure_search_players`.
SEARCH_PLAYERS_TABLE = "search_players"

#: Fixed response order. `navigation` is not one of the five entity kinds the
#: product's pages describe, but it is still a search result — the phrase table
#: exists so typing a destination is as fast as typing an entity — so it is
#: appended after them rather than folded into a group it does not belong to.
GROUP_ORDER: tuple[str, ...] = (
    "player", "team", "team_season", "game", "season", "draft", "navigation",
)

DEFAULT_LIMIT = 8
MIN_QUERY_LENGTH = 2
_MAX_LIMIT = 50


# --- players -------------------------------------------------------------------


def _build_search_players(loader: Any) -> None:
    """Build the lowercased, accent-stripped, gsis_id-only player index.

    `gsis_id IS NOT NULL` is not a nicety here — it is the contract the frontend
    depends on: an unlinkable name renders as plain text, and every row this
    endpoint returns is a link, so a player with no id must never surface.

    Built into a staging table and renamed in, because a bare DROP-then-CREATE
    leaves a window in which a concurrent request finds no table at all.
    """
    loader.ensure("players")
    cur = loader.cursor()
    staging = f"{SEARCH_PLAYERS_TABLE}__staging"
    cur.execute(f"DROP TABLE IF EXISTS {staging}")
    cur.execute(
        f"""
        CREATE TABLE {staging} AS
        SELECT
            gsis_id,
            display_name,
            position,
            headshot,
            latest_team,
            rookie_season AS first_season,
            last_season,
            lower(strip_accents(display_name)) AS search_name
        FROM players
        WHERE gsis_id IS NOT NULL AND display_name IS NOT NULL
        """
    )
    rows = cur.execute(f"SELECT count(*) FROM {staging}").fetchone()[0]
    cur.execute(f"DROP TABLE IF EXISTS {SEARCH_PLAYERS_TABLE}")
    cur.execute(f"ALTER TABLE {staging} RENAME TO {SEARCH_PLAYERS_TABLE}")
    derived.record_build(loader, SEARCH_PLAYERS_TABLE, rows)


DERIVED = derived.register(
    derived.Derived(
        name=SEARCH_PLAYERS_TABLE,
        depends_on=("players",),
        build=_build_search_players,
        description="Normalised player names for the global search box.",
        schema=lambda: "gsis_id,display_name,position,headshot,latest_team,first_season,last_season,search_name",
    )
)


def _ensure_search_players(loader: Any) -> None:
    """Build the index if it is missing or older than the player file it reads."""
    derived.ensure(loader, SEARCH_PLAYERS_TABLE, table=SEARCH_PLAYERS_TABLE)


def _search_players(cur: Any, term: str, limit: int) -> list[dict[str, Any]]:
    latest_row = cur.execute(f"SELECT max(last_season) FROM {SEARCH_PLAYERS_TABLE}").fetchone()
    latest = latest_row[0] if latest_row else None
    rows = cur.execute(
        f"""
        SELECT gsis_id, display_name, position, headshot, latest_team,
               first_season, last_season
        FROM {SEARCH_PLAYERS_TABLE}
        WHERE contains(search_name, ?)
        ORDER BY
            starts_with(search_name, ?) DESC,
            (last_season = ?) DESC,
            display_name
        LIMIT ?
        """,
        [term, term, latest, limit],
    ).fetchall()
    items = []
    for gsis_id, display_name, position, headshot, team, first_season, last_season in rows:
        item: dict[str, Any] = {
            "id": gsis_id,
            "label": display_name,
            "href": f"/players/{gsis_id}",
            "gsis_id": gsis_id,
            "display_name": display_name,
            "first_season": first_season,
            "last_season": last_season,
        }
        sublabel_parts = [p for p in (position, team) if p]
        if sublabel_parts:
            item["sublabel"] = " · ".join(sublabel_parts)
        if position:
            item["position"] = position
        if team:
            item["team"] = team
        if headshot:
            item["headshot_url"] = headshot
        items.append(item)
    return items


# --- teams -----------------------------------------------------------------


@dataclass(frozen=True)
class _TeamRecord:
    abbr: str
    name: str
    nick: str
    logo: str | None


#: (record, lowercased search tokens) for every current franchise. Built once per
#: `Loader` and reused — see `_team_table` — because both `teams_meta` and the
#: alias table are fixed for the life of the process; a `WeakKeyDictionary` so a
#: test's throwaway loader (a fresh one per case, see `conftest.built_loader`)
#: never leaks its team table into the next test or outlives the loader itself.
_TeamEntry = tuple[_TeamRecord, tuple[str, ...]]
_TEAM_TABLE_CACHE: "weakref.WeakKeyDictionary[Any, list[_TeamEntry]]" = weakref.WeakKeyDictionary()


def _historical_label(current: str, alias: str, current_name: str) -> str | None:
    """What this franchise was called while it played under `alias`.

    Scans forward from the stats floor for the first season `alias` was the
    code in use; `label_in_season` is constant across an era, so one hit is
    enough. Returns None for a code with no recorded historical name (there
    isn't a fourth relocation on file).
    """
    if alias == current:
        return None
    for season in range(alignment.FIRST_SEASON, latest_season() + 1):
        if alignment.code_in_season(current, season) == alias:
            label = alignment.label_in_season(current, season, current_name)
            return label if label != current_name else None
    return None


def _team_tokens(record: _TeamRecord, legacy_codes: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Every string a visitor might type for this franchise: current and every alias.

    `legacy_codes` folds in whatever raw abbreviations `teams_meta` itself used
    for this franchise before dedupe (see `_team_table`) — on top of the alias
    table's own codes and historical names, which cover a franchise move even
    when `teams_meta` never carried the old code at all.
    """
    tokens = {record.abbr, record.name, record.nick, *legacy_codes}
    for alias in alignment.alias_group(record.abbr):
        tokens.add(alias)
        label = _historical_label(record.abbr, alias, record.name)
        if label:
            tokens.add(label)
    return tuple(sorted({t.lower() for t in tokens if t}))


def _team_table(loader: Any) -> list[_TeamEntry]:
    """Every current franchise, straight from `teams_meta` — computed once per loader.

    32 rows, fixed for the life of the league — see the module docstring for why
    the whole table is fetched once rather than filtered in SQL per query. Cached
    here rather than re-fetched: `_search_teams`, `_search_team_seasons` and
    `_resolve_team_code` can all touch this table in the same request.

    `teams_meta` is the one registered source with no `team_columns` (see
    `sources.py`), so its `team_abbr` never passes through `canonical_team_sql`
    at load time — it is the one place a non-current code could still reach a
    URL. Every abbreviation is run through `alignment.current_code()` here, and
    rows that collapse onto the same franchise are merged into one record
    (keeping the current-era row's name) rather than emitted as a second, dead
    result for the old code.
    """
    cached = _TEAM_TABLE_CACHE.get(loader)
    if cached is not None:
        return cached

    loader.ensure("teams_meta")
    cur = loader.cursor()
    rows = cur.execute(
        "SELECT team_abbr, team_name, team_nick, team_logo_squared FROM teams_meta"
    ).fetchall()

    current_rows: dict[str, tuple[str, str, str, str | None]] = {}
    legacy_codes: dict[str, set[str]] = {}
    for abbr, name, nick, logo in rows:
        current = alignment.current_code(abbr) or abbr
        legacy_codes.setdefault(current, set()).add(abbr)
        # A row whose own abbr already IS the current code carries the
        # current-era name; prefer it over whatever a stale duplicate says.
        if current not in current_rows or abbr == current:
            current_rows[current] = (current, name, nick, logo)

    table: list[_TeamEntry] = []
    for code in sorted(current_rows):
        abbr, name, nick, logo = current_rows[code]
        record = _TeamRecord(abbr, name, nick, logo)
        legacy = tuple(sorted(legacy_codes[code] - {code}))
        table.append((record, _team_tokens(record, legacy)))
    _TEAM_TABLE_CACHE[loader] = table
    return table


def _search_teams(loader: Any, term: str, limit: int) -> list[dict[str, Any]]:
    ranked: list[tuple[bool, _TeamRecord]] = []
    for record, tokens in _team_table(loader):
        matched = [t for t in tokens if term in t]
        if not matched:
            continue
        is_prefix = any(t.startswith(term) for t in matched)
        ranked.append((is_prefix, record))
    ranked.sort(key=lambda pair: (not pair[0], pair[1].name))
    items = []
    for _, record in ranked[:limit]:
        item: dict[str, Any] = {
            "id": record.abbr,
            "label": record.name,
            "sublabel": record.abbr,
            "href": f"/teams/{record.abbr}",
            "abbr": record.abbr,
        }
        if record.logo:
            item["logo_url"] = record.logo
        items.append(item)
    return items


_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _search_team_seasons(loader: Any, raw_query: str, limit: int) -> list[dict[str, Any]]:
    """A franchise plus a year, e.g. 'Chiefs 2024' or 'OAK 1999'."""
    year_match = _YEAR_RE.search(raw_query)
    if not year_match:
        return []
    year = int(year_match.group())
    if year < alignment.FIRST_SEASON or year > latest_season():
        return []
    remainder = (raw_query[: year_match.start()] + raw_query[year_match.end() :]).strip().lower()
    if not remainder:
        return []

    playing_teams = set(alignment.teams_in_season(year))
    items = []
    for record, tokens in _team_table(loader):
        if record.abbr not in playing_teams:
            continue  # the alignment table is the only source of "did this team exist yet"
        if not any(remainder in t for t in tokens):
            continue
        label = alignment.label_in_season(record.abbr, year, record.name)
        item: dict[str, Any] = {
            "id": f"{record.abbr}-{year}",
            "label": f"{year} {label}",
            "sublabel": alignment.code_in_season(record.abbr, year),
            "href": f"/teams/{record.abbr}/{year}",
            "abbr": record.abbr,
            "season": year,
        }
        if record.logo:
            item["logo_url"] = record.logo
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _resolve_team_code(loader: Any, text: str) -> str | None:
    """The current franchise code for a token typed on one side of 'X at Y'."""
    text = text.strip().lower()
    if not text:
        return None
    fallback: str | None = None
    for record, tokens in _team_table(loader):
        if text in tokens:
            return record.abbr
        if fallback is None and any(text in t for t in tokens):
            fallback = record.abbr
    return fallback


# --- games -------------------------------------------------------------------


#: "BAL at KC", "BAL @ KC", "BAL vs KC" — the shapes a visitor actually types.
_MATCHUP_RE = re.compile(r"^(.+?)\s+(?:at|@|vs\.?|v)\s+(.+)$", re.IGNORECASE)


def _game_item(row: tuple) -> dict[str, Any]:
    game_id, season, week, home_team, away_team, home_score, away_score, gameday = row
    matchup = f"{away_team} at {home_team}"
    if home_score is not None and away_score is not None:
        score = f"{away_team} {int(away_score)} – {home_team} {int(home_score)}"
    else:
        score = None  # a scheduled game genuinely has no score yet, never 0-0
    sublabel_parts = [p for p in (score, str(gameday) if gameday else None) if p]
    item: dict[str, Any] = {
        "id": game_id,
        "label": matchup,
        "href": f"/games/{game_id}",
        "game_id": game_id,
        "matchup": matchup,
        "season": season,
        "week": week,
    }
    if sublabel_parts:
        item["sublabel"] = " · ".join(sublabel_parts)
    if gameday:
        item["date"] = str(gameday)
    if score:
        item["score"] = score
    return item


def _search_games(loader: Any, raw_query: str, term: str, limit: int) -> list[dict[str, Any]]:
    loader.ensure("games")
    cur = loader.cursor()
    columns = (
        "game_id, season, week, home_team, away_team, home_score, away_score, gameday"
    )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    matchup = _MATCHUP_RE.match(raw_query.strip())
    if matchup:
        away_code = _resolve_team_code(loader, matchup.group(1))
        home_code = _resolve_team_code(loader, matchup.group(2))
        if away_code and home_code:
            rows = cur.execute(
                f"""
                SELECT {columns} FROM games
                WHERE away_team = ? AND home_team = ?
                ORDER BY gameday DESC
                LIMIT ?
                """,
                [away_code, home_code, limit],
            ).fetchall()
            for row in rows:
                item = _game_item(row)
                if item["id"] not in seen:
                    seen.add(item["id"])
                    items.append(item)

    remaining = limit - len(items)
    if remaining > 0:
        rows = cur.execute(
            f"""
            SELECT {columns} FROM games
            WHERE contains(lower(game_id), ?)
               OR contains(lower(CAST(gameday AS VARCHAR)), ?)
            ORDER BY gameday DESC
            LIMIT ?
            """,
            [term, term, remaining],
        ).fetchall()
        for row in rows:
            item = _game_item(row)
            if item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)

    return items[:limit]


# --- seasons and draft classes -----------------------------------------------


def _year_only(raw_query: str) -> int | None:
    if raw_query.isdigit() and len(raw_query) == 4:
        return int(raw_query)
    return None


def _search_seasons(raw_query: str, limit: int) -> list[dict[str, Any]]:
    year = _year_only(raw_query)
    if year is None or not (sources.FIRST_SEASON <= year <= latest_season()):
        return []
    return [
        {
            "id": f"season-{year}",
            "label": f"{year} Season",
            "sublabel": "Season hub",
            "href": f"/seasons/{year}",
            "season": year,
        }
    ][:limit]


def _search_draft_classes(raw_query: str, limit: int) -> list[dict[str, Any]]:
    year = _year_only(raw_query)
    if year is None or not (sources.DRAFT_FIRST_SEASON <= year <= latest_season()):
        return []
    return [
        {
            "id": f"draft-{year}",
            "label": f"{year} NFL Draft",
            "sublabel": "Draft class",
            "href": f"/draft/{year}",
            "season": year,
        }
    ][:limit]


# --- navigation phrases --------------------------------------------------------
#
# A small, hand-declared list. No fuzzy matching, no scoring model — a visitor
# who types the name of a page gets the page, and nothing here can drift out of
# sync with the route table because there is only one copy of it.
_STATIC_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("leaders", "Leaders", "/leaders"),
    ("finder", "Finder", "/finder"),
    ("compare", "Compare", "/compare"),
    ("glossary", "Glossary", "/glossary"),
    ("player index", "Player index", "/players"),
    ("teams", "Teams", "/teams"),
    ("seasons", "Seasons", "/seasons"),
    ("draft index", "Draft index", "/draft"),
    ("about the data", "Data & methods", "/about/data"),
    ("data and methods", "Data & methods", "/about/data"),
)

_YEAR_STANDINGS_RE = re.compile(r"^(\d{4})\s+standings$")
_YEAR_DRAFT_RE = re.compile(r"^(\d{4})\s+draft$")


def _search_navigation(raw_query: str, term: str, limit: int) -> list[dict[str, Any]]:
    q = raw_query.strip().lower()
    items: list[dict[str, Any]] = []

    standings_match = _YEAR_STANDINGS_RE.match(q)
    if standings_match:
        year = int(standings_match.group(1))
        if sources.FIRST_SEASON <= year <= latest_season():
            items.append(
                {
                    "id": f"nav-standings-{year}",
                    "label": f"{year} standings",
                    "sublabel": "Standings",
                    "href": f"/seasons/{year}/standings",
                }
            )

    draft_match = _YEAR_DRAFT_RE.match(q)
    if draft_match:
        year = int(draft_match.group(1))
        if sources.DRAFT_FIRST_SEASON <= year <= latest_season():
            items.append(
                {
                    "id": f"nav-draft-{year}",
                    "label": f"{year} draft",
                    "sublabel": "Draft class",
                    "href": f"/draft/{year}",
                }
            )

    for phrase, label, href in _STATIC_ROUTES:
        if len(term) >= MIN_QUERY_LENGTH and (phrase.startswith(term) or term == phrase):
            items.append(
                {"id": f"nav-{href}", "label": label, "sublabel": "Go to page", "href": href}
            )

    return items[:limit]


# --- entry point ---------------------------------------------------------------


def _empty_groups(query: str) -> dict[str, Any]:
    return {"query": query, "groups": [{"type": name, "items": []} for name in GROUP_ORDER]}


def search(q: str, limit: int = DEFAULT_LIMIT, *, loader: Any = None) -> dict[str, Any]:
    """The full `/api/search` payload: fixed group order, always present, never an error.

    A query under `MIN_QUERY_LENGTH` answers with empty groups and touches no
    table at all — the two-character latency budget is met by not querying,
    not by querying fast.
    """
    raw = (q or "").strip()
    limit = max(1, min(limit, _MAX_LIMIT))
    if len(raw) < MIN_QUERY_LENGTH:
        return _empty_groups(raw)

    loader = loader or get_loader()
    cur = loader.cursor()
    term = cur.execute("SELECT lower(strip_accents(?))", [raw]).fetchone()[0]

    _ensure_search_players(loader)

    groups: dict[str, list[dict[str, Any]]] = {
        "player": _search_players(cur, term, limit),
        "team": _search_teams(loader, term, limit),
        "team_season": _search_team_seasons(loader, raw, limit),
        "game": _search_games(loader, raw, term, limit),
        "season": _search_seasons(raw, limit),
        "draft": _search_draft_classes(raw, limit),
        "navigation": _search_navigation(raw, term, limit),
    }

    return {"query": raw, "groups": [{"type": name, "items": groups[name]} for name in GROUP_ORDER]}
