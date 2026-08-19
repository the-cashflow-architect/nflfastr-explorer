"""API-level tests, including the CORS regression that broke production."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROD_ORIGIN = "https://nflfastr-explorer.onrender.com"


def build_client(monkeypatch, tmp_path, env: dict[str, str], store_factory=None):
    for key in ("CORS_ORIGINS", "CORS_ORIGIN_REGEX", "PRELOAD_ON_STARTUP", "DUCKDB_PATH"):
        monkeypatch.delenv(key, raising=False)
    # Preloading would hit the network; every test drives loading explicitly.
    monkeypatch.setenv("PRELOAD_ON_STARTUP", "false")
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "api.duckdb"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Only config and main are reloaded. Reloading app.data_store would swap
    # in a fresh DataStore class and drop the fixture's no-network patch.
    from app import config, main

    importlib.reload(config)
    importlib.reload(main)

    if store_factory is not None:
        main.store = store_factory()

    return main, TestClient(main.app)


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


def test_health_responds_without_loading_data(monkeypatch, tmp_path, store_factory):
    """Health must never block on a multi-minute nflverse download."""
    _, client = build_client(monkeypatch, tmp_path, {}, store_factory)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert store_factory.calls == {}


def test_dataset_listing_is_cheap(monkeypatch, tmp_path, store_factory):
    _, client = build_client(monkeypatch, tmp_path, {}, store_factory)
    res = client.get("/api/datasets")
    assert res.status_code == 200
    assert store_factory.calls == {}
    assert all(d["row_count"] is None for d in res.json())


def test_export_is_capped_and_flags_truncation(monkeypatch, tmp_path, store_factory):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "10"}, store_factory
    )
    res = client.post("/api/datasets/player_weekly/export", json={"format": "csv"})
    assert res.status_code == 200
    assert res.headers["x-export-truncated"] == "true"
    assert res.headers["x-export-rows"] == "10"
    assert res.headers["x-export-matching-rows"] == "60"
    assert len([line for line in res.text.splitlines() if line]) == 11


def test_export_not_flagged_when_under_the_cap(monkeypatch, tmp_path, store_factory):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "1000"}, store_factory
    )
    res = client.post("/api/datasets/player_weekly/export", json={"format": "csv"})
    assert res.headers["x-export-truncated"] == "false"
    assert res.headers["x-export-rows"] == "60"


def test_client_max_rows_cannot_exceed_server_cap(monkeypatch, tmp_path, store_factory):
    _, client = build_client(
        monkeypatch, tmp_path, {"EXPORT_MAX_ROWS": "10"}, store_factory
    )
    res = client.post(
        "/api/datasets/player_weekly/export",
        json={"format": "csv", "max_rows": 1_000_000},
    )
    assert res.headers["x-export-rows"] == "10"


def test_export_rejects_bad_column_before_streaming(monkeypatch, tmp_path, store_factory):
    """A binder error must be a 400, not a truncated half-written download."""
    _, client = build_client(monkeypatch, tmp_path, {}, store_factory)
    res = client.post(
        "/api/datasets/player_weekly/export",
        json={"sort": [{"field": "nope; DROP TABLE player_weekly", "direction": "asc"}]},
    )
    assert res.status_code == 400


def test_unknown_dataset_is_404(monkeypatch, tmp_path, store_factory):
    _, client = build_client(monkeypatch, tmp_path, {}, store_factory)
    assert client.get("/api/datasets/nope/schema").status_code == 404
    assert client.post("/api/datasets/nope/query", json={}).status_code == 404
    assert client.post("/api/datasets/nope/export", json={}).status_code == 404
