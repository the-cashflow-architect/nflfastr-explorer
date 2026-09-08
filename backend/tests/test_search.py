"""Tests for `app.repo.search` and `GET /api/search`.

Team-alias resolution is proven with the STL -> LA relocation, because that is
the one three-letter-code history `factories.py` actually models (`TEAMS_2001`
carries STL, `TEAMS_2024` carries LA, and both are the same fixture franchise).
The task's own acceptance example is "Oakland" / "OAK" / "Raiders" resolving to
the Raiders, but no fixture team ever plays under OAK — see this package's
return notes. STL/LA exercises the identical mechanism (an old code, an old
full name, and a current code all resolving to one franchise), so it stands in
for it here.

`GET /api/search` is exercised against a standalone FastAPI app that mounts
only `app.routers.search`, not `app.main` — `routers/__init__.py::ALL_ROUTERS`
is shared across every package's router and this package does not own it, so
wiring the search router into the real app is left to whoever does.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repo import search as search_repo
from app.routers import search as search_router_module

FIXTURE_FIRST, FIXTURE_LAST = 2001, 2024


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(search_router_module.router)
    return TestClient(app)


class _CountingCursor:
    """Wraps a real DuckDB cursor to record how many rows `fetchall()` actually
    returned for any query whose SQL text contains `substring`.

    This is the only way to tell a real SQL `LIMIT` from a bigger fetch sliced
    down in Python afterwards — both produce the same-length final payload, so
    asserting on the payload alone proves nothing about where the limiting
    happened.
    """

    def __init__(self, real, counts: list[int], substring: str) -> None:
        self._real = real
        self._counts = counts
        self._substring = substring
        self._last_sql = ""

    def execute(self, sql, *args, **kwargs):
        self._last_sql = sql
        self._real.execute(sql, *args, **kwargs)
        return self

    def fetchall(self):
        rows = self._real.fetchall()
        if self._substring in self._last_sql:
            self._counts.append(len(rows))
        return rows

    def __getattr__(self, name):
        return getattr(self._real, name)


def _watch_fetches(built_loader, monkeypatch, substring: str) -> list[int]:
    """Record, for the life of the monkeypatch, the row count `fetchall()`
    returned on every query whose SQL mentions `substring`.
    """
    counts: list[int] = []
    real_cursor_factory = built_loader.cursor
    monkeypatch.setattr(
        built_loader,
        "cursor",
        lambda: _CountingCursor(real_cursor_factory(), counts, substring),
    )
    return counts


# --- shape and the empty-query contract --------------------------------------


def test_group_order_is_fixed_and_always_present(built_loader):
    for query in ("", "  ", "a"):
        payload = search_repo.search(query, loader=built_loader)
        assert [g["type"] for g in payload["groups"]] == list(search_repo.GROUP_ORDER)
        assert all(g["items"] == [] for g in payload["groups"])


def test_nonsense_query_returns_empty_groups_not_an_error(built_loader):
    payload = search_repo.search("qqqqqzzzzznomatch", loader=built_loader)
    assert [g["type"] for g in payload["groups"]] == list(search_repo.GROUP_ORDER)
    assert all(g["items"] == [] for g in payload["groups"])


def test_player_limit_is_enforced_in_sql_not_by_slicing_a_bigger_fetch(built_loader, monkeypatch):
    built_loader.ensure("players")
    cur = built_loader.cursor()
    ids = [r[0] for r in cur.execute("SELECT gsis_id FROM players").fetchall()]
    assert len(ids) > 2, "fixture needs more matches than the limit to prove anything"
    for gsis_id in ids:
        cur.execute(
            "UPDATE players SET display_name = 'Sample Player', last_season = 2024 "
            "WHERE gsis_id = ?",
            [gsis_id],
        )

    fetch_counts = _watch_fetches(built_loader, monkeypatch, search_repo.SEARCH_PLAYERS_TABLE)
    payload = search_repo.search("sample", limit=2, loader=built_loader)
    players = next(g for g in payload["groups"] if g["type"] == "player")["items"]
    assert len(players) == 2
    # The query against `search_players` itself must have returned exactly 2
    # rows from DuckDB — not `len(ids)` rows sliced down to 2 in Python.
    assert fetch_counts == [2]


def test_team_group_fetches_the_whole_table_and_limits_in_python(built_loader, monkeypatch):
    """The teams group is the deliberate exception (see the module docstring):
    32 fixed rows costs nothing to fetch whole and filter in Python, where the
    alias/era logic already lives. Proven, not assumed: watch what `teams_meta`'s
    own cursor returns and confirm it is every row, not `limit` of them.
    """
    built_loader.ensure("teams_meta")
    cur = built_loader.cursor()
    n_teams = len(cur.execute("SELECT team_abbr FROM teams_meta").fetchall())
    assert n_teams > 1, "fixture needs more teams than the limit to prove anything"

    # Every fixture team's name is "<code> Football Club" (see factories.py),
    # so "football" matches all of them — the widest possible team query.
    fetch_counts = _watch_fetches(built_loader, monkeypatch, "teams_meta")
    payload = search_repo.search("football", limit=1, loader=built_loader)
    teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
    assert len(teams) == 1
    assert fetch_counts == [n_teams]


# --- players -------------------------------------------------------------------


def test_player_prefix_match_ranks_above_substring_match(built_loader):
    built_loader.ensure("players")
    cur = built_loader.cursor()
    ids = [r[0] for r in cur.execute("SELECT gsis_id FROM players ORDER BY gsis_id").fetchall()]
    assert len(ids) >= 2
    cur.execute(
        "UPDATE players SET display_name = 'Aaron Rodgers', last_season = 2024 WHERE gsis_id = ?",
        [ids[0]],
    )
    cur.execute(
        "UPDATE players SET display_name = 'Baron Aaronson', last_season = 2024 WHERE gsis_id = ?",
        [ids[1]],
    )

    payload = search_repo.search("aaron", loader=built_loader)
    players = next(g for g in payload["groups"] if g["type"] == "player")["items"]
    names = [p["display_name"] for p in players]
    assert "Aaron Rodgers" in names and "Baron Aaronson" in names
    assert names.index("Aaron Rodgers") < names.index("Baron Aaronson")


def test_active_player_ranks_above_retired_for_an_equal_match_kind(built_loader):
    built_loader.ensure("players")
    cur = built_loader.cursor()
    ids = [r[0] for r in cur.execute("SELECT gsis_id FROM players ORDER BY gsis_id").fetchall()]
    # Neither name is a prefix of the search term, so the only variable left is
    # last_season — isolating the active-over-retired rule from the prefix rule.
    cur.execute(
        "UPDATE players SET display_name = 'John Smithers', last_season = 2024 WHERE gsis_id = ?",
        [ids[0]],
    )
    cur.execute(
        "UPDATE players SET display_name = 'Old Smithers', last_season = 2015 WHERE gsis_id = ?",
        [ids[1]],
    )

    payload = search_repo.search("smithers", loader=built_loader)
    players = next(g for g in payload["groups"] if g["type"] == "player")["items"]
    names = [p["display_name"] for p in players]
    assert names.index("John Smithers") < names.index("Old Smithers")


def test_partial_surname_finds_the_player(built_loader):
    built_loader.ensure("players")
    cur = built_loader.cursor()
    gsis_id = cur.execute("SELECT gsis_id FROM players LIMIT 1").fetchone()[0]
    cur.execute(
        "UPDATE players SET display_name = 'Patrick Mahomes', last_season = 2024 WHERE gsis_id = ?",
        [gsis_id],
    )
    payload = search_repo.search("home", loader=built_loader)  # a partial surname, mid-string
    players = next(g for g in payload["groups"] if g["type"] == "player")["items"]
    assert any(p["gsis_id"] == gsis_id for p in players)


def test_player_result_always_carries_a_real_gsis_id(built_loader):
    built_loader.ensure("players")
    cur = built_loader.cursor()
    cur.execute(
        "INSERT INTO players (gsis_id, display_name, last_season) "
        "VALUES (NULL, 'Noid Ghost Player', 2024)"
    )
    payload = search_repo.search("ghost", loader=built_loader)
    players = next(g for g in payload["groups"] if g["type"] == "player")["items"]
    assert players == []  # an unlinkable player must never surface, not even with an id of None
    for group in payload["groups"]:
        for item in group["items"]:
            assert item.get("id") is not None


def test_players_built_lazily_and_only_once(built_loader):
    """`search_players` is created on first use and never rebuilt on later calls."""
    assert not built_loader.table_exists(search_repo.SEARCH_PLAYERS_TABLE)
    search_repo.search("zz", loader=built_loader)
    assert built_loader.table_exists(search_repo.SEARCH_PLAYERS_TABLE)
    row_count_before = built_loader.row_count(search_repo.SEARCH_PLAYERS_TABLE)

    cur = built_loader.cursor()
    cur.execute(
        "INSERT INTO players (gsis_id, display_name, last_season) "
        "VALUES ('99-99999', 'Late Arrival', 2024)"
    )
    search_repo.search("zz", loader=built_loader)
    # The base `players` table changed, but the derived index does not get rebuilt
    # on a later call — same lazy-build contract as `team_standings`.
    assert built_loader.row_count(search_repo.SEARCH_PLAYERS_TABLE) == row_count_before


# --- teams -----------------------------------------------------------------


def test_current_code_historical_code_and_historical_name_all_resolve_to_one_franchise(built_loader):
    # LA/STL is the one relocation the fixture actually models; see module docstring.
    by_query = {}
    for query in ("LA", "STL", "louis"):  # current code, old code, old full name fragment
        payload = search_repo.search(query, loader=built_loader)
        teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
        matches = [t for t in teams if t["abbr"] == "LA"]
        assert matches, f"{query!r} did not resolve to the LA franchise: {teams}"
        by_query[query] = matches[0]["href"]

    assert len(set(by_query.values())) == 1
    assert by_query["LA"] == "/teams/LA"


def test_team_result_always_carries_the_current_franchise_code(built_loader):
    payload = search_repo.search("STL", loader=built_loader)
    teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
    assert [t["abbr"] for t in teams] == ["LA"]
    assert not any(t["abbr"] == "STL" for t in teams)


def test_a_non_current_code_sitting_in_teams_meta_itself_merges_into_the_current_franchise(
    built_loader,
):
    """`teams_meta` has no `team_columns` (see `sources.py`), so its `team_abbr`
    never passes through `canonical_team_sql` at load time — it is the one place
    a historical code could reach `teams_meta` unmapped. If it ever does, that
    row must merge into the current franchise, not surface as a second, dead
    `/teams/STL` result with a stale name.
    """
    built_loader.ensure("teams_meta")
    cur = built_loader.cursor()
    cur.execute(
        "INSERT INTO teams_meta "
        "(team_abbr, team_name, team_nick, team_conf, team_division, "
        " team_color, team_color2, team_logo_espn, team_logo_squared, team_wordmark) "
        "VALUES ('STL', 'St. Louis Rams (stale row)', 'Rams', 'NFC', 'NFC West', "
        " '#000000', '#ffffff', NULL, NULL, NULL)"
    )

    payload = search_repo.search("STL", loader=built_loader)
    teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
    assert [t["abbr"] for t in teams] == ["LA"]
    assert [t["href"] for t in teams] == ["/teams/LA"]
    # The current-era row's name wins over the stale duplicate's.
    assert teams[0]["label"] == "LA Football Club"

    payload = search_repo.search("LA", loader=built_loader)
    teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
    assert [t["abbr"] for t in teams].count("LA") == 1  # one row, not one per teams_meta row


def test_team_table_is_built_once_per_loader_not_once_per_group_or_request(
    built_loader, monkeypatch
):
    """`_team_records`/`_team_table` used to re-read `teams_meta` and rebuild all
    32 alias token sets on every call — up to four times in one request. Proven
    by counting calls to `_team_tokens`, which only ever runs while the table is
    being built: across two whole requests it must run exactly once per team.
    """
    built_loader.ensure("teams_meta")
    n_teams = len(built_loader.cursor().execute("SELECT team_abbr FROM teams_meta").fetchall())

    calls: list[None] = []
    original = search_repo._team_tokens

    def counting(*args, **kwargs):
        calls.append(None)
        return original(*args, **kwargs)

    monkeypatch.setattr(search_repo, "_team_tokens", counting)

    # Touches the team group and (via the year+text pattern) the team_season group.
    search_repo.search("LA 2001", loader=built_loader)
    # Touches the team group again and, via the matchup pattern, resolves two
    # more team codes through `_resolve_team_code`.
    search_repo.search("BUF at KC", loader=built_loader)

    assert len(calls) == n_teams


def test_team_abbreviation_and_nickname_match(built_loader):
    payload = search_repo.search("KC", loader=built_loader)
    teams = next(g for g in payload["groups"] if g["type"] == "team")["items"]
    assert any(t["abbr"] == "KC" for t in teams)


# --- team seasons ------------------------------------------------------------


def test_team_season_matches_franchise_and_year_by_current_code(built_loader):
    payload = search_repo.search("LA 2001", loader=built_loader)
    team_seasons = next(g for g in payload["groups"] if g["type"] == "team_season")["items"]
    assert team_seasons
    row = team_seasons[0]
    assert row["href"] == "/teams/LA/2001"
    assert row["abbr"] == "LA"
    assert row["season"] == 2001
    # 2001 is inside the pre-relocation era, so the code the club actually
    # played under that year is STL, not the current LA.
    assert row["sublabel"] == "STL"


def test_team_season_matches_by_the_historical_code_too(built_loader):
    payload = search_repo.search("STL 2001", loader=built_loader)
    team_seasons = next(g for g in payload["groups"] if g["type"] == "team_season")["items"]
    assert any(row["href"] == "/teams/LA/2001" for row in team_seasons)


def test_team_season_out_of_window_year_matches_nothing(built_loader):
    payload = search_repo.search("LA 1950", loader=built_loader)
    team_seasons = next(g for g in payload["groups"] if g["type"] == "team_season")["items"]
    assert team_seasons == []


# --- games -------------------------------------------------------------------


def test_games_matchup_pattern_finds_the_game(built_loader):
    payload = search_repo.search("BUF at KC", loader=built_loader)
    games = next(g for g in payload["groups"] if g["type"] == "game")["items"]
    assert games
    assert all(g["matchup"] == "BUF at KC" for g in games)
    assert {g["season"] for g in games} <= {FIXTURE_FIRST, FIXTURE_LAST}


def test_games_game_id_fragment_finds_the_game(built_loader):
    built_loader.ensure("games")
    cur = built_loader.cursor()
    any_id = cur.execute(
        "SELECT game_id FROM games WHERE season = ? LIMIT 1", [FIXTURE_LAST]
    ).fetchone()[0]

    payload = search_repo.search(any_id, loader=built_loader)
    games = next(g for g in payload["groups"] if g["type"] == "game")["items"]
    assert any(g["game_id"] == any_id for g in games)


def test_unplayed_game_shows_no_score_never_a_placeholder_zero(built_loader):
    built_loader.ensure("games")
    cur = built_loader.cursor()
    # The fixture leaves the final week of the latest season unplayed.
    unplayed_id = cur.execute(
        "SELECT game_id FROM games WHERE season = ? AND home_score IS NULL LIMIT 1",
        [FIXTURE_LAST],
    ).fetchone()[0]

    payload = search_repo.search(unplayed_id, loader=built_loader)
    games = next(g for g in payload["groups"] if g["type"] == "game")["items"]
    match = next(g for g in games if g["game_id"] == unplayed_id)
    assert "score" not in match
    assert "date" in match


# --- seasons and draft classes ------------------------------------------------


def test_four_digit_year_matches_both_season_and_draft_class(built_loader):
    payload = search_repo.search(str(FIXTURE_LAST), loader=built_loader)
    by_type = {g["type"]: g["items"] for g in payload["groups"]}
    assert by_type["season"] == [
        {
            "id": f"season-{FIXTURE_LAST}",
            "label": f"{FIXTURE_LAST} Season",
            "sublabel": "Season hub",
            "href": f"/seasons/{FIXTURE_LAST}",
            "season": FIXTURE_LAST,
        }
    ]
    assert by_type["draft"] == [
        {
            "id": f"draft-{FIXTURE_LAST}",
            "label": f"{FIXTURE_LAST} NFL Draft",
            "sublabel": "Draft class",
            "href": f"/draft/{FIXTURE_LAST}",
            "season": FIXTURE_LAST,
        }
    ]


def test_year_before_the_stats_floor_matches_neither(built_loader):
    payload = search_repo.search("1950", loader=built_loader)
    by_type = {g["type"]: g["items"] for g in payload["groups"]}
    assert by_type["season"] == []
    assert by_type["draft"] == []


def test_year_beyond_the_current_season_matches_neither(built_loader):
    payload = search_repo.search(str(FIXTURE_LAST + 5), loader=built_loader)
    by_type = {g["type"]: g["items"] for g in payload["groups"]}
    assert by_type["season"] == []
    assert by_type["draft"] == []


# --- navigation phrases --------------------------------------------------------


def test_navigation_phrase_year_standings(built_loader):
    payload = search_repo.search(f"{FIXTURE_LAST} standings", loader=built_loader)
    nav = next(g for g in payload["groups"] if g["type"] == "navigation")["items"]
    assert any(n["href"] == f"/seasons/{FIXTURE_LAST}/standings" for n in nav)


def test_navigation_phrase_year_draft(built_loader):
    payload = search_repo.search(f"{FIXTURE_LAST} draft", loader=built_loader)
    nav = next(g for g in payload["groups"] if g["type"] == "navigation")["items"]
    assert any(n["href"] == f"/draft/{FIXTURE_LAST}" for n in nav)


def test_navigation_phrase_static_route(built_loader):
    payload = search_repo.search("leaders", loader=built_loader)
    nav = next(g for g in payload["groups"] if g["type"] == "navigation")["items"]
    assert any(n["href"] == "/leaders" for n in nav)


# --- router / app wiring ------------------------------------------------------


def test_get_api_search_endpoint(built_loader):
    from app import deps as deps_module

    deps_module.use_loader(built_loader)
    client = _client()
    response = client.get("/api/search", params={"q": "leaders"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "leaders"
    assert [g["type"] for g in body["groups"]] == list(search_repo.GROUP_ORDER)
    nav = next(g for g in body["groups"] if g["type"] == "navigation")["items"]
    assert any(n["href"] == "/leaders" for n in nav)


def test_get_api_search_short_query_is_empty_not_an_error(built_loader):
    from app import deps as deps_module

    deps_module.use_loader(built_loader)
    client = _client()
    response = client.get("/api/search", params={"q": "a"})
    assert response.status_code == 200
    body = response.json()
    assert all(g["items"] == [] for g in body["groups"])


def test_get_api_search_respects_limit(built_loader):
    from app import deps as deps_module

    built_loader.ensure("players")
    cur = built_loader.cursor()
    for gsis_id, _ in cur.execute("SELECT gsis_id, display_name FROM players").fetchall():
        cur.execute(
            "UPDATE players SET display_name = 'Sample Player', last_season = 2024 "
            "WHERE gsis_id = ?",
            [gsis_id],
        )
    deps_module.use_loader(built_loader)
    client = _client()
    response = client.get("/api/search", params={"q": "sample", "limit": 1})
    body = response.json()
    players = next(g for g in body["groups"] if g["type"] == "player")["items"]
    assert len(players) == 1
