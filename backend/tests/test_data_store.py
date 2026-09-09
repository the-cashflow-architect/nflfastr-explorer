"""The Finder's query surface, over the tables the shared loader really builds.

Every test runs against `store` — a real `DataStore` on the real `built_loader`
database. The store has no loading code of its own to fake: it delegates to the
loader, so what is exercised here is what production runs.

The fixture database holds seasons 2001 and 2024 for the player tables, which
means these tests also stand as the regression on the bug this module was
written to fix — the Finder used to keep its own copy of the same files and
could not see a season before 2022 at all.
"""

from __future__ import annotations

import json
import threading

import pytest

from app import sources
from app.data_store import DATASETS
from app.models import (
    ExportRequest,
    FilterCondition,
    FilterOperator,
    QueryRequest,
    RankingsRequest,
    SortSpec,
    WeeklyBreakdownRequest,
)
from app.query_builder import build_null_count_sql

#: The fixture's player tables: 24 rows a season for 2001 and 2024, with the
#: unattributed row dropped from the weekly file at load.
WEEKLY_ROWS = 48
WEEKLY_ROWS_PER_SEASON = 24
OLD_SEASON = 2001


def loader_window(loader, source_id: str) -> tuple[int, int]:
    """The seasons the loader records having fetched, straight from its log."""
    seasons = [
        record.season
        for record in loader.load_records()
        if record.source_id == source_id and record.season is not None
    ]
    return min(seasons), max(seasons)


# -- what the Finder is pointed at -------------------------------------------


def test_datasets_read_the_registry_tables():
    """Each Finder mode is a view onto a registry source, not a private copy."""
    for dataset_id, cfg in DATASETS.items():
        source = sources.get(cfg.source_id)
        assert cfg.table == source.table, dataset_id


def test_reported_window_matches_what_the_loader_holds(store, built_loader):
    """The line the Finder prints must be what is on disk, for every mode.

    This is the drift check. The Finder said "2022-2025" for as long as it did
    because nothing compared the window it advertised against the seasons the
    loader had actually fetched, and the two lived in different files.
    """
    listing = {entry["id"]: entry for entry in store.list_datasets()}
    for dataset_id, cfg in DATASETS.items():
        schema = store.get_schema(dataset_id)
        first, last = loader_window(built_loader, cfg.source_id)
        assert (schema.season_min, schema.season_max) == (first, last), dataset_id

        entry = {e["id"]: e for e in store.list_datasets()}[dataset_id]
        assert (entry["season_min"], entry["season_max"]) == (first, last), dataset_id
        assert entry["row_count"] == schema.row_count, dataset_id

    # And the pre-load listing has to be about the same datasets.
    assert set(listing) == set(DATASETS)


def test_filters_and_sorts_name_real_columns(store):
    """A filter naming an absent column is a 400 the first time anyone uses it.

    The season and weekly files disagree about the team column's name
    (`recent_team` vs `team`), which is exactly the kind of difference that
    survives review and fails at query time, so it is pinned per dataset here
    rather than trusted.

    Default *columns* are not checked against the fixture: it deliberately omits
    some stat columns the real files carry, to exercise the missing-column paths
    elsewhere. They are presentation rather than client SQL, and `get_schema`
    intersects them with the table — which is what the next test holds.
    """
    for dataset_id, cfg in DATASETS.items():
        store.ensure_loaded(dataset_id)
        columns = set(store._columns_for(cfg.table))
        missing = [f.field for f in cfg.filters if f.field not in columns]
        assert missing == [], f"{dataset_id}: filters name missing columns {missing}"
        assert [s.field for s in cfg.default_sort if s.field not in columns] == [], dataset_id


def test_schema_offers_only_columns_the_table_has(store):
    """Whatever a mode offers as a default view has to be selectable."""
    for dataset_id in DATASETS:
        schema = store.get_schema(dataset_id)
        columns = {c.id for c in schema.columns}
        assert schema.default_columns, dataset_id
        assert set(schema.default_columns) <= columns, dataset_id
        assert {f.field for f in schema.filters if f.type != "range"} <= columns, dataset_id


def test_query_reaches_a_season_the_old_store_could_not(store):
    """2001 is inside the site's window and was outside the Finder's."""
    req = QueryRequest(
        filters=[FilterCondition(field="season", operator=FilterOperator.eq, value=OLD_SEASON)]
    )
    result = store.query("player_weekly", req)
    assert result.total == WEEKLY_ROWS_PER_SEASON
    assert all(row["season"] == OLD_SEASON for row in result.rows)


def test_list_datasets_reports_the_loaded_tables(store):
    """The catalogue counts rows in the table, and reports nothing before it exists."""
    before = {s["id"]: s for s in store.list_datasets()}
    assert before["player_weekly"]["loaded"] is False
    assert before["player_weekly"]["row_count"] is None
    assert before["player_weekly"]["season_min"] is None

    store.ensure_loaded("player_weekly")
    summaries = {s["id"]: s for s in store.list_datasets()}
    assert summaries["player_weekly"]["row_count"] == WEEKLY_ROWS
    assert summaries["player_weekly"]["loaded"] is True
    assert summaries["player_weekly"]["season_min"] == OLD_SEASON


# -- concurrency -------------------------------------------------------------


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
    assert totals == [WEEKLY_ROWS] * 8


# -- data quality ------------------------------------------------------------


def test_data_quality_null_percentages(store):
    result = store.data_quality("player_weekly", [])
    by_id = {c["id"]: c for c in result.columns}
    assert result.total_rows == WEEKLY_ROWS
    assert result.filtered_rows == WEEKLY_ROWS
    # Air-yards-dependent columns are NULL before 2006 (SPEC 0.2), which is
    # half of this fixture's rows.
    assert by_id["passing_cpoe"]["null_pct"] == 50.0
    assert by_id["passing_yards"]["null_pct"] == 0.0


def test_data_quality_respects_filters(store):
    filters = [
        FilterCondition(field="season", operator=FilterOperator.eq, value=OLD_SEASON)
    ]
    result = store.data_quality("player_weekly", filters)
    assert result.total_rows == WEEKLY_ROWS
    assert result.filtered_rows == WEEKLY_ROWS_PER_SEASON


def test_data_quality_sql_is_one_scan():
    """The old implementation ran one `WHERE col IS NULL` count per column."""
    sql = build_null_count_sql("player_week", ["a", "b", "c"], " WHERE x = ?")
    assert sql.count("FROM") == 1
    assert "IS NULL" not in sql
    assert sql == (
        'SELECT COUNT(*), COUNT("a"), COUNT("b"), COUNT("c") '
        "FROM player_week WHERE x = ?"
    )


def test_null_count_sql_rejects_bad_identifiers():
    with pytest.raises(ValueError):
        build_null_count_sql("t", ['a" OR 1=1 --'], "")


# -- schema, sort and injection ---------------------------------------------


def test_default_sort_drops_missing_columns(store):
    """An upstream column rename must not 500 every query."""
    schema = store.get_schema("player_weekly")
    available = {c.id for c in schema.columns}
    assert schema.default_sort  # something survived
    assert all(s.field in available for s in schema.default_sort)
    assert store.query("player_weekly", QueryRequest()).total == WEEKLY_ROWS


def test_query_rejects_injection_in_sort(store):
    store.ensure_loaded("player_weekly")
    req = QueryRequest(sort=[{"field": "season; DROP TABLE player_week", "direction": "asc"}])
    with pytest.raises(ValueError):
        store.query("player_weekly", req)


# -- export ------------------------------------------------------------------


def test_export_is_capped_and_streams(store):
    store.ensure_loaded("player_weekly")
    chunks = list(store.export_stream("player_weekly", ExportRequest(), max_rows=10))
    body = "".join(chunks)
    lines = [line for line in body.splitlines() if line]
    assert len(lines) == 11  # header + 10 rows
    assert len(chunks) > 1  # actually streamed, not one big string


def test_export_row_count_reports_pre_cap_total(store):
    store.ensure_loaded("player_weekly")
    assert store.export_row_count("player_weekly", ExportRequest()) == WEEKLY_ROWS


def test_export_json_is_valid(store):
    store.ensure_loaded("player_weekly")
    body = "".join(
        store.export_stream(
            "player_weekly", ExportRequest(format="json"), max_rows=7
        )
    )
    parsed = json.loads(body)
    assert len(parsed) == 7
    assert parsed[0]["season"] in (OLD_SEASON, 2024)


def test_export_rejects_unknown_sort_column(store):
    store.ensure_loaded("player_weekly")
    bad = ExportRequest(sort=[{"field": "not a column", "direction": "asc"}])
    with pytest.raises(ValueError):
        store.export_stream("player_weekly", bad)


# -- weekly breakdown --------------------------------------------------------


def test_weekly_breakdown_pivots_one_stat_by_week(store):
    req = WeeklyBreakdownRequest(
        filters=[FilterCondition(field="season", operator=FilterOperator.in_, value=[2024])],
        group_columns=["player_display_name"],
        weekly_field="passing_yards",
        # Requesting the weekly field again as an agg column should be a
        # no-op, not double-counted or summed as a flat total.
        agg_columns=["passing_yards"],
        sort=[SortSpec(field="player_display_name", direction="asc")],
        page=1,
        page_size=50,
    )
    resp = store.weekly_breakdown("player_weekly", req)

    assert resp.weeks == [1, 2, 3, 4]
    assert resp.total == 6  # the fixture cycles six players through four weeks
    row = resp.rows[0]
    for w in resp.weeks:
        assert f"week_{w}" in row
    assert "passing_yards" not in row
    # a week with no data for this player must come through as JSON-safe
    # None, never a bare NaN (which is not valid JSON).
    assert all(v is None or isinstance(v, (int, float)) for v in row.values() if v != row["player_display_name"])
    assert not any(isinstance(v, float) and v != v for v in row.values())


def test_weekly_breakdown_rejects_unknown_weekly_field(store):
    req = WeeklyBreakdownRequest(group_columns=["player_display_name"], weekly_field="not_a_real_column")
    with pytest.raises(ValueError):
        store.weekly_breakdown("player_weekly", req)


def test_weekly_breakdown_rejects_empty_group_columns(store):
    req = WeeklyBreakdownRequest(group_columns=["not_a_real_column"], weekly_field="passing_yards")
    with pytest.raises(ValueError):
        store.weekly_breakdown("player_weekly", req)


# -- rankings ----------------------------------------------------------------


def test_ranked_query_computes_rank_and_qualification(store):
    req = RankingsRequest(
        filters=[FilterCondition(field="season", operator=FilterOperator.in_, value=[2024])],
        columns=["player_display_name", "passing_yards"],
        sort=[SortSpec(field="passing_yards", direction="desc")],
        page=1,
        page_size=50,
        rank_fields=["passing_yards"],
        qualify_field="passing_yards",
        qualify_min=230,
    )
    resp = store.ranked_query("player_weekly", req)

    assert resp.total == WEEKLY_ROWS_PER_SEASON
    total_qualified = resp.rows[0]["__total_qualified"]
    assert total_qualified == sum(1 for r in resp.rows if r["passing_yards"] >= 230)
    assert 0 < total_qualified < resp.total  # the threshold has to actually split the field
    assert all(r["__total_qualified"] == total_qualified for r in resp.rows)

    qualified_values = sorted((r["passing_yards"] for r in resp.rows if r["__qualifies"]), reverse=True)
    for r in resp.rows:
        assert r["__qualifies"] == (r["passing_yards"] >= 230)
        expected_rank = sum(1 for v in qualified_values if v > r["passing_yards"]) + 1
        assert r["__rank__passing_yards"] == expected_rank


def test_ranked_query_without_qualification_ranks_everyone(store):
    req = RankingsRequest(
        filters=[FilterCondition(field="season", operator=FilterOperator.in_, value=[2024])],
        columns=["passing_yards"],
        page=1,
        page_size=50,
        rank_fields=["passing_yards"],
    )
    resp = store.ranked_query("player_weekly", req)

    assert all(r["__qualifies"] is True for r in resp.rows)
    assert all(r["__total_qualified"] == resp.total for r in resp.rows)
    best = max(r["passing_yards"] for r in resp.rows)
    assert next(r["__rank__passing_yards"] for r in resp.rows if r["passing_yards"] == best) == 1


def test_ranked_query_rejects_unknown_rank_field(store):
    req = RankingsRequest(rank_fields=["not_a_real_column"])
    with pytest.raises(ValueError):
        store.ranked_query("player_weekly", req)
