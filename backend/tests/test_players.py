"""Tests for `app.repo.players`, `app.repo.percentiles` and the six player endpoints.

The fixture database models `players`, the three player stat files, `games` and
play-by-play. It deliberately does *not* model `draft_picks`, `combine`,
`snap_counts`, the NGS files, PFR advanced or ESPN QBR — those all 404 through
`conftest.fixture_file`. That is not a gap in these tests, it is the case they exist
to hold: a deployment where half the sources have not landed must still answer, with
the missing blocks *absent* from the payload rather than present and empty. Almost
every assertion below about a missing block is checking exactly that.

Two players are inserted directly into `players` by the tests that need them — one
offensive lineman with no season stat row, one defensive back — because
`factories.py` is shared and models neither. See this package's return notes.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app import main
from app.etl import buckets
from app.repo import percentiles as percentiles_repo
from app.repo import players as players_repo
from app.routers import players as players_router

#: The fixture's own seasons: one either side of both the 2002 realignment and the
#: 2006 air-yards charting boundary.
FIRST, LAST = 2001, 2024

#: `factories.write_players` emits six players, `00-0000000` through `00-0000005`.
QB = "00-0000000"
LINEMAN = "00-9999901"
DEFENDER = "00-9999902"


def _insert_player(loader: Any, gsis_id: str, name: str, position: str, group: str) -> None:
    """A player with a bio row and no season stat row — a quarter of every roster.

    Offensive linemen, long snappers and most special-teamers never appear in
    `stats_player_reg` at all (see the module docstring for why this is inserted
    here rather than added to the shared factory).
    """
    loader.ensure("players")
    cur = loader.cursor()
    cur.execute(
        """
        INSERT INTO players (gsis_id, display_name, first_name, last_name, position,
                             position_group, jersey_number, birth_date, height, weight,
                             headshot, college_name, college_conference, rookie_season,
                             last_season, latest_team, status, years_of_experience,
                             draft_year, draft_round, draft_pick, draft_team, pfr_id, espn_id)
        VALUES (?, ?, 'Test', 'Player', ?, ?, 70, DATE '1994-05-05', 78, 320,
                NULL, 'State University', 'Big Conference', 2016, 2024, 'KC', 'ACT', 8,
                NULL, NULL, NULL, NULL, NULL, NULL)
        """,
        [gsis_id, name, position, group],
    )


#: Mounted once per process. `routers/__init__.py::ALL_ROUTERS` is shared across
#: packages and this one does not own it, so the wiring happens here instead —
#: against the real `app.main.app`, not a bare `FastAPI()`, so a prefix collision
#: with another package's routes would show up as a failure here.
_MOUNTED = False


def _client() -> TestClient:
    global _MOUNTED
    if not _MOUNTED:
        main.app.include_router(players_router.router)
        _MOUNTED = True
    return TestClient(main.app)


# --- GET /api/players ------------------------------------------------------------


def test_index_pages_and_reports_its_total(built_loader):
    first = players_repo.player_index(page=1, page_size=2, loader=built_loader)
    second = players_repo.player_index(page=2, page_size=2, loader=built_loader)
    assert first["total"] == 6
    assert len(first["rows"]) == 2
    ids = {row["gsis_id"] for row in first["rows"]} | {row["gsis_id"] for row in second["rows"]}
    assert len(ids) == 4


def test_index_filters_by_name_position_and_college(built_loader):
    by_name = players_repo.player_index(q="Player 2", loader=built_loader)
    assert [row["display_name"] for row in by_name["rows"]] == ["Player 2"]

    by_position = players_repo.player_index(position="QB", loader=built_loader)
    assert by_position["rows"]
    assert all(row["position_group"] == "QB" for row in by_position["rows"])

    assert players_repo.player_index(college="State", loader=built_loader)["total"] == 6
    assert players_repo.player_index(college="Nowhere", loader=built_loader)["total"] == 0


def test_index_headline_is_the_position_groups_own_stat(built_loader):
    rows = {row["gsis_id"]: row for row in players_repo.player_index(loader=built_loader)["rows"]}
    assert rows[QB]["headline"]["id"] == "passing_yards"
    assert rows[QB]["headline"]["value"] > 0


def test_a_player_with_no_season_row_gets_a_blank_headline_and_a_reason(built_loader):
    """Never a zero. A lineman with no stat row has not gained zero yards."""
    _insert_player(built_loader, LINEMAN, "Test Lineman", "T", "OL")
    rows = {row["gsis_id"]: row for row in players_repo.player_index(loader=built_loader)["rows"]}
    headline = rows[LINEMAN]["headline"]
    assert headline["value"] is None
    assert headline["id"] is None
    # Snap counts are the position-appropriate headline and start in 2012; the note
    # has to say which of "no data for him" and "not loaded" is the case.
    assert str(percentiles_repo.sources.SNAP_COUNTS_FIRST_SEASON) in headline["note"]
    assert rows[LINEMAN]["games"] is None


def test_index_states_the_active_rule_rather_than_implying_one(built_loader):
    payload = players_repo.player_index(status="active", loader=built_loader)
    assert payload["total"] == 6
    assert str(LAST) in payload["rules"]["active"]
    assert players_repo.player_index(status="retired", loader=built_loader)["total"] == 0


def test_index_season_filter_uses_the_players_own_span(built_loader):
    # Every fixture player's rookie season is 2015 or later, so a 2001 filter must
    # find nobody even though the season stats file has 2001 rows for them.
    assert players_repo.player_index(season=FIRST, loader=built_loader)["total"] == 0
    assert players_repo.player_index(season=LAST, loader=built_loader)["total"] == 6


# --- GET /api/players/{gsis_id} --------------------------------------------------


def test_hub_identity_and_draft_line(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    assert hub["identity"]["display_name"] == "Player 0"
    assert hub["identity"]["slug"] == "player-0"
    assert hub["identity"]["status_label"] == "Active"
    # `draft_team` is a PFR code and is resolved by season, never mapped blindly.
    assert hub["draft"]["team"] == "KC"
    assert hub["draft"]["class_href"] == "/draft/2015"


def test_hub_multi_team_season_shows_per_team_rows_plus_a_combined_row(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    rows = hub["career_regular"]["rows"]
    season_rows = [r for r in rows if r["season"] == FIRST]
    combined = [r for r in season_rows if r["is_combined"]]
    per_team = [r for r in season_rows if not r["is_combined"]]
    assert len(combined) == 1
    assert len(per_team) > 1
    assert combined[0]["stats"]["passing_yards"] == sum(
        r["stats"]["passing_yards"] for r in per_team
    )
    assert combined[0]["team_label"] == f"{len(per_team)} teams"


def test_hub_career_total_equals_the_sum_of_the_combined_season_rows(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    table = hub["career_regular"]
    seasons = {}
    for row in table["rows"]:
        # One row per season carries that season's whole total: the combined row
        # where he changed teams, the single row where he did not.
        if row["is_combined"] or row["season"] not in seasons:
            seasons[row["season"]] = row
        if row["is_combined"]:
            seasons[row["season"]] = row
    assert table["total"]["stats"]["passing_yards"] == sum(
        row["stats"]["passing_yards"] for row in seasons.values()
    )
    assert table["total"]["seasons"] == len(seasons)


def test_hub_season_row_carries_the_code_the_club_played_under(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    rams = [
        row for row in hub["career_regular"]["rows"]
        if row["season"] == FIRST and row["team"] == "LA"
    ]
    assert rams and rams[0]["code_in_season"] == "STL"


def test_hub_cpoe_is_null_before_the_charting_boundary_never_zero(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    charting = percentiles_repo.sources.CHARTING_FIRST_SEASON
    assert FIRST < charting <= LAST
    early = [r for r in hub["career_regular"]["rows"] if r["season"] == FIRST]
    late = [r for r in hub["career_regular"]["rows"] if r["season"] == LAST]
    assert all(row["stats"]["passing_cpoe"] is None for row in early)
    assert any(row["stats"]["passing_cpoe"] is not None for row in late)


def test_hub_league_leading_cells_are_flagged_on_the_season_total(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    flagged = [row for row in hub["career_regular"]["rows"] if row["led_league"]]
    assert flagged, "the fixture's top passer should lead something"
    assert all(row["is_combined"] or True for row in flagged)
    assert "counting stats only" in hub["career_regular"]["leader_note"].lower()


def test_hub_omits_blocks_with_no_data_rather_than_emptying_them(built_loader):
    """draft_picks, combine, NGS and PFR advanced all 404 in this fixture."""
    hub = players_repo.player_hub(QB, loader=built_loader)
    assert "honors" not in hub
    coverage = {entry["source"]: entry for entry in hub["coverage"]}
    assert coverage["ngs_passing"]["available"] is False
    assert coverage["ngs_passing"]["note"]
    assert coverage["player_season_reg"]["first_season"] == FIRST
    assert coverage["player_season_reg"]["last_season"] == LAST


def test_hub_tiles_are_at_most_four_and_each_carries_a_context_line(built_loader):
    hub = players_repo.player_hub(QB, loader=built_loader)
    assert 1 <= len(hub["tiles"]) <= 4
    assert all(tile["context"] for tile in hub["tiles"])
    assert hub["tiles"][0]["id"] == "games"


def test_hub_for_a_player_with_no_stat_rows_drops_the_career_tables(built_loader):
    _insert_player(built_loader, LINEMAN, "Test Lineman", "T", "OL")
    hub = players_repo.player_hub(LINEMAN, loader=built_loader)
    assert "career_regular" not in hub
    assert "career_postseason" not in hub
    assert hub["available_tabs"]["splits"] is False
    assert "defensive or line" in hub["available_tabs"]["splits_note"]


def test_hub_is_none_for_an_unknown_id(built_loader):
    assert players_repo.player_hub("00-0000999", loader=built_loader) is None


# --- GET /api/players/{gsis_id}/percentiles ---------------------------------------


def test_percentiles_always_carry_their_cohort_and_qualification(built_loader):
    payload = percentiles_repo.player_percentiles(QB, loader=built_loader)
    assert payload["cohort"]["n"] >= 1
    assert payload["cohort"]["qualification"]
    assert payload["cohort"]["position_group"] == "QB"
    for metric in payload["metrics"]:
        assert metric["n"] >= 1
        assert metric["computed_by_us"] is True
        if metric["percentile"] is not None:
            assert 0.0 <= metric["percentile"] <= 100.0


def test_percentiles_scope_to_one_season_when_asked(built_loader):
    payload = percentiles_repo.player_percentiles(QB, season=LAST, loader=built_loader)
    assert payload["scope"] == "season"
    assert payload["season"] == LAST
    assert payload["cohort"]["season"] == LAST


def test_percentile_metric_carries_the_charting_window_it_depends_on(built_loader):
    payload = percentiles_repo.player_percentiles(QB, loader=built_loader)
    cpoe = [m for m in payload["metrics"] if m["id"] == "cpoe"]
    assert cpoe, "the fixture's QB metrics include CPOE"
    assert cpoe[0]["first_season"] == percentiles_repo.sources.CHARTING_FIRST_SEASON
    assert "not zero" in cpoe[0]["coverage_note"]


def test_percentiles_have_no_metrics_for_a_group_we_do_not_rank(built_loader):
    _insert_player(built_loader, LINEMAN, "Test Lineman", "T", "OL")
    payload = percentiles_repo.player_percentiles(LINEMAN, loader=built_loader)
    assert "metrics" not in payload
    assert "OL" in payload["note"]


def test_cohort_qualification_is_measured_against_real_team_games(built_loader):
    built_loader.ensure("games")
    built_loader.ensure("player_season_reg")
    played = percentiles_repo.team_games(built_loader, LAST)
    assert played and played > 0
    resolved = percentiles_repo.resolve_qualification(
        built_loader,
        "QB",
        percentiles_repo.table_columns(built_loader, percentiles_repo.SEASON_TABLE),
        season=LAST,
        seasons_in_scope=[LAST],
    )
    assert resolved.threshold == 14.0 * played
    assert "per team game" in resolved.words


# --- GET /api/players/{gsis_id}/gamelog -------------------------------------------


def test_gamelog_joins_the_schedule_and_the_derived_epa_table(built_loader):
    log = players_repo.player_gamelog(QB, loader=built_loader)
    assert log["rows"]
    row = log["rows"][0]
    assert row["game_id"] and row["game_href"] == f"/games/{row['game_id']}"
    assert row["result"] in {"W", "L", "T"}
    assert row["home_away"] in {"home", "away"}
    assert row["epa"] is not None and row["plays"]
    assert 0.0 <= row["success_rate"] <= 1.0


def test_gamelog_fantasy_points_are_computed_in_three_formats(built_loader):
    log = players_repo.player_gamelog(QB, season=LAST, loader=built_loader)
    row = log["rows"][0]
    receptions = row["stats"].get("receptions")
    assert row["fantasy_standard"] is not None
    assert row["fantasy_ppr"] >= row["fantasy_half"] >= row["fantasy_standard"]
    assert log["fantasy"]["computed_by_us"] is True
    assert log["fantasy"]["columns_used"]
    assert receptions is None or row["fantasy_ppr"] == row["fantasy_standard"] + receptions


def test_gamelog_started_is_labelled_a_proxy_and_null_without_snaps(built_loader):
    log = players_repo.player_gamelog(QB, loader=built_loader)
    assert "proxy" in log["started_proxy"]["rule"]
    assert log["started_proxy"]["computed_by_us"] is True
    # Snap counts do not load in this fixture: the flag is unknown, not False.
    assert all(row["started_proxy"] is None for row in log["rows"])
    assert all(row["offense_snaps"] is None for row in log["rows"])


def test_gamelog_scopes_to_one_season(built_loader):
    log = players_repo.player_gamelog(QB, season=FIRST, loader=built_loader)
    assert log["rows"]
    assert {row["season"] for row in log["rows"]} == {FIRST}
    assert log["games"] == len(log["rows"])
    assert log["splits_summary"]["games"] == log["games"]


# --- GET /api/players/{gsis_id}/splits --------------------------------------------


def test_splits_career_is_the_sum_of_its_seasons(built_loader):
    career = players_repo.player_splits(QB, loader=built_loader)
    per_season = [
        players_repo.player_splits(QB, season=season, loader=built_loader)
        for season in (FIRST, LAST)
    ]

    def plays(payload: dict, role: str, bucket: str) -> int:
        for entry in payload.get("situation", []):
            if entry["role"] != role:
                continue
            for row in entry["buckets"]:
                if row["bucket"] == bucket:
                    return row["plays"]
        return 0

    role = career["situation"][0]["role"]
    bucket = career["situation"][0]["buckets"][0]["bucket"]
    assert plays(career, role, bucket) == sum(plays(p, role, bucket) for p in per_season)
    assert plays(career, role, bucket) > 0


def test_splits_rates_are_pooled_from_the_summed_counts(built_loader):
    career = players_repo.player_splits(QB, loader=built_loader)
    row = career["situation"][0]["buckets"][0]
    assert row["epa_per_play"] == row["epa"] / row["plays"]
    assert 0.0 <= row["success_rate"] <= 1.0


def test_splits_flag_small_samples_with_their_n(built_loader):
    career = players_repo.player_splits(QB, loader=built_loader)
    for entry in career["situation"]:
        for row in entry["buckets"]:
            assert row["low_sample"] == (row["plays"] < players_repo.SMALL_SAMPLE_PLAYS)
            assert row["plays"] is not None


def test_splits_say_why_they_do_not_exist_for_a_defender(built_loader):
    _insert_player(built_loader, DEFENDER, "Test Corner", "CB", "DB")
    payload = players_repo.player_splits(DEFENDER, loader=built_loader)
    assert "situation" not in payload
    assert payload["unavailable"]["reason"]
    assert payload["unavailable"]["roles"] == [role.key for role in buckets.ROLES]
    assert "passer" in payload["unavailable"]["why"]


def test_splits_buckets_are_the_etls_own_sixteen(built_loader):
    career = players_repo.player_splits(QB, loader=built_loader)
    seen = {row["bucket"] for entry in career["situation"] for row in entry["buckets"]}
    assert seen <= set(buckets.BUCKET_KEYS)
    assert career["computed_by_us"] is True


# --- GET /api/players/{gsis_id}/advanced ------------------------------------------


def test_advanced_reports_a_window_per_source_and_no_empty_blocks(built_loader):
    payload = players_repo.player_advanced(QB, loader=built_loader)
    assert "ngs" not in payload
    assert "advstats" not in payload
    assert "qbr" not in payload
    sources_checked = {entry["source"] for entry in payload["coverage"]}
    assert {"ngs_passing", "advstats_pass", "qbr_season", "snap_counts"} <= sources_checked
    for entry in payload["coverage"]:
        assert entry["note"], "an unavailable source has to say why"
        assert entry["declared_first_season"] is not None


def test_advanced_windows_are_the_players_own_not_the_registrys(built_loader):
    """`player_week` stands in here for a source the player does appear in."""
    built_loader.ensure("players")
    built_loader.ensure("player_week")
    identity = players_repo._identity_row(built_loader, QB)
    window = players_repo._source_window(
        built_loader, "player_week", "gsis", ("player_id",), identity
    )
    assert window["declared_first_season"] == percentiles_repo.sources.FIRST_SEASON
    assert window["first_season"] == FIRST
    assert window["last_season"] == LAST
    assert window["rows"] > 0


# --- the HTTP surface --------------------------------------------------------------


def test_endpoints_answer_through_the_real_app(built_loader):
    client = _client()

    index = client.get("/api/players", params={"page_size": 3})
    assert index.status_code == 200
    assert index.json()["total"] == 6

    hub = client.get(f"/api/players/{QB}")
    assert hub.status_code == 200
    body = hub.json()
    assert body["identity"]["gsis_id"] == QB
    # The two halves of the honesty contract, over the wire and not just in the
    # dict: a block with no data is *absent*, while a value we looked for and did
    # not find is *present and null*. Serialisation must not collapse them.
    assert "honors" not in body
    early = [r for r in body["career_regular"]["rows"] if r["season"] == FIRST][0]
    assert "passing_cpoe" in early["stats"] and early["stats"]["passing_cpoe"] is None

    for suffix in ("percentiles", "gamelog", "splits", "advanced"):
        response = client.get(f"/api/players/{QB}/{suffix}")
        assert response.status_code == 200, suffix
        assert response.json()["gsis_id"] == QB


def test_unknown_player_is_a_404_on_every_player_endpoint(built_loader):
    client = _client()
    for path in (
        "/api/players/00-0000999",
        "/api/players/00-0000999/gamelog",
        "/api/players/00-0000999/splits",
        "/api/players/00-0000999/advanced",
    ):
        assert client.get(path).status_code == 404, path


def test_season_parameters_reject_nonsense(built_loader):
    client = _client()
    assert client.get(f"/api/players/{QB}/percentiles", params={"season": "soon"}).status_code == 422
    assert client.get(f"/api/players/{QB}/splits", params={"type": "sideways"}).status_code == 422
    assert client.get(f"/api/players/{QB}/percentiles", params={"season": "career"}).status_code == 200


# --- degraded and less-travelled paths ---------------------------------------------


def test_index_team_filter_matches_any_franchise_he_played_for(built_loader):
    payload = players_repo.player_index(team="LA", loader=built_loader)
    assert payload["total"] >= 1
    for row in payload["rows"]:
        assert row["latest_team"] == "LA" or "LA" in row["teams"]
    assert players_repo.player_index(team="ZZZ", loader=built_loader)["total"] == 0


def test_index_sorts_by_name_and_by_games(built_loader):
    by_name = players_repo.player_index(sort="name", loader=built_loader)["rows"]
    assert [r["display_name"] for r in by_name] == sorted(r["display_name"] for r in by_name)
    by_games = players_repo.player_index(sort="games", loader=built_loader)["rows"]
    played = [r["games"] for r in by_games if r["games"] is not None]
    assert played == sorted(played, reverse=True)


def test_index_still_answers_when_the_season_stats_table_is_missing(built_loader):
    """A fresh deployment mid-build has bios and no stats. It still has to answer."""
    players_repo.player_index(loader=built_loader)  # loads and records both sources
    built_loader.cursor().execute("DROP TABLE player_season_reg")
    payload = players_repo.player_index(loader=built_loader)
    assert payload["total"] == 6
    assert all(row["games"] is None for row in payload["rows"])
    assert all(row["headline"]["value"] is None for row in payload["rows"])
    assert all(row["headline"]["note"] for row in payload["rows"])
