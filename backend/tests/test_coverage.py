"""Tests for the honesty payload: `app.repo.coverage` and `GET /api/coverage`.

Two things this file has to prove beyond the usual behaviour: that the payload
tells the truth about what `built_loader`'s fixture actually holds (2001 and
2024, nothing else, for whatever we `ensure()`), and that a dataset nobody
asked to load is reported as missing rather than as a false zero. The
grep-for-year-literals test is the specific failure this whole endpoint exists
to prevent, so it is checked directly against the file, not just against its
output.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import sources
from app.repo import coverage as coverage_repo

COVERAGE_PY = Path(__file__).resolve().parents[1] / "app" / "repo" / "coverage.py"

# The two seasons `built_loader` actually generates fixture files for — one
# either side of the 2002 realignment and the 2006 charting boundary. Used
# only in assertions here, never in the module under test.
FIXTURE_FIRST, FIXTURE_LAST = 2001, 2024


def test_no_year_literals_in_coverage_repo():
    """Every coverage year in the payload must be read off `sources.py`.

    A four-digit number typed directly into this file is exactly the bug this
    endpoint exists to prevent — the day it disagrees with the registry is the
    day the site starts lying about its own coverage.
    """
    text = COVERAGE_PY.read_text()
    year_like = re.findall(r"\b(?:19|20)\d{2}\b", text)
    assert year_like == [], f"repo/coverage.py contains year literal(s): {year_like}"


def test_reports_the_actual_fixture_window_not_the_declared_one(built_loader):
    built_loader.ensure("games")
    built_loader.ensure("player_season_reg")
    built_loader.ensure("team_season")

    payload = coverage_repo.build_coverage(loader=built_loader)
    by_id = {row["id"]: row for row in payload["datasets"]}

    for dataset_id in ("games", "player_season_reg", "team_season"):
        row = by_id[dataset_id]
        assert row["season_min"] == FIXTURE_FIRST
        assert row["season_max"] == FIXTURE_LAST
        assert row["status"] == "loaded"
        assert row["row_count"] and row["row_count"] > 0
        assert row["loaded_at"] is not None

    # The declared window is open-ended (runs through whatever the latest
    # season is); the actual window is capped at what the fixture built. The
    # two must be allowed to differ, and this is the row that proves it.
    assert by_id["player_season_reg"]["declared_last_season"] is None
    assert by_id["player_season_reg"]["season_max"] == FIXTURE_LAST


def test_unloaded_dataset_is_missing_not_a_false_zero(built_loader):
    """A dataset nobody `ensure()`d yet must never look like it has zero rows.

    Zero rows and "we haven't loaded this" are different facts; collapsing
    them would make an un-built deployment look like a genuinely empty
    dataset instead of an incomplete one.
    """
    payload = coverage_repo.build_coverage(loader=built_loader)
    by_id = {row["id"]: row for row in payload["datasets"]}

    combine = by_id["combine"]
    assert combine["status"] == "unavailable"
    assert combine["row_count"] is None
    assert combine["season_min"] is None
    assert combine["season_max"] is None
    assert combine["loaded_at"] is None


def test_every_registered_source_appears_exactly_once(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    ids = [row["id"] for row in payload["datasets"]]
    assert ids == [source.id for source in sources.SOURCES]
    assert len(set(ids)) == len(ids)


def test_charting_boundary_is_sourced_from_the_registry(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    charting = payload["coverage_windows"]["charting"]
    assert charting["first_season"] == sources.CHARTING_FIRST_SEASON
    assert charting["first_season"] == 2006  # what the registry actually says today


def test_named_windows_all_trace_back_to_sources_constants(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    windows = payload["coverage_windows"]
    assert windows["stats"]["first_season"] == sources.FIRST_SEASON
    assert windows["next_gen_stats"]["first_season"] == sources.NGS_FIRST_SEASON
    assert windows["pfr_advanced"]["first_season"] == sources.ADVSTATS_FIRST_SEASON
    assert windows["snap_counts"]["first_season"] == sources.SNAP_COUNTS_FIRST_SEASON
    assert windows["injuries"]["first_season"] == sources.INJURIES_FIRST_SEASON
    assert windows["draft"]["first_season"] == sources.DRAFT_FIRST_SEASON
    for window in windows.values():
        assert window["note"]


def test_not_building_list_gives_a_reason_for_everything_it_names(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    not_building = payload["not_building"]
    assert len(not_building) >= 10
    for item in not_building:
        assert item["what"].strip()
        assert item["why"].strip()
    # Nothing about it may be an accident of this session's data window.
    assert coverage_repo.NOT_BUILDING == tuple(not_building)


def test_disk_usage_and_latest_completed_season(built_loader):
    built_loader.ensure("games")
    payload = coverage_repo.build_coverage(loader=built_loader)
    assert payload["disk_usage_bytes"] >= 0
    assert payload["latest_completed_season"] == FIXTURE_LAST


def test_latest_completed_season_is_none_before_games_loads(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    assert payload["latest_completed_season"] is None


def test_coverage_note_passes_through_from_the_registry(built_loader):
    payload = coverage_repo.build_coverage(loader=built_loader)
    by_id = {row["id"]: row for row in payload["datasets"]}
    # team_season's def_* caveat is the one every allowed-side computation on
    # the site depends on readers actually seeing.
    assert "def_" in by_id["team_season"]["coverage_note"]


# --- router / app wiring ------------------------------------------------------


def test_get_api_coverage_endpoint(built_loader):
    built_loader.ensure("games")

    from app import main

    client = TestClient(main.app)
    response = client.get("/api/coverage")

    assert response.status_code == 200
    body = response.json()
    assert {"datasets", "coverage_windows", "not_building", "generated_at"} <= body.keys()
    ids = {row["id"] for row in body["datasets"]}
    assert "games" in ids
    games_row = next(row for row in body["datasets"] if row["id"] == "games")
    assert games_row["season_max"] == FIXTURE_LAST


def test_existing_dataset_endpoints_are_unaffected(built_loader):
    """Mounting ALL_ROUTERS must never shadow the pre-existing dataset routes."""
    from app import main

    client = TestClient(main.app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/datasets").status_code == 200
