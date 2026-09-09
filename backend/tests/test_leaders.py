"""Tests for `app.repo.leaders` and the two `/api/leaders` endpoints.

`built_loader`'s league is eight clubs over two seasons — 2001 and 2024 — and its
player files are the weekly generator, so the loaded `player_season_reg` carries
roughly twenty of the ninety columns the real file has. That is not a limitation
here, it is the point: most of what this module has to get right is what happens when
a column is *not* there, and the fixture has whole categories missing (no kicking, no
returns, no defensive columns) alongside categories that are complete.

Two facts of the fixture the assertions below lean on:

* 2001 has four played weeks and 2024 three (its week 4 is unplayed), so the two
  seasons have different team-game counts and a qualification threshold that is one
  number for both would be visibly wrong.
* `passing_cpoe` is NULL for 2001 and populated for 2024, which is the real charting
  boundary in miniature.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import sources
from app.repo import leaders as repo
from app.routers import leaders as leaders_router

FIXTURE_SEASONS = (2001, 2024)

#: The claim this product may never make. Our floor is 1999 and a leaderboard that
#: implied a century of coverage would be the single most damaging screenshot the
#: site could produce, so it is asserted against the payloads *and* the source.
FORBIDDEN = re.compile(r"all[\s\-_]?time", re.IGNORECASE)


# --- helpers -------------------------------------------------------------------


def _client() -> TestClient:
    """The real application, with this package's router mounted.

    `routers/__init__.py::ALL_ROUTERS` is shared across packages and this one does
    not own it, so the router is mounted here rather than there — but on
    `app.main.app`, so the wiring under test is the real app's.
    """
    from app import main

    mounted = any(
        getattr(route, "path", "").startswith("/api/leaders") for route in main.app.routes
    )
    if not mounted:
        main.app.include_router(leaders_router.router)
    return TestClient(main.app)


def _load_box(loader) -> None:
    loader.ensure("games")
    loader.ensure("players")
    loader.ensure("player_season_reg")
    loader.ensure("player_week")


def _strings(payload: Any) -> list[str]:
    """Every string anywhere in a payload, for the claims we check across all of it."""
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        return [s for value in payload.values() for s in _strings(value)]
    if isinstance(payload, (list, tuple)):
        return [s for item in payload for s in _strings(item)]
    return []


def _hub_stat(index: dict, category: str, stat: str) -> dict | None:
    for block in index["categories"]:
        if block["id"] != category:
            continue
        for entry in block["stats"]:
            if entry["id"] == stat:
                return entry
    return None


# --- the hub ---------------------------------------------------------------------


def test_hub_lists_only_the_boards_this_deployment_can_build(built_loader):
    _load_box(built_loader)
    index = repo.leaders_index(loader=built_loader)

    available = {block["id"] for block in index["categories"]}
    assert {"passing", "rushing", "receiving", "scoring", "fantasy"} <= available

    # The fixture's player file has no kicking, return or defensive columns, so those
    # boards are named as unavailable rather than offered as boards of zeroes.
    unavailable = {(row["category"], row["stat"]) for row in index["unavailable"]}
    assert ("kicking", "fg_made") in unavailable
    assert ("defence", "def_sacks") in unavailable
    assert "kicking" not in available
    for entry in index["unavailable"]:
        assert "not in the data" in entry["reason"]


def test_every_board_on_the_hub_carries_a_window_and_a_scope(built_loader):
    _load_box(built_loader)
    index = repo.leaders_index(loader=built_loader)

    assert index["era"]["from"] == sources.FIRST_SEASON
    assert index["era"]["to"] == max(FIXTURE_SEASONS)

    for block in index["categories"]:
        for stat in block["stats"]:
            assert stat["era"]["from"] >= sources.FIRST_SEASON
            assert stat["era"]["note"]
            assert stat["scopes"], f"{stat['id']} is listed with no scope"
            assert stat["default_scope"] in stat["scopes"]
            assert stat["href"] == f"/leaders/{block['id']}/{stat['id']}"


def test_rate_boards_state_their_minimum(built_loader):
    _load_box(built_loader)
    index = repo.leaders_index(loader=built_loader)

    ypa = _hub_stat(index, "passing", "yards_per_attempt")
    assert ypa is not None
    assert "At least 14 pass attempts per team game" in ypa["qualification"]

    # A counting board has no minimum to state, and does not invent one.
    yards = _hub_stat(index, "passing", "passing_yards")
    assert yards is not None
    assert "qualification" not in yards


# --- windows ------------------------------------------------------------------------


def test_cpoe_and_epa_carry_two_different_windows(built_loader):
    _load_box(built_loader)
    index = repo.leaders_index(loader=built_loader)

    cpoe = _hub_stat(index, "advanced", "cpoe")
    assert cpoe is not None
    assert cpoe["era"]["from"] == sources.CHARTING_FIRST_SEASON
    assert str(sources.CHARTING_FIRST_SEASON) in cpoe["era"]["note"]

    # The EPA board reads the play-derived table, which the hub deliberately does
    # not build, so its window is read off the board itself.
    epa = repo.leaderboard("advanced", "epa_total", scope="career", loader=built_loader)
    assert epa["era"]["from"] == sources.FIRST_SEASON
    assert epa["era"]["from"] != cpoe["era"]["from"]

    # The two CPOE boards are separate boards with separate windows, never one board
    # that quietly changes meaning partway through.
    assert repo.find("advanced", "ngs_cpoe")[1].first_season == sources.NGS_FIRST_SEASON


def test_a_narrow_window_clamps_the_season_filter(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "advanced", "cpoe", scope="season", season_min=sources.FIRST_SEASON,
        loader=built_loader,
    )
    # Asking for 1999 on a board whose data starts in 2006 does not silently answer
    # for 1999: the filter comes back clamped to what the board can cover.
    assert board["filters"]["season_min"] == sources.CHARTING_FIRST_SEASON
    assert all(row["season"] >= sources.CHARTING_FIRST_SEASON for row in board["rows"])


def test_the_uncharted_season_is_absent_rather_than_zero(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("advanced", "cpoe", scope="season", loader=built_loader)
    seasons = {row["season"] for row in board["rows"]}
    assert seasons == {2024}, "2001 has no CPOE and must not appear with a zero"


def test_no_payload_claims_more_than_the_window_covers(built_loader):
    _load_box(built_loader)
    payloads = [
        repo.leaders_index(loader=built_loader),
        repo.leaderboard("passing", "passing_yards", scope="career", loader=built_loader),
        repo.leaderboard("passing", "yards_per_attempt", scope="season", loader=built_loader),
        repo.leaderboard("fantasy", "fantasy_points", scope="game", loader=built_loader),
    ]
    for payload in payloads:
        for text in _strings(payload):
            assert not FORBIDDEN.search(text), f"payload claims more than it has: {text!r}"


def test_the_source_never_writes_the_claim_either():
    """A payload test only catches the strings a test happened to reach."""
    root = Path(__file__).resolve().parents[1] / "app"
    for path in (root / "repo" / "leaders.py", root / "routers" / "leaders.py"):
        assert not FORBIDDEN.search(path.read_text()), f"{path} writes the claim"


# --- pooling ---------------------------------------------------------------------------


def test_career_rates_are_pooled_and_not_an_average_of_seasons(built_loader):
    _load_box(built_loader)
    cur = built_loader.cursor()
    # A second 2024 row for one player, with a volume unlike his 2001 one. Both
    # fixture seasons are otherwise identical, and two identical seasons cannot tell
    # a pooled rate from an averaged one — the bug this test exists to catch.
    cur.execute(
        """
        INSERT INTO player_season_reg (season, week, season_type, player_id,
            player_display_name, position, position_group, team, opponent_team,
            passing_yards, passing_tds, attempts, completions, games)
        VALUES (2024, 1, 'REG', '00-0000000', 'Player 0', 'QB', 'QB', 'KC', 'BUF',
                100, 0, 100, 10, 1)
        """
    )
    totals = cur.execute(
        """
        SELECT season, sum(passing_yards), sum(attempts)
        FROM player_season_reg
        WHERE player_id = '00-0000000' AND season_type = 'REG'
        GROUP BY season ORDER BY season
        """
    ).fetchall()
    pooled = sum(row[1] for row in totals) / sum(row[2] for row in totals)
    averaged = sum(row[1] / row[2] for row in totals) / len(totals)
    assert round(pooled, 2) != round(averaged, 2), "fixture no longer distinguishes the two"

    board = repo.leaderboard("passing", "yards_per_attempt", scope="career", loader=built_loader)
    row = next(r for r in board["rows"] if r["gsis_id"] == "00-0000000")
    assert row["value"] == round(pooled, 2)
    assert "pooled" in " ".join(_strings(board["rules"])).lower()


def test_pooled_cpoe_is_weighted_by_the_attempts_it_was_measured_over(built_loader):
    _load_box(built_loader)
    cur = built_loader.cursor()
    expected = cur.execute(
        """
        SELECT sum(passing_cpoe * attempts) / sum(CASE WHEN passing_cpoe IS NOT NULL
                                                       THEN attempts END)
        FROM player_season_reg
        WHERE player_id = '00-0000001' AND season_type = 'REG'
        """
    ).fetchone()[0]
    board = repo.leaderboard("advanced", "cpoe", scope="career", loader=built_loader)
    row = next(r for r in board["rows"] if r["gsis_id"] == "00-0000001")
    # The seasons with no CPOE contribute neither numerator nor denominator: their
    # attempts would otherwise drag every career that starts before charting toward
    # zero and present that as a measurement.
    assert row["value"] == round(expected, 2)


# --- qualification -----------------------------------------------------------------------


def test_the_threshold_is_stated_in_words_with_its_number(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("passing", "yards_per_attempt", scope="season", loader=built_loader)
    rule = board["qualification"]
    assert rule["applied"] is True
    assert "At least 14 pass attempts per team game" in rule["rule_text"]
    # 2001 played four weeks and 2024 three, so one number for both would be wrong at
    # one end: the sentence carries the spread and says why it moves.
    assert "56" in rule["rule_text"] and "42" in rule["rule_text"]
    assert "NFL" in rule["rule_text"]
    # And the numbers themselves, so the page does not have to parse the sentence.
    assert rule["thresholds_by_season"] == {"2001": 56.0, "2024": 42.0}


def test_a_career_threshold_is_one_seasons_worth_and_says_so(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("passing", "completion_pct", scope="career", loader=built_loader)
    rule = board["qualification"]
    assert rule["applied"] is True
    assert rule["threshold"] == pytest.approx(14.0 * 3)  # 2024 has three played weeks
    assert "one season's worth" in rule["rule_text"]


def test_a_single_game_threshold_is_one_team_game(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("passing", "yards_per_attempt", scope="game", loader=built_loader)
    assert board["qualification"]["threshold"] == pytest.approx(14.0)
    assert "in the game" in board["qualification"]["rule_text"]


def test_turning_the_minimum_off_still_states_the_rule(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "passing", "yards_per_attempt", scope="season", qualified=False, loader=built_loader
    )
    rule = board["qualification"]
    assert rule["applied"] is False
    assert "switched off" in rule["rule_text"]
    assert "14 pass attempts per team game" in rule["rule_text"]


def test_a_board_nobody_qualifies_for_is_empty_and_explains_itself(built_loader):
    _load_box(built_loader)
    # Eight-play fixture drives give nobody 42 dropbacks, which is exactly the
    # honest answer: the board exists, and this filter is what is empty.
    strict = repo.leaderboard("advanced", "epa_per_dropback", scope="career", loader=built_loader)
    assert strict["available"] is True
    assert strict["total"] == 0
    assert strict["rows"] == []
    assert "empty" in strict["note"]

    loose = repo.leaderboard(
        "advanced", "epa_per_dropback", scope="career", qualified=False, loader=built_loader
    )
    assert loose["total"] > 0
    assert "dropbacks" in loose["qualification"]["rule_text"]


# --- ranking ------------------------------------------------------------------------------


def test_ties_share_a_rank_and_the_row_says_how_many(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("passing", "passing_tds", scope="season", loader=built_loader)
    top = [row for row in board["rows"] if row["rank"] == 1]
    assert len(top) > 1
    for row in top:
        assert row["tied"] is True
        assert row["tied_count"] == len(top)
    # A shared rank consumes the ranks beneath it, the way a standings table does.
    following = min(row["rank"] for row in board["rows"] if row["rank"] > 1)
    assert following == len(top) + 1


def test_lower_is_better_boards_rank_the_other_way(built_loader):
    _load_box(built_loader)
    # The fixture's player file has no interceptions column, so the board is not
    # offered at all until there is one — which is also the shortest way to prove
    # that adding the column is all it takes.
    absent = repo.leaderboard("passing", "interception_pct", scope="season", loader=built_loader)
    assert absent["available"] is False

    cur = built_loader.cursor()
    cur.execute("ALTER TABLE player_season_reg ADD COLUMN passing_interceptions DOUBLE")
    cur.execute("UPDATE player_season_reg SET passing_interceptions = (attempts % 5)")
    board = repo.leaderboard("passing", "interception_pct", scope="season", loader=built_loader)
    assert board["available"] is True
    assert board["stat"]["higher_is_better"] is False
    values = [row["value"] for row in board["rows"]]
    assert values == sorted(values), "a rate where low is good must rank low first"
    assert board["rows"][0]["rank"] == 1


def test_paging_reports_the_whole_board_not_the_page(built_loader):
    _load_box(built_loader)
    first = repo.leaderboard(
        "passing", "passing_yards", scope="season", page=1, page_size=2, loader=built_loader
    )
    assert len(first["rows"]) == 2
    assert first["total"] > 2
    past_the_end = repo.leaderboard(
        "passing", "passing_yards", scope="season", page=99, page_size=2, loader=built_loader
    )
    assert past_the_end["rows"] == []
    assert past_the_end["total"] == first["total"]


# --- scopes and filters -----------------------------------------------------------------------


def test_the_single_game_scope_links_each_row_to_its_game(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("passing", "passing_yards", scope="game", loader=built_loader)
    assert board["rows"]
    linked = [row for row in board["rows"] if row.get("game_id")]
    assert linked, "no single-game row resolved to a game in the schedule"
    for row in linked:
        assert row["game_href"] == f"/games/{row['game_id']}"
        assert row["week"] is not None
        assert row["season"] in FIXTURE_SEASONS


def test_a_position_filter_narrows_the_board(built_loader):
    _load_box(built_loader)
    everyone = repo.leaderboard("passing", "passing_yards", scope="season", loader=built_loader)
    quarterbacks = repo.leaderboard(
        "passing", "passing_yards", scope="season", position="QB", loader=built_loader
    )
    assert 0 < quarterbacks["total"] < everyone["total"]
    assert all(row["position"] == "QB" for row in quarterbacks["rows"])


def test_a_team_filter_says_it_narrowed_the_career_total(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "passing", "passing_yards", scope="career", team="KC", loader=built_loader
    )
    assert board["filters"]["team"] == "KC"
    assert all(row["team"] == "KC" for row in board["rows"])
    assert "not his career total" in board["rules"]["team"]


def test_active_only_states_the_rule_it_applied(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "passing", "passing_yards", scope="career", active_only=True, loader=built_loader
    )
    assert board["filters"]["active_only"] is True
    assert "final season of 2024" in board["rules"]["active_only"]


def test_a_season_range_is_honoured(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "passing", "passing_yards", scope="season", season_min=2024, season_max=2024,
        loader=built_loader,
    )
    assert board["seasons_in_scope"] == [2024]
    assert {row["season"] for row in board["rows"]} == {2024}


# --- fantasy ----------------------------------------------------------------------------------


def test_the_three_scoring_formats_differ_by_the_receptions_term(built_loader):
    _load_box(built_loader)
    values = {}
    for scoring in ("standard", "half", "ppr"):
        board = repo.leaderboard(
            "fantasy", "fantasy_points", scope="season", scoring=scoring,
            season_min=2024, season_max=2024, loader=built_loader,
        )
        row = next(r for r in board["rows"] if r["gsis_id"] == "00-0000001")
        values[scoring] = row["value"]
        assert board["stat"]["scoring_format"] == scoring
        assert board["filters"]["scoring"] == scoring
    assert values["standard"] < values["half"] < values["ppr"]
    # Half PPR is exactly half the distance, which is the whole reason all three are
    # computed here rather than read: nflverse publishes no half-PPR column.
    assert values["half"] == pytest.approx((values["standard"] + values["ppr"]) / 2, abs=0.05)


def test_fantasy_names_the_components_it_could_not_find(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("fantasy", "fantasy_points", scope="season", loader=built_loader)
    stat = board["stat"]
    assert stat["computed_by_us"] is True
    assert "passing_yards" in stat["components_used"]
    # The fixture's file has no interception or fumble columns; the payload says so
    # rather than quietly scoring those components as zero.
    assert "interceptions" in stat["components_missing"]
    assert "not in the total" in stat["components_note"]


def test_fantasy_has_no_career_board_and_says_which_scopes_it_has(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("fantasy", "fantasy_points", scope="career", loader=built_loader)
    assert board["available"] is False
    assert "rows" not in board
    assert board["supported_scopes"] == ["season", "game"]


# --- absence ------------------------------------------------------------------------------------


def test_a_board_with_no_columns_is_absent_not_empty(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("kicking", "fg_made", scope="career", loader=built_loader)
    assert board["available"] is False
    assert "rows" not in board, "a missing board must not render as a board of nobody"
    assert "not in the data that has been loaded" in board["note"]
    # It still says what window it would have covered, so the page can explain itself.
    assert board["era"]["from"] == sources.FIRST_SEASON


def test_a_computed_board_names_the_columns_it_summed(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard("scoring", "touchdowns_accounted_for", scope="career", loader=built_loader)
    assert board["stat"]["computed_by_us"] is True
    assert board["stat"]["components_used"] == ["passing_tds"]
    assert "rushing_tds" in board["stat"]["components_missing"]


def test_unknown_boards_raise(built_loader):
    with pytest.raises(repo.UnknownBoard):
        repo.leaderboard("blitzing", "sacks", loader=built_loader)
    with pytest.raises(repo.UnknownBoard):
        repo.leaderboard("passing", "arm_strength", loader=built_loader)


# --- the endpoints --------------------------------------------------------------------------------


def test_the_hub_endpoint_answers_on_the_real_app(built_loader):
    _load_box(built_loader)
    response = _client().get("/api/leaders")
    assert response.status_code == 200
    body = response.json()
    assert body["era"]["from"] == sources.FIRST_SEASON
    assert body["categories"]
    for text in _strings(body):
        assert not FORBIDDEN.search(text)


def test_the_board_endpoint_answers_on_the_real_app(built_loader):
    _load_box(built_loader)
    response = _client().get(
        "/api/leaders/passing/passing_yards",
        params={"scope": "season", "page_size": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "season"
    assert len(body["rows"]) == 5
    assert body["qualification"]["rule_text"]
    assert body["era"]["from"] == sources.FIRST_SEASON
    assert body["rows"][0]["href"].startswith("/players/")


def test_an_unknown_board_is_a_404(built_loader):
    _load_box(built_loader)
    response = _client().get("/api/leaders/passing/arm_strength")
    assert response.status_code == 404


def test_an_unknown_scope_is_rejected(built_loader):
    _load_box(built_loader)
    response = _client().get("/api/leaders/passing/passing_yards", params={"scope": "decade"})
    assert response.status_code == 422


def test_only_the_career_line_carries_a_span_of_seasons(built_loader):
    _load_box(built_loader)
    career = repo.leaderboard("passing", "passing_yards", scope="career", loader=built_loader)
    assert career["rows"][0]["seasons"] == 2
    assert career["rows"][0]["first_season"] == 2001

    season = repo.leaderboard("passing", "passing_yards", scope="season", loader=built_loader)
    row = season["rows"][0]
    assert row["season"] in FIXTURE_SEASONS
    # A single season's row does not restate its own season three more times.
    assert "seasons" not in row and "first_season" not in row


def test_the_hub_never_starts_the_play_by_play_derivation(built_loader):
    """A grid of links must not be the request that reads twenty-seven seasons of
    plays. The hub reports what exists; the board that needs it builds it."""
    _load_box(built_loader)
    assert not built_loader.table_exists("derived_player_game_epa")

    index = repo.leaders_index(loader=built_loader)
    assert not built_loader.table_exists("derived_player_game_epa")
    unavailable = {(row["category"], row["stat"]) for row in index["unavailable"]}
    assert ("advanced", "epa_total") in unavailable

    repo.leaderboard("advanced", "epa_total", scope="career", loader=built_loader)
    assert built_loader.table_exists("derived_player_game_epa")

    after = repo.leaders_index(loader=built_loader)
    assert _hub_stat(after, "advanced", "epa_total") is not None


def test_a_success_rate_board_divides_successes_by_plays(built_loader):
    _load_box(built_loader)
    board = repo.leaderboard(
        "advanced", "success_rate_pass", scope="season", qualified=False,
        season_min=2024, season_max=2024, loader=built_loader,
    )
    row = board["rows"][0]
    expected = built_loader.cursor().execute(
        """
        SELECT 100.0 * sum(successes) / sum(plays)
        FROM derived_player_game_epa
        WHERE season = 2024 AND role = 'passer' AND gsis_id = ?
        """,
        [row["gsis_id"]],
    ).fetchone()[0]
    assert row["value"] == round(expected, 1)
    assert row["support"]["plays"] > 0


def test_the_ngs_board_reads_the_spelling_that_file_actually_uses(built_loader):
    """Next Gen Stats keys players on `player_gsis_id`, not `player_id`, and ships a
    season-total row at week 0 beside the weekly ones.

    The fixture does not model NGS — the real file is not reachable from a test — so
    the table is built here with the column names and the week-0 quirk the real one
    has. Without this the board would have looked available and answered with nobody
    on it, which is the one failure mode this module exists to prevent.
    """
    _load_box(built_loader)
    cur = built_loader.cursor()
    cur.execute(
        """
        CREATE TABLE ngs_passing AS
        SELECT 2016 + (i % 9) AS season, 'REG' AS season_type, (i % 4) + 1 AS week,
               '00-00' || lpad((i % 6)::VARCHAR, 5, '0') AS player_gsis_id,
               'Player ' || (i % 6) AS player_display_name,
               'QB' AS player_position, 'KC' AS team_abbr,
               (25 + i)::DOUBLE AS attempts,
               ((i % 11) - 5)::DOUBLE AS completion_percentage_above_expectation
        FROM range(36) t(i)
        UNION ALL
        -- The season-total row. Pooling the weeks and then adding this would count
        -- every attempt twice.
        SELECT 2016, 'REG', 0, '00-0000000', 'Player 0', 'QB', 'KC', 9999.0, 99.0
        """
    )
    board = repo.leaderboard(
        "advanced", "ngs_cpoe", scope="career", qualified=False, loader=built_loader
    )
    assert board["available"] is True
    assert board["rows"], "the NGS board resolved but ranked nobody"
    assert board["era"]["from"] == sources.NGS_FIRST_SEASON
    assert sources.NGS_FIRST_SEASON > sources.CHARTING_FIRST_SEASON

    expected = cur.execute(
        """
        SELECT sum(completion_percentage_above_expectation * attempts) / sum(attempts)
        FROM ngs_passing WHERE player_gsis_id = ? AND week > 0
        """,
        [board["rows"][0]["gsis_id"]],
    ).fetchone()[0]
    assert board["rows"][0]["value"] == round(expected, 2)
