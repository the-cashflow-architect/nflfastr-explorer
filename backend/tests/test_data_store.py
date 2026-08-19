"""Regression tests for the loading, concurrency, and export fixes."""

from __future__ import annotations

import json
import threading

import pytest

from app.models import ExportRequest, FilterCondition, FilterOperator, QueryRequest
from app.query_builder import build_null_count_sql


def test_lazy_load_only_touches_requested_dataset(store, store_factory):
    store.ensure_loaded("player_weekly")
    assert store_factory.calls == {"player_weekly": 1}
    assert not store.is_loaded("player_season")


def test_list_datasets_never_triggers_a_download(store, store_factory):
    summaries = store.list_datasets()
    assert store_factory.calls == {}
    assert all(s["row_count"] is None and s["loaded"] is False for s in summaries)

    store.ensure_loaded("player_weekly")
    summaries = {s["id"]: s for s in store.list_datasets()}
    assert summaries["player_weekly"]["row_count"] == 60
    assert summaries["player_season"]["row_count"] is None


def test_concurrent_first_requests_load_exactly_once(store, store_factory):
    """Two threads racing into an unloaded dataset must not double-CREATE."""
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker():
        try:
            barrier.wait(timeout=10)
            store.ensure_loaded("player_weekly")
        except BaseException as exc:  # noqa: BLE001 - recorded and re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert store_factory.calls["player_weekly"] == 1


def test_concurrent_queries_do_not_share_a_connection(store):
    """Queries run on separate cursors, so parallel use must not blow up."""
    store.ensure_loaded("player_weekly")
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []
    totals: list[int] = []

    def worker(page: int):
        try:
            barrier.wait(timeout=10)
            res = store.query("player_weekly", QueryRequest(page=page, page_size=5))
            totals.append(res.total)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i + 1,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert totals == [60] * 8


def test_restart_reuses_persisted_tables(store_factory):
    """A crash-and-restart must not re-download every parquet file."""
    first = store_factory()
    first.ensure_loaded("player_weekly")
    assert store_factory.calls["player_weekly"] == 1

    second = store_factory()  # simulates a fresh process on the same volume
    second.ensure_loaded("player_weekly")
    assert store_factory.calls["player_weekly"] == 1
    assert second.query("player_weekly", QueryRequest()).total == 60


def test_data_quality_null_percentages(store):
    result = store.data_quality("player_weekly", [])
    by_id = {c["id"]: c for c in result.columns}
    assert result.total_rows == 60
    assert result.filtered_rows == 60
    assert by_id["cpoe"]["null_pct"] == 50.0
    assert by_id["passing_yards"]["null_pct"] == 0.0


def test_data_quality_respects_filters(store):
    filters = [
        FilterCondition(field="season", operator=FilterOperator.eq, value=2024)
    ]
    result = store.data_quality("player_weekly", filters)
    assert result.total_rows == 60
    assert result.filtered_rows == 30


def test_data_quality_sql_is_one_scan():
    """The old implementation ran one `WHERE col IS NULL` count per column."""
    sql = build_null_count_sql("player_weekly", ["a", "b", "c"], " WHERE x = ?")
    assert sql.count("FROM") == 1
    assert "IS NULL" not in sql
    assert sql == (
        'SELECT COUNT(*), COUNT("a"), COUNT("b"), COUNT("c") '
        "FROM player_weekly WHERE x = ?"
    )


def test_null_count_sql_rejects_bad_identifiers():
    with pytest.raises(ValueError):
        build_null_count_sql("t", ['a" OR 1=1 --'], "")


def test_default_sort_drops_missing_columns(store):
    """An upstream column rename must not 500 every query."""
    schema = store.get_schema("player_weekly")
    available = {c.id for c in schema.columns}
    assert schema.default_sort  # something survived
    assert all(s.field in available for s in schema.default_sort)
    # And a default query still works despite the config naming absent columns.
    assert store.query("player_weekly", QueryRequest()).total == 60


def test_export_is_capped_and_streams(store):
    store.ensure_loaded("player_weekly")
    chunks = list(store.export_stream("player_weekly", ExportRequest(), max_rows=10))
    body = "".join(chunks)
    lines = [line for line in body.splitlines() if line]
    assert len(lines) == 11  # header + 10 rows
    assert len(chunks) > 1  # actually streamed, not one big string


def test_export_row_count_reports_pre_cap_total(store):
    store.ensure_loaded("player_weekly")
    assert store.export_row_count("player_weekly", ExportRequest()) == 60


def test_export_json_is_valid(store):
    store.ensure_loaded("player_weekly")
    body = "".join(
        store.export_stream(
            "player_weekly", ExportRequest(format="json"), max_rows=7
        )
    )
    parsed = json.loads(body)
    assert len(parsed) == 7
    assert parsed[0]["season"] in (2024, 2025)


def test_export_rejects_unknown_sort_column(store):
    store.ensure_loaded("player_weekly")
    bad = ExportRequest(sort=[{"field": "not a column", "direction": "asc"}])
    with pytest.raises(ValueError):
        store.export_stream("player_weekly", bad)


def test_query_rejects_injection_in_sort(store):
    store.ensure_loaded("player_weekly")
    req = QueryRequest(sort=[{"field": "season; DROP TABLE player_weekly", "direction": "asc"}])
    with pytest.raises(ValueError):
        store.query("player_weekly", req)


def test_stale_persisted_table_is_refreshed(store_factory, monkeypatch):
    """A persisted file must not pin the app to a months-old nflverse copy."""
    import app.data_store as ds

    first = ds.DataStore(path=str(store_factory.db_path), max_age_hours=24)
    first.ensure_loaded("player_weekly")
    assert store_factory.calls["player_weekly"] == 1

    # Backdate the load stamp past the TTL.
    first.conn.execute(
        "UPDATE _load_log SET loaded_at = now()::TIMESTAMP - INTERVAL 48 HOUR "
        "WHERE table_name = 'player_weekly'"
    )

    second = ds.DataStore(path=str(store_factory.db_path), max_age_hours=24)
    second.ensure_loaded("player_weekly")
    assert store_factory.calls["player_weekly"] == 2
    assert second.query("player_weekly", QueryRequest()).total == 60


def test_ttl_of_zero_never_refreshes(store_factory):
    import app.data_store as ds

    first = ds.DataStore(path=str(store_factory.db_path), max_age_hours=0)
    first.ensure_loaded("player_weekly")
    second = ds.DataStore(path=str(store_factory.db_path), max_age_hours=0)
    second.ensure_loaded("player_weekly")
    assert store_factory.calls["player_weekly"] == 1


def test_failed_refresh_falls_back_to_cached_copy(store_factory, monkeypatch):
    """A flaky nflverse download must not delete the data we already have."""
    import app.data_store as ds

    first = ds.DataStore(path=str(store_factory.db_path), max_age_hours=24)
    first.ensure_loaded("player_weekly")
    first.conn.execute(
        "UPDATE _load_log SET loaded_at = now()::TIMESTAMP - INTERVAL 48 HOUR "
        "WHERE table_name = 'player_weekly'"
    )

    def boom(self, url):
        raise RuntimeError("nflverse unreachable")

    monkeypatch.setattr(ds.DataStore, "_download_parquet", boom)

    second = ds.DataStore(path=str(store_factory.db_path), max_age_hours=24)
    second.ensure_loaded("player_weekly")
    assert second.query("player_weekly", QueryRequest()).total == 60


def test_failed_first_load_propagates(store_factory, monkeypatch):
    """With nothing cached there is no fallback, so the error must surface."""
    import app.data_store as ds

    def boom(self, url):
        raise RuntimeError("nflverse unreachable")

    monkeypatch.setattr(ds.DataStore, "_download_parquet", boom)
    fresh = ds.DataStore(path=str(store_factory.db_path))
    with pytest.raises(RuntimeError):
        fresh.ensure_loaded("player_weekly")


def test_wide_source_columns_are_projected_away(store):
    """PBP's source has ~380 columns; only the configured ones may load.

    Loading every column is what exhausted the instance, so this pins the
    projection rather than trusting it.
    """
    schema = store.get_schema("play_by_play")
    loaded = {c.id for c in schema.columns}
    assert "a_column_we_never_select" not in loaded
    assert loaded <= set(ds_columns())


def ds_columns():
    import app.data_store as ds

    return ds.PBP_COLUMNS


def test_duckdb_memory_limit_is_pinned(store):
    """DuckDB defaults to a share of host RAM, which a container does not have."""
    cur = store._cursor()
    limit = cur.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert limit not in (None, "")
    # Must be well under a small instance; the default would be GB-scale.
    assert "GB" not in limit.upper() or float(limit.upper().split("GB")[0]) <= 1
    order = cur.execute(
        "SELECT current_setting('preserve_insertion_order')"
    ).fetchone()[0]
    assert order is False or str(order).lower() == "false"
