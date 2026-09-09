"""API-level tests: CORS, the dataset endpoints' contract, and their error codes.

The dataset endpoints are the Finder's whole backend, so the tests that drive
them run against `built_loader` — the same small real database the store tests
use — through a `TestClient`. The CORS tests need no data and take none.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROD_ORIGIN = "https://nflfastr-explorer.onrender.com"

#: The fixture's weekly player table: 24 rows each for 2001 and 2024.
WEEKLY_ROWS = 48
OLD_SEASON = 2001


def build_client(monkeypatch, tmp_path, env: dict[str, str], with_data: bool = False):
    for key in ("CORS_ORIGINS", "CORS_ORIGIN_REGEX", "DUCKDB_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "api.duckdb"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    from app import config, data_store, main

    importlib.reload(config)
    importlib.reload(main)

    if with_data:
        # A store of its own, so one test's column cache cannot answer for
        # another test's database. It reads whatever loader `deps` points at,
        # which under `built_loader` is the fixture one.
        main.store = data_store.DataStore()

    return main, TestClient(main.app)


# -- CORS --------------------------------------------------------------------


def test_production_origin_is_allowed_when_configured(monkeypatch, tmp_path):
    """The original bug: only localhost was allowed, so the live site broke."""
    _, client = build_client(monkeypatch, tmp_path, {"CORS_ORIGINS": PROD_ORIGIN})
    res = client.get("/api/health", headers={"Origin": PROD_ORIGIN})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == PROD_ORIGIN


def test_preflight_from_production_origin_is_allowed(monkeypatch, tmp_path):
    _, client = build_client(monkeypatch, tmp_path, {"CORS_ORIGINS": PROD_ORIGIN})
    res = client.options(
        "/api/datasets/player_weekly/query",
        headers={
            "Origin": PROD_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == PROD_ORIGIN


def test_localhost_stays_allowed_without_configuration(monkeypatch, tmp_path):
    _, client = build_client(monkeypatch, tmp_path, {})
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_origin_is_still_rejected(monkeypatch, tmp_path):
    _, client = build_client(monkeypatch, tmp_path, {"CORS_ORIGINS": PROD_ORIGIN})
    res = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in res.headers


def test_origin_regex_covers_preview_deploys(monkeypatch, tmp_path):
    _, client = build_client(
        monkeypatch,
        tmp_path,
        {"CORS_ORIGIN_REGEX": r"https://.*\.vercel\.app"},
    )
    origin = "https://nflfastr-explorer-git-main.vercel.app"
    res = client.get("/api/health", headers={"Origin": origin})
    assert res.headers["access-control-allow-origin"] == origin


def test_trailing_slash_in_configured_origin_is_tolerated(monkeypatch, tmp_path):
    _, client = build_client(monkeypatch, tmp_path, {"CORS_ORIGINS": PROD_ORIGIN + "/"})
    res = client.get("/api/health", headers={"Origin": PROD_ORIGIN})
    assert res.headers["access-control-allow-origin"] == PROD_ORIGIN


# -- the catalogue -----------------------------------------------------------


def test_dataset_listing_reports_the_real_window(monkeypatch, tmp_path, built_loader):
    """`/api/datasets` is where the Finder's coverage line comes from."""
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    client.get("/api/datasets/player_weekly/schema")  # the mode the visitor picked

    entry = {d["id"]: d for d in client.get("/api/datasets").json()}["player_weekly"]
    assert entry["row_count"] == WEEKLY_ROWS
    assert entry["season_min"] == OLD_SEASON
    assert entry["season_max"] == 2024


def test_schema_window_matches_the_rows_it_can_return(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    schema = client.get("/api/datasets/player_weekly/schema").json()
    assert (schema["season_min"], schema["season_max"]) == (OLD_SEASON, 2024)

    res = client.post(
        "/api/datasets/player_weekly/query",
        json={"filters": [{"field": "season", "operator": "eq", "value": OLD_SEASON}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] > 0
    assert {row["season"] for row in body["rows"]} == {OLD_SEASON}


# -- export ------------------------------------------------------------------


def test_export_is_capped_and_flags_truncation(monkeypatch, tmp_path, built_loader):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "10"}, with_data=True
    )
    res = client.post("/api/datasets/player_weekly/export", json={"format": "csv"})
    assert res.status_code == 200
    assert res.headers["x-export-truncated"] == "true"
    assert res.headers["x-export-rows"] == "10"
    assert res.headers["x-export-matching-rows"] == str(WEEKLY_ROWS)
    assert len([line for line in res.text.splitlines() if line]) == 11


def test_export_not_flagged_when_under_the_cap(monkeypatch, tmp_path, built_loader):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "1000"}, with_data=True
    )
    res = client.post("/api/datasets/player_weekly/export", json={"format": "csv"})
    assert res.headers["x-export-truncated"] == "false"
    assert res.headers["x-export-rows"] == str(WEEKLY_ROWS)


def test_client_max_rows_cannot_exceed_server_cap(monkeypatch, tmp_path, built_loader):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "10"}, with_data=True
    )
    res = client.post(
        "/api/datasets/player_weekly/export",
        json={"format": "csv", "max_rows": 1_000_000},
    )
    assert res.headers["x-export-rows"] == "10"


def test_export_rejects_bad_column_before_streaming(monkeypatch, tmp_path, built_loader):
    """A binder error must be a 400, not a truncated half-written download."""
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/export",
        json={"sort": [{"field": "nope; DROP TABLE player_week", "direction": "asc"}]},
    )
    assert res.status_code == 400


# -- error codes -------------------------------------------------------------


def test_unknown_dataset_is_404(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    assert client.get("/api/datasets/nope/schema").status_code == 404
    assert client.post("/api/datasets/nope/query", json={}).status_code == 404
    assert client.post("/api/datasets/nope/export", json={}).status_code == 404


def test_unknown_filter_field_is_400_not_500(monkeypatch, tmp_path, built_loader):
    """A stale filter naming a column the target table lacks must not 500.

    This is exactly what happened switching the frontend's player_season
    view from weekly granularity: the season table has no "week" column,
    and DuckDB's BinderException was propagating as an unhandled 500.
    """
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/query",
        json={"filters": [{"field": "not_a_real_column", "operator": "eq", "value": 1}]},
    )
    assert res.status_code == 400


def test_unknown_sort_field_is_400_not_500(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/query",
        json={"sort": [{"field": "not_a_real_column", "direction": "desc"}]},
    )
    assert res.status_code == 400


def test_unknown_field_in_data_quality_is_400(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/data-quality",
        json={"filters": [{"field": "not_a_real_column", "operator": "eq", "value": 1}]},
    )
    assert res.status_code == 400


def test_unknown_field_in_export_is_400(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/export",
        json={"filters": [{"field": "not_a_real_column", "operator": "eq", "value": 1}]},
    )
    assert res.status_code == 400


def test_unknown_field_in_filter_options_is_400(monkeypatch, tmp_path, built_loader):
    _, client = build_client(monkeypatch, tmp_path, {}, with_data=True)
    res = client.post(
        "/api/datasets/player_weekly/filter-options",
        json={"field": "team", "filters": [{"field": "not_a_real_column", "operator": "eq", "value": 1}]},
    )
    assert res.status_code == 400
