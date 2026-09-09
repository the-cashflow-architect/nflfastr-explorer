"""Tests for `app.repo.teams` and the four `/api/teams` endpoints.

The `built_loader` fixture's league is eight clubs over two seasons — 2001, one
season before both the realignment and the air-yards charting boundary, and 2024,
one after. That is enough to prove era-correct grouping (six divisions in 2001,
eight in 2024), historical-code resolution (STL answers as the Rams and a 2001 row
prints "St. Louis Rams"), and every rate-from-counts claim.

Three source shapes the fixture does not model are built by hand here, in the real
tables, with the real column names, because the claims that depend on them are the
ones most worth holding:

* `team_week` reciprocity. `factories.write_team_week` pairs a team with an
  opponent that does not carry it back, so no club's opponent row is findable and
  the allowed-side self-join has nothing to join. A four-club, one-week frame is
  written into the loader's own `team_week` table to prove the join.
* `rosters` and `snap_counts` are not published by the fixture at all, so the
  roster endpoint would only ever be provably 503. Small real-shaped tables prove
  the pfr_id join, the SUM/SUM snap share, and that an unmatched player is left
  out of the ranking rather than sunk to the bottom of it.

`factories.py` is shared, so none of that was added there; see this package's
return notes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import sources
from app.etl import alignment
from app.repo import teams as repo
from app.routers import teams as teams_router

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
        getattr(route, "path", "").startswith("/api/teams") for route in main.app.routes
    )
    if not mounted:
        main.app.include_router(teams_router.router)
    return TestClient(main.app)


def _write_reciprocal_team_week(loader, season: int) -> None:
    """A four-club week where every club's opponent carries it back."""
    loader.ensure("team_week")
    cur = loader.cursor()
    columns = [
        "season", "week", "season_type", "team", "opponent_team",
        "passing_yards", "rushing_yards", "def_sacks", "def_interceptions",
        "passing_epa",
    ]
    present = {row[0] for row in cur.execute("DESCRIBE team_week").fetchall()}
    assert set(columns) <= present, sorted(set(columns) - present)
    cur.execute("DELETE FROM team_week WHERE season = ?", [season])
    rows = [
        (season, 1, "REG", "KC", "BUF", 300.0, 100.0, 3.0, 1.0, 5.0),
        (season, 1, "REG", "BUF", "KC", 200.0, 50.0, 2.0, 0.0, 1.0),
        (season, 1, "REG", "BAL", "CIN", 250.0, 80.0, 1.0, 2.0, 3.0),
        (season, 1, "REG", "CIN", "BAL", 150.0, 60.0, 4.0, 1.0, -2.0),
    ]
    cur.executemany(
        f"INSERT INTO team_week ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        rows,
    )


def _write_team_season(loader, season: int) -> None:
    """Season totals matching the hand-built week, so offence is predictable."""
    loader.ensure("team_season")
    cur = loader.cursor()
    columns = [
        "season", "season_type", "team", "passing_yards", "rushing_yards",
        "def_sacks", "def_interceptions", "passing_epa",
    ]
    cur.execute("DELETE FROM team_season WHERE season = ?", [season])
    cur.executemany(
        f"INSERT INTO team_season ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        [
            (season, "REG", "KC", 300.0, 100.0, 3.0, 1.0, 5.0),
            (season, "REG", "BUF", 200.0, 50.0, 2.0, 0.0, 1.0),
            (season, "REG", "BAL", 250.0, 80.0, 1.0, 2.0, 3.0),
            (season, "REG", "CIN", 150.0, 60.0, 4.0, 1.0, -2.0),
        ],
    )


def _write_roster_and_snaps(loader, season: int) -> None:
    """A three-man roster and two games of snaps, in the published column names.

    `Blocker` takes every offensive snap; `Rotational` takes half of them;
    `Unmatched` carries a pfr_id no snap-count row has, which is the case the
    roster endpoint has to refuse to score as zero.
    """
    cur = loader.cursor()
    cur.execute(
        """
        CREATE OR REPLACE TABLE rosters (
          season INTEGER, team VARCHAR, position VARCHAR,
          depth_chart_position VARCHAR, jersey_number INTEGER, status VARCHAR,
          full_name VARCHAR, gsis_id VARCHAR, pfr_id VARCHAR, birth_date DATE,
          height DOUBLE, weight DOUBLE, college VARCHAR, years_exp INTEGER,
          entry_year INTEGER, draft_club VARCHAR, draft_number INTEGER,
          headshot_url VARCHAR)
        """
    )
    cur.executemany(
        "INSERT INTO rosters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (season, "KC", "T", "LT", 71, "ACT", "Blocker", "00-0000001", "Blok01",
             "1996-03-01", 78.0, 315.0, "State University", 5, 2019, "KC", 33, None),
            (season, "KC", "WR", "WR", 15, "ACT", "Rotational", "00-0000002", "Rota02",
             "1998-05-04", 72.0, 195.0, "State University", 3, 2021, "KC", 90, None),
            (season, "KC", "CB", "CB", 24, "ACT", "Unmatched", "00-0000003", "Nope03",
             "1999-07-07", 71.0, 190.0, "State University", 1, 2023, "KC", None, None),
        ],
    )
    cur.execute(
        """
        CREATE OR REPLACE TABLE snap_counts (
          game_id VARCHAR, season INTEGER, week INTEGER, player VARCHAR,
          pfr_player_id VARCHAR, position VARCHAR, team VARCHAR, opponent VARCHAR,
          offense_snaps DOUBLE, offense_pct DOUBLE,
          defense_snaps DOUBLE, defense_pct DOUBLE,
          st_snaps DOUBLE, st_pct DOUBLE)
        """
    )
    cur.executemany(
        "INSERT INTO snap_counts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (f"{season}_01_BUF_KC", season, 1, "Blocker", "Blok01", "T", "KC", "BUF",
             60.0, 1.0, 0.0, 0.0, 4.0, 0.2),
            (f"{season}_01_BUF_KC", season, 1, "Rotational", "Rota02", "WR", "KC", "BUF",
             30.0, 0.5, 0.0, 0.0, 8.0, 0.4),
            (f"{season}_02_KC_BUF", season, 2, "Blocker", "Blok01", "T", "KC", "BUF",
             40.0, 1.0, 0.0, 0.0, 2.0, 0.1),
            (f"{season}_02_KC_BUF", season, 2, "Rotational", "Rota02", "WR", "KC", "BUF",
             10.0, 0.25, 0.0, 0.0, 6.0, 0.3),
        ],
    )


# --- the index: era-correct structure ----------------------------------------


@pytest.mark.parametrize(
    "season, expected_divisions, expected_teams", [(2001, 6, 31), (2024, 8, 32)]
)
def test_index_uses_the_seasons_own_alignment(
    built_loader, season, expected_divisions, expected_teams
):
    payload = repo.team_index(season, loader=built_loader)
    panels = [d for c in payload["conferences"] for d in c["divisions"]]
    assert len(panels) == expected_divisions
    assert payload["divisions"] == expected_divisions
    assert payload["teams"] == expected_teams
    assert sum(len(p["teams"]) for p in panels) == expected_teams
    # Pre-2002 division names are Central, not North/South.
    if season == 2001:
        assert {p["label"] for p in panels} == {
            "AFC East", "AFC Central", "AFC West",
            "NFC East", "NFC Central", "NFC West",
        }


def test_index_names_a_2001_card_by_what_it_was_called_then(built_loader):
    payload = repo.team_index(2001, loader=built_loader)
    cards = {
        card["abbr"]: card
        for conference in payload["conferences"]
        for division in conference["divisions"]
        for card in division["teams"]
    }
    rams = cards["LA"]
    assert rams["code_in_season"] == "STL"
    assert rams["name"] == "St. Louis Rams"
    assert rams["href"] == "/teams/LA/2001"
    assert rams["franchise_href"] == "/teams/LA"


def test_index_card_without_a_standings_row_carries_no_record(built_loader):
    payload = repo.team_index(2024, loader=built_loader)
    cards = {
        card["abbr"]: card
        for conference in payload["conferences"]
        for division in conference["divisions"]
        for card in division["teams"]
    }
    # DEN is in the 2024 alignment but plays no fixture game.
    assert cards["DEN"]["record"] is None
    assert cards["DEN"]["division_finish"] is None
    assert "DEN" in payload["note"]
    assert cards["KC"]["record"]["w"] == 2


def test_index_defaults_to_the_latest_completed_season(built_loader):
    payload = repo.team_index(loader=built_loader)
    assert payload["season"] == max(FIXTURE_SEASONS)
    assert payload["window"] == {
        "first_season": sources.FIRST_SEASON,
        "last_season": max(FIXTURE_SEASONS),
    }


def test_index_refuses_a_season_outside_the_window(built_loader):
    with pytest.raises(repo.SeasonOutOfWindow):
        repo.team_index(sources.FIRST_SEASON - 1, loader=built_loader)


# --- the franchise hub -------------------------------------------------------


def test_franchise_answers_to_a_historical_code(built_loader):
    by_old = repo.franchise("STL", loader=built_loader)
    by_new = repo.franchise("LA", loader=built_loader)
    assert by_old["team"]["abbr"] == "LA" == by_new["team"]["abbr"]
    assert "STL" in by_old["team"]["aliases"]
    assert [s["season"] for s in by_old["seasons"]] == [2024, 2001]


def test_franchise_year_by_year_prints_the_name_of_the_time(built_loader):
    payload = repo.franchise("LA", loader=built_loader)
    row_2001 = next(s for s in payload["seasons"] if s["season"] == 2001)
    assert row_2001["label"] == "St. Louis Rams"
    assert row_2001["code_in_season"] == "STL"
    assert row_2001["coach"] == "Coach STL"
    assert row_2001["href"] == "/teams/LA/2001"


def test_franchise_era_badge_reads_the_registry_not_a_literal(built_loader):
    payload = repo.franchise("KC", loader=built_loader)
    assert payload["era"]["seasons_from"] == sources.FIRST_SEASON
    assert payload["era"]["draft_from"] == sources.DRAFT_FIRST_SEASON


def test_franchise_leaders_carry_the_since_1999_label(built_loader):
    payload = repo.franchise("KC", loader=built_loader)
    leaders = payload["leaders"]
    assert leaders["since_1999"] is True
    assert leaders["first_season"] == sources.FIRST_SEASON
    board = leaders["categories"]["passing"][0]
    assert [row["rank"] for row in board["career"]] == list(
        range(1, len(board["career"]) + 1)
    )
    # Career totals pool a player's seasons; single-season rows do not.
    assert board["career"][0]["value"] >= board["single_season"][0]["value"]


def test_franchise_coaches_come_from_games_and_split_regular_from_postseason(
    built_loader,
):
    payload = repo.franchise("KC", loader=built_loader)
    coaches = {c["coach"]: c for c in payload["coaches"]}
    coach = coaches["Coach KC"]
    assert coach["seasons"] == [2001, 2024]
    assert coach["seasons_count"] == 2
    # The fixture's one postseason game per season is a Super Bowl KC wins, and it
    # lands in the playoff record rather than inflating the regular-season one.
    assert coach["playoff_w"] == 2 and coach["playoff_l"] == 0
    # Eight regular-season games scheduled, seven played: the unplayed 2024 week
    # four game is not a loss, and is not counted at all.
    assert coach["w"] + coach["l"] + coach["t"] == 7
    assert payload["coaches_note"]


def test_franchise_omits_the_draft_block_when_the_file_is_not_loaded(built_loader):
    payload = repo.franchise("KC", loader=built_loader)
    assert "draft" not in payload  # absent, not an empty list


def test_unknown_franchise_is_refused(built_loader):
    with pytest.raises(repo.UnknownTeam):
        repo.franchise("ZZZ", loader=built_loader)


# --- the team-season cockpit -------------------------------------------------


def test_team_season_is_absent_for_a_club_that_did_not_exist_yet(built_loader):
    assert repo.team_season("HOU", 2001, loader=built_loader) is None
    assert repo.team_season("HOU", 2024, loader=built_loader) is not None


def test_team_season_ranks_against_the_league_that_season(built_loader):
    payload = repo.team_season("LA", 2001, loader=built_loader)
    assert payload["label"] == "2001 St. Louis Rams"
    assert payload["team"]["code_in_season"] == "STL"
    for tile in payload["ratings"]:
        # 31 clubs in 2001, not 32 — and never a rank against clubs with no number.
        assert tile["league_teams"] == len(alignment.teams_in_season(2001)) == 31
        assert tile["of"] <= tile["league_teams"]
        assert tile["rank"] is None or tile["rank"] <= tile["of"]


def test_every_rating_tile_says_we_computed_it(built_loader):
    payload = repo.team_season("KC", 2024, loader=built_loader)
    tiles = {tile["id"]: tile for tile in payload["ratings"]}
    assert tiles["offense_epa_per_play"]["computed_by_us"] is True
    assert tiles["defense_epa_per_play"]["allowed_side"] is True
    assert all(tile["formula"] for tile in tiles.values())
    assert "def_" not in tiles["defense_epa_per_play"]["formula"] or (
        "never used as an allowed figure" in tiles["defense_epa_per_play"]["formula"]
    )


def test_epa_per_play_is_a_ratio_of_sums_not_an_average_of_rates(built_loader):
    payload = repo.team_season("KC", 2024, loader=built_loader)
    cur = built_loader.cursor()
    epa, plays = cur.execute(
        """
        SELECT sum(d.epa_total), sum(d.plays)
        FROM derived_game_team_stats d JOIN games g ON g.game_id = d.game_id
        WHERE d.season = 2024 AND d.team = 'KC' AND g.game_type = 'REG'
        """
    ).fetchone()
    tile = next(t for t in payload["ratings"] if t["id"] == "offense_epa_per_play")
    assert tile["value"] == pytest.approx(epa / plays, abs=1e-4)


def test_schedule_rows_carry_a_downsampled_sparkline_seen_from_this_club(
    built_loader,
):
    home = repo.team_season("KC", 2024, loader=built_loader)
    away = repo.team_season("BUF", 2024, loader=built_loader)
    home_row = next(r for r in home["schedule"] if r["game_id"] == "2024_01_BUF_KC")
    away_row = next(r for r in away["schedule"] if r["game_id"] == "2024_01_BUF_KC")

    assert home_row["home_away"] == "home" and away_row["home_away"] == "away"
    assert 0 < len(home_row["wp_sparkline"]) <= repo.WP_SPARKLINE_POINTS + 2
    assert home_row["wp_sparkline_side"] == "KC"
    stored = built_loader.cursor().execute(
        "SELECT count(*) FROM derived_wp_series WHERE game_id = '2024_01_BUF_KC'"
    ).fetchone()[0]
    assert len(home_row["wp_sparkline"]) <= stored
    # The away club's curve is the home club's, mirrored — not somebody else's game.
    for (h_secs, h_wp), (a_secs, a_wp) in zip(
        home_row["wp_sparkline"], away_row["wp_sparkline"]
    ):
        assert h_secs == a_secs
        assert h_wp + a_wp == pytest.approx(1.0, abs=1e-4)


def test_schedule_running_record_counts_only_the_regular_season(built_loader):
    payload = repo.team_season("KC", 2024, loader=built_loader)
    regular = [r for r in payload["schedule"] if r["game_type"] == "REG"]
    post = [r for r in payload["schedule"] if r["game_type"] != "REG"]
    assert regular[0]["running_record"] == "1-0-0"
    assert all(r["running_record"] is None for r in post)
    # The fixture's week-4 game is unplayed: no result, no record, no zero score.
    unplayed = [r for r in regular if r["result"] is None]
    assert unplayed and all(r["points_for"] is None for r in unplayed)
    assert all(r["running_record"] is None for r in unplayed)


def test_allowed_side_is_a_self_join_over_the_opponents_actually_faced(built_loader):
    _write_reciprocal_team_week(built_loader, 2024)
    _write_team_season(built_loader, 2024)
    payload = repo.team_season("KC", 2024, loader=built_loader)
    rows = {row["stat"]: row for row in payload["team_stats"]["rows"]}

    passing = rows["passing_yards"]
    assert passing["offense"] == 300.0
    assert passing["allowed"] == 200.0  # BUF's own offensive row, not KC's def_*
    assert passing["allowed_computed_by_us"] is True
    assert passing["allowed_source"] == "stats_team_week self-join over opponents"

    coverage = payload["team_stats"]["allowed_coverage"]
    assert coverage == {
        "team_weeks": 1,
        "opponent_rows_matched": 1,
        "complete": True,
        "note": "Every game this club played found its opponent's weekly row.",
    }
    assert payload["team_stats"]["computed_by_us"] == ["allowed"]


def test_no_def_column_is_ever_presented_as_an_allowed_figure(built_loader):
    _write_reciprocal_team_week(built_loader, 2024)
    _write_team_season(built_loader, 2024)
    payload = repo.team_season("KC", 2024, loader=built_loader)
    stats = {row["stat"] for row in payload["team_stats"]["rows"]}
    assert not any(stat.startswith("def_") for stat in stats)
    assert "def_* columns" in payload["allowed_side_method"]


def test_points_allowed_comes_from_the_scoreboard(built_loader):
    payload = repo.team_season("KC", 2024, loader=built_loader)
    points = next(r for r in payload["team_stats"]["rows"] if r["stat"] == "points")
    assert points["offense"] == payload["record"]["pf"]
    assert points["allowed"] == payload["record"]["pa"]
    assert points["allowed_source"] == "games.csv final scores"


def test_drive_profile_divides_counts_rather_than_averaging_rates(built_loader):
    payload = repo.team_season("KC", 2024, loader=built_loader)
    team = payload["drive_profile"]["team"]
    assert team["drives_per_game"] == pytest.approx(team["drives"] / team["games"])
    assert sum(team["result_mix"].values()) == team["drives"]
    assert payload["drive_profile"]["computed_by_us"] is True
    assert payload["drive_profile"]["opponent"]["drives"] > 0


def test_snap_and_injury_blocks_state_their_windows_instead_of_showing_zeros(
    built_loader,
):
    payload = repo.team_season("LA", 2001, loader=built_loader)
    assert payload["windows"]["snap_counts_from"] == sources.SNAP_COUNTS_FIRST_SEASON
    assert payload["windows"]["injuries_from"] == sources.INJURIES_FIRST_SEASON
    snaps = payload["roster_leaders"]["snap_share_coverage"]
    assert snaps["available"] is False
    assert str(sources.SNAP_COUNTS_FIRST_SEASON) in snaps["note"]
    assert "by_snap_share" not in payload["roster_leaders"]
    assert payload["injuries"]["coverage"]["available"] is False
    assert "rows" not in payload["injuries"]


def test_special_teams_names_the_block_it_cannot_build(built_loader):
    # The fixture's team file carries no kicking columns, so the block is absent
    # entirely rather than present and empty.
    payload = repo.team_season("KC", 2024, loader=built_loader)
    assert "special_teams" not in payload


# --- the roster --------------------------------------------------------------


def test_roster_is_unavailable_until_the_roster_file_is_loaded(built_loader):
    with pytest.raises(repo.SourceUnavailable):
        repo.team_roster("KC", 2024, loader=built_loader)


def test_roster_snap_share_is_sum_over_sum_and_unmatched_players_are_not_zero(
    built_loader,
):
    _write_roster_and_snaps(built_loader, 2024)
    payload = repo.team_roster("KC", 2024, loader=built_loader)
    rows = {row["name"]: row for row in payload["rows"]}

    # 60 + 40 of a team 60 + 40; 30 + 10 of the same denominator.
    assert rows["Blocker"]["offense_share"] == pytest.approx(1.0)
    assert rows["Rotational"]["offense_share"] == pytest.approx(40 / 100)
    assert rows["Blocker"]["snap_rank"] == 1
    assert rows["Rotational"]["snap_rank"] == 2

    unmatched = rows["Unmatched"]
    assert unmatched["offense_share"] is None
    assert unmatched["offense_snaps"] is None
    assert unmatched["snap_note"] and "not zero" in unmatched["snap_note"]
    assert "snap_rank" not in unmatched  # excluded from the ranking, not last in it
    assert payload["unmatched_snap_players"] == 1
    # Ranked players first; the unmatched one follows rather than sorting to zero.
    assert [row["name"] for row in payload["rows"]] == [
        "Blocker", "Rotational", "Unmatched"
    ]
    assert payload["coverage"]["snaps_available"] is True


def test_roster_omits_snap_columns_before_snap_counts_exist(built_loader):
    _write_roster_and_snaps(built_loader, 2001)
    built_loader.cursor().execute(
        "UPDATE rosters SET season = 2001 WHERE season = 2024"
    )
    payload = repo.team_roster("KC", 2001, loader=built_loader)
    assert payload["coverage"]["snaps_available"] is False
    assert str(sources.SNAP_COUNTS_FIRST_SEASON) in payload["coverage"]["note"]
    assert all("offense_share" not in row for row in payload["rows"])


def test_roster_position_groups_filter_and_are_counted(built_loader):
    _write_roster_and_snaps(built_loader, 2024)
    everyone = repo.team_roster("KC", 2024, loader=built_loader)
    assert everyone["counts"] == {
        "offense": 2, "defense": 1, "special_teams": 0, "unclassified": 0, "all": 3,
    }
    defense = repo.team_roster(
        "KC", 2024, position_group="defense", loader=built_loader
    )
    assert [row["name"] for row in defense["rows"]] == ["Unmatched"]
    # The counts describe the whole roster, not the filtered slice.
    assert defense["counts"]["all"] == 3


def test_roster_rejects_an_unknown_position_group(built_loader):
    _write_roster_and_snaps(built_loader, 2024)
    with pytest.raises(ValueError):
        repo.team_roster("KC", 2024, position_group="kickers", loader=built_loader)


def test_roster_age_is_taken_at_the_season_not_today(built_loader):
    _write_roster_and_snaps(built_loader, 2024)
    payload = repo.team_roster("KC", 2024, loader=built_loader)
    blocker = next(r for r in payload["rows"] if r["name"] == "Blocker")
    assert blocker["age"] == 28  # born 1996-03-01, measured at 2024-09-01
    assert blocker["age_computed_by_us"] is True


# --- the endpoints, on the real app ------------------------------------------


def test_endpoints_answer_on_the_application(built_loader):
    client = _client()

    index = client.get("/api/teams", params={"season": 2001})
    assert index.status_code == 200
    body = index.json()
    assert body["divisions"] == 6
    assert body["teams"] == 31

    franchise = client.get("/api/teams/STL")
    assert franchise.status_code == 200
    assert franchise.json()["team"]["abbr"] == "LA"

    season = client.get("/api/teams/STL/2001")
    assert season.status_code == 200
    assert season.json()["label"] == "2001 St. Louis Rams"


def test_endpoint_status_codes_are_honest(built_loader):
    client = _client()
    assert client.get("/api/teams/ZZZ").status_code == 404
    assert client.get("/api/teams/HOU/2001").status_code == 404
    assert client.get("/api/teams/KC/1998").status_code == 404

    roster = client.get("/api/teams/KC/2024/roster")
    assert roster.status_code == 503
    assert "not been loaded" in roster.json()["detail"]


def test_every_endpoint_declares_a_response_model(built_loader):
    paths = {
        route.path: route
        for route in teams_router.router.routes
        if getattr(route, "path", "").startswith("/api/teams")
    }
    assert len(paths) == 4
    for path, route in paths.items():
        assert route.response_model is not None, path


def test_a_relocated_franchise_uses_its_present_day_name(built_loader, monkeypatch):
    """`/teams/LA` is the Rams today, not the club they were in 2013.

    `teams_colors_logos.csv` ships the pre-relocation rows too — STL, SD, OAK —
    and they canonicalise onto the same franchise as LA, LAC and LV. Taking
    whichever the file lists last picks the old one, and the franchise page then
    introduces itself in the present tense under a name the club has not used
    for a decade. The historical name is still correct *with a season attached*,
    which is what `label_in_season` is for.
    """
    cur = built_loader.cursor()
    built_loader.ensure("teams_meta")
    # Both rows, in the order the real file lists them: current first, historical
    # second, so a last-write-wins merge would take the wrong one.
    cur.execute(
        """
        INSERT INTO teams_meta (team_abbr, team_name, team_nick, team_conf,
                                team_division, team_color, team_color2,
                                team_logo_espn, team_logo_squared, team_wordmark)
        VALUES ('LA', 'Los Angeles Rams', 'Rams', 'NFC', 'NFC West', '#003594',
                '#FFA300', 'logo', 'sq', 'wm'),
               ('STL', 'St. Louis Rams', 'Rams', 'NFC', 'NFC West', '#003594',
                '#FFA300', 'logo', 'sq', 'wm')
        """
    )
    branding = repo._branding(built_loader)
    assert branding["LA"]["name"] == "Los Angeles Rams"
    assert "STL" not in branding
