"""Tests for `app.repo.games` and the two `/api/games` endpoints.

The `built_loader` fixture's league is eight clubs over two seasons — 2001, one
season before both the realignment and the air-yards charting boundary, and 2024,
one after — plus one unplayed week in the later season, which is the fixture's
stand-in for the 2026 schedule `games.csv` also carries. That is enough to hold
the four claims this package makes: a pre-charting game shows no air-yards
columns rather than zeros, a scheduled game shows a fixture rather than a 0-0 box
score, a single game's context is a percentile among team-games and never a rank
out of 32, and a season whose plays are not resident materialises on demand and
says so honestly while it does.

Two source shapes the fixture does not publish are built by hand here, in real
tables with the published column names, because the blocks that depend on them
are exactly the ones that must disappear when the data does not exist:

* `snap_counts` (2012+) and its `pfr_id` join to `players`, including one player
  no id matches — the case whose share must stay unknown rather than become zero.
* `officials`, whose crew rows the schedule file does not carry.

The closing-line columns are added to the loaded `games` table the same way,
since `factories.write_games_csv` writes a schedule without betting columns —
which is itself the "only fields that exist" case, tested before they are added.

`factories.py` is shared, so none of that was added there; see this package's
return notes.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import sources
from app.loader import SeasonBusy
from app.repo import games as repo
from app.routers import games as games_router

#: The fixture's week-one game in each season: KC at home, BUF away, and the only
#: game the play-by-play factory writes plays for.
GAME_2024 = "2024_01_BUF_KC"
GAME_2001 = "2001_01_BUF_KC"
#: Week four of the latest fixture season is written with no scores — the
#: schedule-only game.
UNPLAYED_2024 = "2024_04_KC_BUF"


# --- helpers -----------------------------------------------------------------


def _client() -> TestClient:
    """The real application with this package's router mounted.

    `routers/__init__.py::ALL_ROUTERS` is shared across packages and this one does
    not own it, so the router is mounted here rather than there — but on
    `app.main.app`, so the wiring under test is the real app's.
    """
    from app import main

    mounted = any(
        getattr(route, "path", "") == "/api/games/{game_id}" for route in main.app.routes
    )
    if not mounted:
        main.app.include_router(games_router.router)
    return TestClient(main.app)


def _write_snap_counts(loader, season: int, game_id: str) -> None:
    """Two clubs' snaps for one game, in the published column names.

    `Play01` is a pfr_id `players` carries; `NOBODY` is one it does not, which is
    the row whose player link has to be absent rather than guessed.
    """
    cur = loader.cursor()
    cur.execute(
        """
        CREATE OR REPLACE TABLE snap_counts (
          game_id VARCHAR, season INTEGER, week INTEGER, player VARCHAR,
          pfr_player_id VARCHAR, position VARCHAR, team VARCHAR, opponent VARCHAR,
          offense_snaps DOUBLE, offense_pct DOUBLE,
          defense_snaps DOUBLE, defense_pct DOUBLE,
          st_snaps DOUBLE, st_pct DOUBLE
        )
        """
    )
    cur.executemany(
        "INSERT INTO snap_counts VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (game_id, season, "Player 1", "Play01", "QB", "KC", "BUF",
             60.0, 1.0, 0.0, 0.0, 2.0, 0.08),
            (game_id, season, "Nobody At All", "NOBODY", "WR", "KC", "BUF",
             30.0, 0.5, 0.0, 0.0, 10.0, 0.4),
            (game_id, season, "Player 2", "Play02", "CB", "BUF", "KC",
             0.0, 0.0, 55.0, 0.95, 4.0, 0.16),
        ],
    )


def _write_officials(loader, game_id: str) -> None:
    cur = loader.cursor()
    cur.execute(
        "CREATE OR REPLACE TABLE officials ("
        "  game_id VARCHAR, official_name VARCHAR, off_pos VARCHAR)"
    )
    cur.executemany(
        "INSERT INTO officials VALUES (?, ?, ?)",
        [
            (game_id, "Ref One", "Referee"),
            (game_id, "Ump Two", "Umpire"),
            ("some_other_game", "Not This Crew", "Referee"),
        ],
    )


def _add_betting_columns(loader, game_id: str) -> None:
    """The closing line, added to the loaded schedule table after the fact.

    `factories.write_games_csv` writes no betting columns, which is how the
    "absent, not null" case is tested; these four are what the real file carries.
    """
    cur = loader.cursor()
    for column in ("spread_line", "total_line", "home_moneyline", "away_moneyline"):
        cur.execute(f'ALTER TABLE games ADD COLUMN IF NOT EXISTS "{column}" DOUBLE')
    cur.execute(
        "UPDATE games SET spread_line = 3.0, total_line = 40.0, "
        "home_moneyline = -160, away_moneyline = 140 WHERE game_id = ?",
        [game_id],
    )


# --- the game payload --------------------------------------------------------


def test_game_header_carries_only_fields_the_schedule_file_has(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    header = payload["header"]

    assert header["game_id"] == GAME_2024
    assert header["season"] == 2024
    assert header["home"]["abbr"] == "KC"
    assert header["away"]["abbr"] == "BUF"
    assert header["roof"] == "outdoors"
    assert header["surface"] == "grass"
    assert header["referee"] == "Ref One"
    assert header["home"]["coach"] == "Coach KC"

    # Not in games.csv, not in any verified source, so not keys at all.
    for absent in ("attendance", "duration", "tv_network", "network"):
        assert absent not in header

    assert payload["status"]["played"] is True
    assert payload["final"]["home"] == header["home"]["score"]


def test_scoring_line_score_and_drives_come_from_the_derived_tables(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)

    line = payload["line_score"]
    assert line["source"] == "derived_scoring_plays"
    assert [p["period"] for p in line["periods"]] == sorted(
        p["period"] for p in line["periods"]
    )
    # Periods add up to the running total the scoring plays produced.
    assert sum(p["home"] for p in line["periods"]) == line["home_total"]
    assert sum(p["away"] for p in line["periods"]) == line["away_total"]

    assert payload["scoring"], "the fixture game scores"
    first = payload["scoring"][0]
    assert first["anchor"] == f"play-{first['play_id']}"

    drives = payload["drives"]
    assert drives, "the fixture game has drives"
    for drive in drives:
        if drive["start_yardline_100"] is not None and drive["end_yardline_100"] is not None:
            assert drive["net_yards"] == (
                drive["start_yardline_100"] - drive["end_yardline_100"]
            )
    # Drive EPA is not stored in derived_drives, so it is not invented here.
    assert "epa" not in drives[0]


def test_win_probability_is_downsampled_and_names_its_biggest_swing(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    wp = payload["win_probability"]

    assert wp["points"], "the fixture game has a win-probability series"
    assert len(wp["points"]) <= repo.MAX_WP_POINTS
    assert len(wp["points"]) <= wp["points_stored"]
    assert all(0.0 <= point["home_wp"] <= 1.0 for point in wp["points"])

    swing = wp["biggest_swing"]
    assert swing["computed_by_us"] is True
    assert "not certainly" in swing["note"] or "rather than" in swing["note"]
    # The named swing is the largest step in the stored series, not a guess.
    assert swing["delta"] == pytest.approx(
        round(swing["home_wp_after"] - swing["home_wp_before"], 4), abs=1e-4
    )

    # The Vegas-informed series is not in our column projection, so it is absent.
    assert all("vegas_home_wp" not in point for point in wp["points"])


def test_team_stat_context_is_a_percentile_among_team_games_not_a_rank(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    stats = payload["team_stats"]

    ids = {row["stat"] for row in stats["rows"]}
    assert {"epa_per_play", "success_rate", "yards"} <= ids

    cur = built_loader.cursor()
    team_games = cur.execute(
        "SELECT count(*) FROM derived_game_team_stats WHERE season = 2024"
    ).fetchone()[0]

    for row in stats["rows"]:
        # A single game is never ranked 1-of-32 (SPEC section 3, correction 5).
        assert "rank" not in row and "of" not in row
        for side in ("home_context", "away_context"):
            context = row[side]
            if context is None:
                continue
            assert set(context) == {"percentile", "n", "season"}
            assert 0.0 <= context["percentile"] <= 1.0
            assert context["season"] == 2024
            assert context["n"] <= team_games

    assert stats["team_games_in_season"] == team_games
    assert "percentile" in stats["percentile_method"]


def test_rates_are_divided_from_the_stored_counts(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    rows = {row["stat"]: row for row in payload["team_stats"]["rows"]}
    home = payload["header"]["home"]["abbr"]

    plays, epa, successes = built_loader.cursor().execute(
        "SELECT plays, epa_total, successes FROM derived_game_team_stats "
        "WHERE game_id = ? AND team = ?",
        [GAME_2024, home],
    ).fetchone()

    assert rows["epa_per_play"]["home"] == pytest.approx(epa / plays, abs=1e-4)
    assert rows["success_rate"]["home"] == pytest.approx(successes / plays, abs=1e-4)


def test_box_score_shows_air_yards_only_in_the_charting_era(built_loader):
    modern = repo.game(GAME_2024, loader=built_loader)["box_score"]
    charting_columns = {
        column["id"]
        for category in modern["categories"]
        for column in category["columns"]
    }
    assert "passing_cpoe" in charting_columns
    assert "receiving_air_yards" in charting_columns
    assert modern["charting_note"] is None

    old = repo.game(GAME_2001, loader=built_loader)["box_score"]
    old_columns = {
        column["id"]
        for category in old["categories"]
        for column in category["columns"]
    }
    # Nobody charted air yards before 2006, so the columns are absent rather than
    # present and zero.
    assert "passing_cpoe" not in old_columns
    assert "receiving_air_yards" not in old_columns
    assert str(sources.CHARTING_FIRST_SEASON) in old["charting_note"]

    # The weekly factory only puts KC on the field in week one, so the away side
    # of this game genuinely has no box line — which is a list with nothing in it,
    # not a category that vanishes for the club that did play.
    passing = next(c for c in modern["categories"] if c["id"] == "passing")
    assert passing["home"]
    assert all(row["href"].startswith("/players/") for row in passing["home"])
    # Sorted by the category's leading column, so the starter is the first row.
    attempts = [row["values"]["attempts"] for row in passing["home"]]
    assert attempts == sorted(attempts, reverse=True)


def test_a_pre_2012_game_has_no_snap_block_at_all(built_loader):
    _write_snap_counts(built_loader, 2001, GAME_2001)
    payload = repo.game(GAME_2001, loader=built_loader)

    assert "snaps" not in payload
    coverage = payload["coverage"]
    assert coverage["snap_counts_available"] is False
    assert coverage["snap_counts_first_season"] == sources.SNAP_COUNTS_FIRST_SEASON
    assert coverage["air_yards_charted"] is False


def test_snap_rows_keep_an_unmatched_player_without_inventing_a_link(built_loader):
    _write_snap_counts(built_loader, 2024, GAME_2024)
    snaps = repo.game(GAME_2024, loader=built_loader)["snaps"]

    matched = {row["name"]: row for row in snaps["home"]}
    assert matched["Player 1"]["gsis_id"] is not None
    assert matched["Player 1"]["href"].startswith("/players/")
    # No pfr_id matched: no link, and the snaps he did play are still his.
    assert matched["Nobody At All"]["gsis_id"] is None
    assert matched["Nobody At All"]["href"] is None
    assert matched["Nobody At All"]["offense_snaps"] == 30.0
    assert snaps["unmatched_players"] == 1
    # Shares stay proportions whatever units the file ships them in.
    assert matched["Player 1"]["offense_pct"] == 1.0
    assert snaps["away"][0]["defense_pct"] == 0.95


def test_officials_and_betting_are_absent_until_their_sources_exist(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    assert "officials" not in payload
    assert "betting" not in payload
    # The referee is in the schedule file, so it survives with no officials file.
    assert payload["header"]["referee"] == "Ref One"

    _write_officials(built_loader, GAME_2024)
    _add_betting_columns(built_loader, GAME_2024)
    payload = repo.game(GAME_2024, loader=built_loader)

    assert [official["name"] for official in payload["officials"]] == [
        "Ref One", "Ump Two",
    ]
    betting = payload["betting"]
    assert betting["spread_line"] == 3.0
    home = payload["final"]["home"]
    away = payload["final"]["away"]
    assert betting["home_margin"] == home - away
    assert betting["ats_result"] == ("home" if home - away > 3.0 else "away")
    assert betting["ou_result"] == ("over" if home + away > 40.0 else "under")
    assert "ats_result" in betting["computed_by_us"]


def test_an_unplayed_game_is_a_fixture_not_a_zeroed_box_score(built_loader):
    payload = repo.game(UNPLAYED_2024, loader=built_loader)

    assert payload["status"]["played"] is False
    assert payload["status"]["label"] == "Scheduled"
    assert payload["header"]["home"]["score"] is None
    assert payload["header"]["stadium"]
    for absent in (
        "final", "line_score", "scoring", "win_probability", "team_stats",
        "drives", "box_score", "snaps", "play_log",
    ):
        assert absent not in payload, f"{absent} must not exist for an unplayed game"


def test_unknown_game_is_a_lookup_failure(built_loader):
    with pytest.raises(repo.UnknownGame):
        repo.game("2024_01_NOT_AGAME", loader=built_loader)


def test_play_log_info_counts_only_what_is_already_reachable(built_loader):
    payload = repo.game(GAME_2024, loader=built_loader)
    info = payload["play_log"]

    assert info["source"] == "resident"
    assert info["ready"] is True
    plays = built_loader.cursor().execute(
        "SELECT count(*) FROM pbp WHERE game_id = ?", [GAME_2024]
    ).fetchone()[0]
    assert info["total_plays"] == plays
    assert info["href"] == f"/api/games/{GAME_2024}/plays"


# --- the play log ------------------------------------------------------------


def test_play_log_pages_and_filters(built_loader):
    everything = repo.plays(GAME_2024, loader=built_loader)
    assert everything["rows"]
    assert everything["total"] == len(everything["rows"])
    assert everything["source"] == "resident"

    first = repo.plays(GAME_2024, page_size=5, loader=built_loader)
    second = repo.plays(GAME_2024, page=2, page_size=5, loader=built_loader)
    assert len(first["rows"]) == 5
    assert first["total"] == everything["total"]
    assert [r["play_id"] for r in first["rows"]] != [r["play_id"] for r in second["rows"]]

    options = everything["filter_options"]
    assert set(options["teams"]) == {"KC", "BUF"}

    by_team = repo.plays(GAME_2024, team="KC", loader=built_loader)
    assert by_team["rows"] and all(r["posteam"] == "KC" for r in by_team["rows"])
    assert by_team["total"] < everything["total"]
    assert by_team["filters_applied"]["team"] == "KC"

    by_down = repo.plays(GAME_2024, down=3, loader=built_loader)
    assert all(r["down"] == 3 for r in by_down["rows"])

    by_type = repo.plays(GAME_2024, play_type="pass", loader=built_loader)
    assert all(r["play_type"] == "pass" for r in by_type["rows"])

    by_epa = repo.plays(GAME_2024, min_abs_epa=0.5, loader=built_loader)
    assert by_epa["rows"] and all(abs(r["epa"]) >= 0.5 for r in by_epa["rows"])

    drive = everything["rows"][0]["drive"]
    by_drive = repo.plays(GAME_2024, drive=drive, loader=built_loader)
    assert all(r["drive"] == drive for r in by_drive["rows"])


def test_play_rows_carry_air_yards_only_from_the_charting_era(built_loader):
    modern = repo.plays(GAME_2024, loader=built_loader)
    assert modern["coverage"]["air_yards_charted"] is True
    assert any("air_yards" in row for row in modern["rows"])
    assert modern["coverage_note"] is None

    old = repo.plays(GAME_2001, loader=built_loader)
    assert old["rows"], "an on-demand season still answers with its plays"
    assert old["source"] == "on_demand"
    assert all("air_yards" not in row for row in old["rows"])
    assert str(sources.CHARTING_FIRST_SEASON) in old["coverage_note"]


def test_a_busy_season_is_an_honest_wait_not_an_empty_play_list(built_loader, monkeypatch):
    def busy(self, season):
        raise SeasonBusy("Another season is still loading.")

    monkeypatch.setattr(type(built_loader), "pbp_relation", busy)
    with pytest.raises(repo.SeasonLoading) as excinfo:
        repo.plays(GAME_2001, loader=built_loader)
    message = str(excinfo.value)
    assert "2001" in message and "try again" in message


def test_an_unplayed_game_has_no_rows_key(built_loader):
    payload = repo.plays(UNPLAYED_2024, loader=built_loader)
    assert payload["played"] is False
    # Not an empty list: that would read as "this game had no plays".
    assert "rows" not in payload
    assert "not been played" in payload["note"]


def test_a_played_game_with_no_plays_on_file_says_so(built_loader):
    """The factory writes plays for week one only, which is this case exactly."""
    payload = repo.plays("2024_02_KC_BUF", loader=built_loader)

    assert payload["played"] is True
    assert payload["rows"] == []
    assert payload["total"] == 0
    assert "carries no plays for this game" in payload["note"]


def test_bad_paging_and_a_team_that_did_not_play_are_refused(built_loader):
    with pytest.raises(ValueError):
        repo.plays(GAME_2024, page=0, loader=built_loader)
    with pytest.raises(ValueError):
        repo.plays(GAME_2024, page_size=repo.MAX_PAGE_SIZE + 1, loader=built_loader)
    with pytest.raises(ValueError) as excinfo:
        repo.plays(GAME_2024, team="SF", loader=built_loader)
    assert "did not play in this game" in str(excinfo.value)


# --- the endpoints -----------------------------------------------------------


def test_endpoints_answer_on_the_real_app(built_loader):
    client = _client()

    response = client.get(f"/api/games/{GAME_2024}")
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["home"]["abbr"] == "KC"
    assert body["team_stats"]["rows"]
    # Absent blocks stay absent through the response model, not null keys.
    assert "snaps" not in body
    assert "betting" not in body

    plays = client.get(
        f"/api/games/{GAME_2024}/plays", params={"team": "KC", "page_size": 5}
    )
    assert plays.status_code == 200
    assert len(plays.json()["rows"]) <= 5

    assert client.get("/api/games/2024_01_NOT_AGAME").status_code == 404
    assert client.get(f"/api/games/{GAME_2024}/plays?team=SF").status_code == 400


def test_a_loading_season_is_a_503_with_a_real_sentence(built_loader, monkeypatch):
    def busy(self, season):
        raise SeasonBusy("Another season is still loading.")

    monkeypatch.setattr(type(built_loader), "pbp_relation", busy)
    response = _client().get(f"/api/games/{GAME_2001}/plays")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "2001" in detail and detail.endswith(".")


def test_no_coverage_year_is_written_into_this_package():
    """Every window comes from the registry; a literal year here would drift.

    Prose may cite one — the docstrings above do — so docstrings and comments are
    stripped before the check, and what is left is the code that would actually
    decide what the site claims to know.
    """
    for module in (repo, games_router):
        with open(module.__file__, encoding="utf-8") as handle:
            body = handle.read()
        body = re.sub(r'""".*?"""', "", body, flags=re.DOTALL)
        code = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("#")
        )
        found = re.findall(r"\b(?:19|20)\d{2}\b", code)
        assert not found, f"{module.__name__} hardcodes {found}"
