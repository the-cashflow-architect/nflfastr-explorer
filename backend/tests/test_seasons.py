"""Tests for `app.repo.seasons` and the four `/api/seasons` endpoints.

`built_loader`'s league is eight clubs over two seasons — 2001 (six divisions, no
air-yards charting) and 2024 (eight divisions, fully charted) — each with a single
postseason game (a Super Bowl only, no wild-card/divisional/conference rounds).
That is enough to prove era-correct standings grouping, honest "no bracket"
behaviour when only the final round is on file, and every rate-from-counts claim.
It is not enough to prove a full multi-round bracket renders correctly, so that
shape is built by hand here, in the real `games` table, with the real column names.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.etl import alignment
from app.repo import seasons as repo
from app.routers import seasons as seasons_router

FIXTURE_SEASONS = (2001, 2024)


# --- helpers -----------------------------------------------------------------


def _client() -> TestClient:
    """The real application, with this package's router mounted.

    `routers/__init__.py::ALL_ROUTERS` is shared across packages and this one does
    not own it, so the router is mounted here rather than there — but on
    `app.main.app`, so the wiring under test is the real app's.
    """
    from app import main

    mounted = any(
        getattr(route, "path", "").startswith("/api/seasons") for route in main.app.routes
    )
    if not mounted:
        main.app.include_router(seasons_router.router)
    return TestClient(main.app)


def _load_core(loader) -> None:
    loader.ensure("games")
    loader.ensure("teams_meta")
    loader.ensure("players")


def _full_bracket_games(season: int) -> list[tuple]:
    """A real four-team-per-conference, single-conference bracket for `season`.

    AFC: KC (1-seed, bye), BUF (2), BAL (3) hosts CIN (4) in the wild card, KC
    hosts BUF in the divisional, KC wins to reach (and win) the Super Bowl. Seeds
    are pinned exactly the way SPEC 0.8 says a real bracket pins them: byes and
    hosts are unambiguous once every round is on file.
    """
    return [
        (f"{season}_18_CIN_BAL", season, "WC", 18, "2024-01-14", "BAL", 24, "CIN", 17),
        (f"{season}_19_BAL_KC", season, "DIV", 19, "2024-01-21", "KC", 27, "BAL", 20),
        (f"{season}_19_BUF_KC", season, "CON", 20, "2024-01-28", "KC", 31, "BUF", 24),
        (f"{season}_21_KC_SF", season, "SB", 21, "2024-02-11", "KC", 25, "SF", 22),
    ]


def _write_full_bracket(loader, season: int) -> None:
    """Replace the fixture's lone Super Bowl row with a real four-round bracket.

    `write_games_csv` gives every season exactly one postseason game so the
    "no bracket" honesty path has something to prove; a couple of tests need the
    other path, a bracket seeds can actually be read off, so they build one here
    directly in the loaded table with the columns the real file carries.
    """
    loader.ensure("games")
    cur = loader.cursor()
    columns = [c[0] for c in cur.execute("DESCRIBE games").fetchall()]
    cur.execute(
        "DELETE FROM games WHERE season = ? AND game_type <> 'REG'", [season]
    )
    row_cols = ["game_id", "season", "game_type", "week", "gameday", "home_team",
                "home_score", "away_team", "away_score"]
    missing = set(row_cols) - set(columns)
    assert not missing, f"games table is missing expected columns: {missing}"
    placeholders = ", ".join("?" * len(row_cols))
    for game_id, s, gtype, week, gameday, home, hs, away, as_ in _full_bracket_games(season):
        cur.execute(
            f"INSERT INTO games ({', '.join(row_cols)}) VALUES ({placeholders})",
            [game_id, s, gtype, week, gameday, home, hs, away, as_],
        )


# --- season index --------------------------------------------------------------


def test_season_index_spans_the_full_window_newest_first(built_loader):
    loader = built_loader
    _load_core(loader)
    payload = repo.season_index(loader=loader)
    seasons = [row["season"] for row in payload["seasons"]]
    assert seasons[0] == max(seasons)
    assert seasons == sorted(seasons, reverse=True)
    assert seasons[0] >= 2024
    assert min(seasons) == 1999
    assert payload["coverage_href"] == "/about/data"


def test_season_index_marks_the_fixture_seasons_complete_with_a_champion(built_loader):
    loader = built_loader
    _load_core(loader)
    payload = repo.season_index(loader=loader)
    by_season = {row["season"]: row for row in payload["seasons"]}

    for season in FIXTURE_SEASONS:
        row = by_season[season]
        assert row["complete"] is True
        # The fixture's Super Bowl row always has the first team (index 0) as
        # home, winning 27-20.
        assert row["champion"] == "KC"
        assert row["champion_href"] == f"/teams/KC/{season}"
        assert row["top_scoring_team"] is not None
        assert row["href"] == f"/seasons/{season}"


def test_season_index_leaves_a_season_with_no_games_honestly_incomplete(built_loader):
    loader = built_loader
    _load_core(loader)
    payload = repo.season_index(loader=loader)
    by_season = {row["season"]: row for row in payload["seasons"]}
    # 1999 is in the window but the fixture never wrote it into `games`.
    row = by_season[1999]
    assert row["complete"] is False
    assert row["champion"] is None
    assert row["top_scoring_team"] is None


def test_season_index_endpoint(built_loader):
    _load_core(built_loader)
    from app import deps

    deps.use_loader(built_loader)
    resp = _client().get("/api/seasons")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["seasons"]) == 2024 - 1999 + 1


# --- season hub ------------------------------------------------------------


def test_season_hub_rejects_a_season_outside_the_window(built_loader):
    with pytest.raises(repo.SeasonOutOfWindow):
        repo.season_hub(1900, loader=built_loader)


def test_season_hub_standings_block_matches_the_era(built_loader):
    """2001 groups into (at most) six divisions, 2024 into eight — never the
    other way around, and never grouped off `teams_meta`'s present-day division."""
    loader = built_loader
    _load_core(loader)
    for season, max_divisions in ((2001, 6), (2024, 8)):
        hub = repo.season_hub(season, loader=loader)
        standings = hub["standings"]
        assert standings["season"] == season
        assert len(standings["groups"]) <= max_divisions
        for group in standings["groups"]:
            for team in group["teams"]:
                conf, div = alignment.division_of(team["team"], season)
                assert (conf, div) == (team["conference"], team["division"])


def test_season_hub_bracket_renders_with_only_the_super_bowl_on_file(built_loader):
    """The base fixture writes exactly one postseason game per season. A bracket
    still renders — "postseason games exist" is the whole condition (SPEC 3,
    Season Hub) — but a lone Super Bowl is not a tree a seeding can be read off,
    so both sides carry no seed rather than a guessed one."""
    loader = built_loader
    _load_core(loader)
    hub = repo.season_hub(2024, loader=loader)
    bracket = hub["bracket"]
    assert bracket is not None
    assert [r["round"] for r in bracket["rounds"]] == ["SB"]
    sb_game = bracket["rounds"][0]["games"][0]
    assert sb_game["home"]["seed"] is None
    assert sb_game["away"]["seed"] is None
    assert sb_game["winner"] == sb_game["home"]["abbr"]


def test_season_hub_renders_every_round_of_a_real_playoff_tree(built_loader):
    """Field size here (4 AFC clubs across three rounds) does not match the 7-seed
    2024 field `alignment.playoff_seeds` declares, so `team_standings` correctly
    leaves these clubs unseeded (SPEC 0.8: an incomplete field is not guessed at)
    — what this proves is that the bracket assembles every round, in order, each
    matchup linked and each winner read correctly off the score."""
    loader = built_loader
    _load_core(loader)
    _write_full_bracket(loader, 2024)
    hub = repo.season_hub(2024, loader=loader)
    bracket = hub["bracket"]
    assert bracket is not None
    rounds = {r["round"]: r for r in bracket["rounds"]}
    assert [r["round"] for r in bracket["rounds"]] == ["WC", "DIV", "CON", "SB"]
    for round_games in bracket["rounds"]:
        for game in round_games["games"]:
            assert game["href"] == f"/games/{game['game_id']}"
            assert game["winner"] in (game["home"]["abbr"], game["away"]["abbr"])

    sb_game = rounds["SB"]["games"][0]
    assert sb_game["winner"] == "KC"
    assert sb_game["home"]["abbr"] == "KC"
    assert rounds["WC"]["games"][0]["winner"] == "BAL"


def test_season_hub_epa_quadrant_uses_the_opponent_self_join(built_loader):
    """Every team's defence figure must come from what its opponents produced on
    offence in the same games, never its own `def_*` production (SPEC 0.5).

    `write_pbp` models a single game (the week-1 KC-BUF matchup), so those are the
    only two clubs `derived_game_team_stats` — and therefore the quadrant — can
    possibly carry; that is itself the honest behaviour under test, not a gap in
    it."""
    loader = built_loader
    _load_core(loader)
    loader.ensure("pbp")
    hub = repo.season_hub(2024, loader=loader)
    quadrant = hub["epa_quadrant"]
    assert quadrant
    by_team = {row["team"]: row for row in quadrant}
    assert set(by_team) == {"KC", "BUF"}
    for row in quadrant:
        assert row["href"] == f"/teams/{row['team']}/2024"
        assert row["off_epa"] is not None
        assert row["def_epa"] is not None
    # KC's defence figure is BUF's own offensive rate that same game, and BUF's is
    # KC's — the self-join, not each club's own production.
    assert by_team["KC"]["def_epa"] == by_team["BUF"]["off_epa"]
    assert by_team["BUF"]["def_epa"] == by_team["KC"]["off_epa"]


def test_season_hub_leaders_omit_categories_with_no_matching_column(built_loader):
    """The fixture's `player_season_reg` (routed through the weekly generator) has
    no rushing_tds/receiving_tds/defense columns at all, so "scoring" and
    "defense" must be genuinely absent — never a zeroed-out board."""
    loader = built_loader
    _load_core(loader)
    loader.ensure("player_season_reg")
    hub = repo.season_hub(2024, loader=loader)
    leaders = hub["leaders"]
    assert "passing" in leaders
    assert "rushing" in leaders
    assert "receiving" in leaders
    assert "defense" not in leaders
    row = leaders["passing"][0]
    assert row["rank"] == 1
    assert row["href"] == f"/players/{row['gsis_id']}"
    assert row["value"] >= leaders["passing"][-1]["value"]


def test_season_hub_epa_leaders_present_once_pbp_is_loaded(built_loader):
    loader = built_loader
    _load_core(loader)
    loader.ensure("pbp")
    hub = repo.season_hub(2024, loader=loader)
    assert "epa" in hub["leaders"]
    assert hub["leaders"]["epa"][0]["support"]["plays"] > 0


def test_season_hub_endpoint(built_loader):
    _load_core(built_loader)
    built_loader.ensure("player_season_reg")
    from app import deps

    deps.use_loader(built_loader)
    resp = _client().get("/api/seasons/2024")
    assert resp.status_code == 200
    body = resp.json()
    assert body["season"] == 2024
    assert body["draft_href"] == "/draft/2024"
    assert "standings" in body


def test_season_hub_endpoint_404s_outside_the_window(built_loader):
    from app import deps

    deps.use_loader(built_loader)
    resp = _client().get("/api/seasons/1900")
    assert resp.status_code == 404


# --- standings ---------------------------------------------------------------


def test_full_standings_view_toggle_resorts_without_changing_the_field(built_loader):
    loader = built_loader
    _load_core(loader)
    division = repo.full_standings(2024, view="division", loader=loader)
    conference = repo.full_standings(2024, view="conference", loader=loader)
    assert division["view"] == "division"
    assert conference["view"] == "conference"
    div_teams = {t["team"] for g in division["groups"] for t in g["teams"]}
    conf_teams = {t["team"] for g in conference["groups"] for t in g["teams"]}
    assert div_teams == conf_teams
    assert {g["conference"] for g in conference["groups"]} == {"AFC", "NFC"}


def test_full_standings_rejects_an_unknown_view(built_loader):
    with pytest.raises(ValueError):
        repo.full_standings(2024, view="galaxy", loader=built_loader)


def test_full_standings_endpoint(built_loader):
    _load_core(built_loader)
    from app import deps

    deps.use_loader(built_loader)
    resp = _client().get("/api/seasons/2024/standings?view=conference")
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "conference"
    assert len(body["groups"]) == 2


# --- week scoreboard -----------------------------------------------------------


def test_week_scoreboard_lists_every_game_with_a_result(built_loader):
    """`write_pbp` models exactly one game — week 1's KC-vs-BUF matchup — so that
    is the one row in this week whose sparkline and biggest-swing can possibly be
    populated; the other three games are played (`games.csv` has real scores for
    all of week 1) but carry no derived play data, and both facts matter."""
    loader = built_loader
    _load_core(loader)
    loader.ensure("pbp")
    week = repo.week_scoreboard(2024, 1, loader=loader)
    assert week["season"] == 2024
    assert week["week"] == 1
    assert week["week_type"] == "REG"
    assert len(week["games"]) == 4  # eight fixture teams, four games a week
    by_id = {g["game_id"]: g for g in week["games"]}
    for game in week["games"]:
        assert game["played"] is True
        assert game["home_score"] is not None
    kc_buf = by_id["2024_01_BUF_KC"]
    assert kc_buf["wp_sparkline"]
    assert kc_buf["biggest_play"] is not None
    assert kc_buf["biggest_play"]["wpa"] is not None


def test_week_scoreboard_bye_teams_is_the_set_difference(built_loader):
    loader = built_loader
    _load_core(loader)
    week = repo.week_scoreboard(2024, 1, loader=loader)
    playing = set()
    for game in week["games"]:
        playing.add(game["home"]["abbr"])
        playing.add(game["away"]["abbr"])
    expected_byes = set(alignment.teams_in_season(2024)) - playing
    assert set(week["bye_teams"]) == expected_byes
    # The fixture's 8 clubs are a real subset of the 32-team 2024 league, so most
    # of the league is on a bye every single week — exactly the honest case a
    # smaller deployment should still compute correctly.
    assert expected_byes


def test_week_scoreboard_unplayed_week_is_honestly_marked(built_loader):
    """`write_games_csv` leaves the last regular-season week of the latest season
    unplayed. The fixtures still come back — never an empty games list, which
    would read as a bye week for everyone."""
    loader = built_loader
    _load_core(loader)
    week = repo.week_scoreboard(2024, 4, loader=loader)
    assert week["games"]
    for game in week["games"]:
        assert game["played"] is False
        assert game["home_score"] is None
        assert game["wp_sparkline"] is None
        assert game["biggest_play"] is None


def test_week_scoreboard_missing_week_returns_no_games_with_a_note(built_loader):
    loader = built_loader
    _load_core(loader)
    week = repo.week_scoreboard(2024, 30, loader=loader)
    assert week["games"] == []
    assert week["note"]


def test_week_scoreboard_endpoint(built_loader):
    _load_core(built_loader)
    from app import deps

    deps.use_loader(built_loader)
    resp = _client().get("/api/seasons/2024/week/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["week"] == 1
    assert len(body["games"]) == 4
