"""The Finder's backend: one generic query surface over tables the loader owns.

Every endpoint under `/api/datasets` — schema, query, filter options, data
quality, weekly breakdown, rankings, export — is served from here, and none of it
loads anything. Each dataset is a view onto a table the registry-driven loader
(`app/sources.py`, `app/loader.py`) already builds, canonicalised and season-
tracked; this module asks the shared loader for it and reads it.

It used to download its own copy of the same nflverse files into tables of its
own, four seasons deep, beside the loader's twenty-seven. That is how the Finder
came to print "2022-2025" on a site that covers 1999 onward: the one page whose
job is to answer what the fixed pages cannot was the page that could not see a
2003 season at all, and said nothing about it. Coverage is declared in the
registry once; what this file reports is measured off the rows.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Iterator

import duckdb

from . import sources
from .config import EXPORT_CHUNK_ROWS, EXPORT_MAX_ROWS
from .deps import get_loader
from .filter_config import (
    DEFAULT_PBP_COLUMNS,
    DEFAULT_PBP_SORT,
    DEFAULT_PLAYER_SEASON_COLUMNS,
    DEFAULT_PLAYER_SEASON_SORT,
    DEFAULT_PLAYER_WEEKLY_COLUMNS,
    DEFAULT_PLAYER_WEEKLY_SORT,
    PBP_FILTERS,
    PLAYER_SEASON_FILTERS,
    PLAYER_WEEKLY_FILTERS,
    categorize_column,
)
from .glossary import get_column_meta
from .models import (
    DataQualityResponse,
    DatasetMeta,
    ExportRequest,
    FilterCondition,
    FilterDef,
    FilterOptionsResponse,
    QueryRequest,
    QueryResponse,
    RankingsRequest,
    RankingsResponse,
    SortSpec,
    WeeklyBreakdownRequest,
    WeeklyBreakdownResponse,
)
from .query_builder import (
    build_null_count_sql,
    build_order,
    build_select_columns,
    build_where,
    quote_identifier,
)


@dataclass(frozen=True)
class DatasetConfig:
    """One Finder mode: a registry source, plus how the Finder presents it."""

    source_id: str
    name: str
    description: str
    source: str
    filters: list[FilterDef]
    default_columns: list[str]
    default_sort: list[SortSpec]

    @property
    def table(self) -> str:
        # Read from the registry rather than repeated here. A table name written
        # down in two places is a table that eventually disagrees with itself,
        # which is the exact shape of the bug this module used to be.
        return sources.get(self.source_id).table


DATASETS: dict[str, DatasetConfig] = {
    "player_weekly": DatasetConfig(
        source_id="player_week",
        name="Weekly Player Stats",
        description="Player game-week statistics from nflfastR calculate_stats(), ideal for game logs and weekly leaders.",
        source="nflverse stats_player (summary_level=week)",
        filters=PLAYER_WEEKLY_FILTERS,
        default_columns=DEFAULT_PLAYER_WEEKLY_COLUMNS,
        default_sort=DEFAULT_PLAYER_WEEKLY_SORT,
    ),
    "player_season": DatasetConfig(
        source_id="player_season_reg",
        name="Season Player Stats",
        description="Regular-season aggregated player statistics — season totals and rates.",
        source="nflverse stats_player (summary_level=reg)",
        filters=PLAYER_SEASON_FILTERS,
        default_columns=DEFAULT_PLAYER_SEASON_COLUMNS,
        default_sort=DEFAULT_PLAYER_SEASON_SORT,
    ),
    "play_by_play": DatasetConfig(
        source_id="pbp",
        name="Play Explorer",
        description="Individual play-by-play rows from nflfastR — filter down to specific situations, players, and outcomes.",
        # Play-by-play is the one table too large to hold whole: the loader keeps
        # the recent seasons resident and materialises older ones per season on
        # demand, which a whole-table query surface cannot reach. The window this
        # dataset reports is read off the resident table, so it says so itself.
        source="nflverse pbp (seasons held resident)",
        filters=PBP_FILTERS,
        default_columns=DEFAULT_PBP_COLUMNS,
        default_sort=DEFAULT_PBP_SORT,
    ),
}


class DataStore:
    """Query surface over the loader's tables.

    Two things matter for correctness here:

    * FastAPI runs sync endpoints in a threadpool, so several requests can be in
      this object at once. A DuckDB connection is not safe to share across
      threads, so every query runs on its own cursor (a separate connection to
      the same database) from the shared loader.
    * The per-table column list is read once and cached behind a lock, because
      every request needs it and `DESCRIBE` is a round trip.
    """

    def __init__(self) -> None:
        self._columns: dict[str, list[str]] = {}
        self._dtypes: dict[str, dict[str, str]] = {}
        self._state_lock = threading.Lock()

    # -- loading -----------------------------------------------------------

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        return get_loader().cursor()

    def _run(self, cur: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
        """Execute user-driven SQL, translating "no such column" into a 400.

        A filter, sort, or column list can reference a field that doesn't
        exist for the dataset being queried (e.g. a stale filter carried over
        after switching from weekly to season data, where the team column is
        named differently). DuckDB reports that as a BinderException, which
        FastAPI would otherwise surface as an unhandled 500 — turning it into
        a ValueError lets the existing `except ValueError -> 400` handling in
        main.py catch it like any other bad request.
        """
        try:
            return cur.execute(sql, params) if params is not None else cur.execute(sql)
        except duckdb.BinderException as exc:
            raise ValueError(f"Invalid field in request: {exc}") from exc

    def ensure_loaded(self, dataset_id: str) -> DatasetConfig:
        """Make sure this dataset's table exists and is current.

        Downloading, staging, freshness and per-season tracking all belong to the
        loader; this delegation is the whole of the Finder's loading code.
        """
        cfg = DATASETS[dataset_id]
        get_loader().ensure(cfg.source_id)

        with self._state_lock:
            if cfg.table in self._columns:
                return cfg

        info = self._cursor().execute(f"DESCRIBE {cfg.table}").fetchall()
        with self._state_lock:
            self._columns[cfg.table] = [row[0] for row in info]
            self._dtypes[cfg.table] = {row[0]: row[1] for row in info}
        return cfg

    def is_loaded(self, dataset_id: str) -> bool:
        return get_loader().table_exists(DATASETS[dataset_id].table)

    def _default_sort(
        self, cfg: DatasetConfig, columns: list[str]
    ) -> list[SortSpec]:
        """Drop default sorts naming columns this dataset doesn't have.

        Upstream nflverse schemas change between seasons; without this an
        absent column turns every query into a 500.
        """
        return [s for s in cfg.default_sort if s.field in columns]

    def _columns_for(self, table: str) -> list[str]:
        with self._state_lock:
            return list(self._columns[table])

    def _records(self, df) -> list[dict[str, Any]]:
        """Row dicts with nulls as JSON-safe `None`, never float `NaN`.

        `df.where(df.notna(), None)` looks like it does this, but pandas
        silently coerces `None` back to `NaN` when the target column is
        float-typed — so a NULL in any numeric column (a common case: a
        player with no snaps in a stat, or a week a player didn't play)
        would otherwise reach the client as a bare `NaN` token, which is not
        valid JSON and fails to parse in the browser.
        """
        records = df.to_dict(orient="records")
        for row in records:
            for key, value in row.items():
                if isinstance(value, float) and value != value:  # NaN != NaN
                    row[key] = None
        return records

    # -- metadata ----------------------------------------------------------

    def list_datasets(self) -> list[dict[str, Any]]:
        """The catalogue, reported from the tables as they actually are.

        Nothing here loads. A dataset whose table the loader has not built yet
        reports nulls rather than a window it cannot stand behind.
        """
        cur = self._cursor()
        out = []
        for ds_id, cfg in DATASETS.items():
            loaded = self.is_loaded(ds_id)
            first, last = self._season_window(cur, cfg.table) if loaded else (None, None)
            out.append(
                {
                    "id": ds_id,
                    "name": cfg.name,
                    "description": cfg.description,
                    "source": cfg.source,
                    "row_count": self._count(cur, cfg.table) if loaded else None,
                    "season_min": first,
                    "season_max": last,
                    "loaded": loaded,
                }
            )
        return out

    def _count(self, cur: duckdb.DuckDBPyConnection, table: str) -> int:
        return int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _season_window(
        self, cur: duckdb.DuckDBPyConnection, table: str
    ) -> tuple[int | None, int | None]:
        """The seasons this table actually holds — measured, never declared.

        The Finder prints this window verbatim under the mode selector, so it is
        read off the rows. A declared window is a claim; this is a fact, and the
        two used to differ by twenty-three seasons with only the claim on screen.
        """
        columns = {row[0] for row in cur.execute(f"DESCRIBE {table}").fetchall()}
        if "season" not in columns:
            return (None, None)
        row = cur.execute(f"SELECT min(season), max(season) FROM {table}").fetchone()
        if not row or row[0] is None:
            return (None, None)
        return (int(row[0]), int(row[1]))

    def get_schema(self, dataset_id: str) -> DatasetMeta:
        cfg = self.ensure_loaded(dataset_id)
        columns = self._columns_for(cfg.table)
        dtypes = self._dtypes[cfg.table]
        cur = self._cursor()

        column_meta = []
        for col in columns:
            meta = get_column_meta(col, dtypes[col])
            meta["category"] = categorize_column(col)
            column_meta.append(meta)

        available_filters = [
            f for f in cfg.filters if f.field in columns or f.type == "range"
        ]
        season_min, season_max = self._season_window(cur, cfg.table)

        return DatasetMeta(
            id=dataset_id,
            name=cfg.name,
            description=cfg.description,
            source=cfg.source,
            row_count=self._count(cur, cfg.table),
            season_min=season_min,
            season_max=season_max,
            columns=column_meta,
            filters=available_filters,
            default_columns=[c for c in cfg.default_columns if c in columns],
            default_sort=self._default_sort(cfg, columns),
        )

    # -- querying ----------------------------------------------------------

    def query(self, dataset_id: str, req: QueryRequest) -> QueryResponse:
        cfg = self.ensure_loaded(dataset_id)
        table = cfg.table
        columns = self._columns_for(table)
        cur = self._cursor()

        where_sql, params = build_where(req.filters)
        order_sql = build_order(req.sort or self._default_sort(cfg, columns))
        select_sql = build_select_columns(req.columns, columns)

        count_sql = f"SELECT COUNT(*) FROM {table}{where_sql}"
        total = int(self._run(cur, count_sql, params).fetchone()[0])

        offset = (req.page - 1) * req.page_size
        data_sql = (
            f"SELECT {select_sql} FROM {table}{where_sql}{order_sql} LIMIT ? OFFSET ?"
        )
        rows = self._run(cur, data_sql, params + [req.page_size, offset]).fetchdf()
        records = self._records(rows)

        return QueryResponse(
            rows=records,
            total=total,
            page=req.page,
            page_size=req.page_size,
            columns=list(rows.columns),
        )

    def ranked_query(self, dataset_id: str, req: RankingsRequest) -> RankingsResponse:
        """Like `query`, but every row also carries its rank on each requested
        stat, against one shared qualification rule for the whole request.

        A row's rank is "1 + how many qualifying rows beat it" — the standard
        rank definition, and one that happens to work identically whether the
        row itself qualifies or not: for a qualifying row it's its standing
        among the qualified cohort; for a non-qualifying row it's exactly the
        standing it *would* have if inserted into that cohort. No window
        function or join is needed for that — a row's rank never depends on
        any other non-qualifying row, so a correlated subquery against a
        small pre-filtered "qualified rows" CTE is enough, and avoids needing
        a join key that doesn't exist uniformly across every dataset here.
        """
        cfg = self.ensure_loaded(dataset_id)
        table = cfg.table
        columns = self._columns_for(table)
        cur = self._cursor()

        where_sql, where_params = build_where(req.filters)
        order_sql = build_order(req.sort or self._default_sort(cfg, columns))
        select_sql = build_select_columns(req.columns, columns)

        rank_fields = list(dict.fromkeys(f for f in req.rank_fields if f in columns))
        if not rank_fields:
            raise ValueError("rank_fields must reference real columns")

        qualify_field = req.qualify_field if req.qualify_field in columns else None
        use_qualify = qualify_field is not None and req.qualify_min is not None

        count_sql = f"SELECT COUNT(*) FROM {table}{where_sql}"
        total = int(self._run(cur, count_sql, where_params).fetchone()[0])

        if use_qualify:
            qf = quote_identifier(qualify_field)
            q_only_sql = f"SELECT * FROM filtered WHERE {qf} >= ?"
            qualifies_expr = f"({qf} >= ?)"
            extra_params: list[Any] = [req.qualify_min, req.qualify_min]
        else:
            q_only_sql = "SELECT * FROM filtered"
            qualifies_expr = "TRUE"
            extra_params = []

        rank_cols = [
            f'(SELECT COUNT(*) FROM q_only WHERE {quote_identifier(f)} > filtered.{quote_identifier(f)}) '
            f'+ 1 AS "__rank__{f}"'
            for f in rank_fields
        ]

        offset = (req.page - 1) * req.page_size
        data_sql = (
            f"WITH filtered AS (SELECT * FROM {table}{where_sql}), "
            f"q_only AS ({q_only_sql}) "
            f'SELECT {select_sql}, {qualifies_expr} AS "__qualifies", '
            f'(SELECT COUNT(*) FROM q_only) AS "__total_qualified", '
            f"{', '.join(rank_cols)} "
            f"FROM filtered{order_sql} LIMIT ? OFFSET ?"
        )
        params = where_params + extra_params + [req.page_size, offset]
        rows = self._run(cur, data_sql, params).fetchdf()
        records = self._records(rows)

        return RankingsResponse(
            rows=records,
            total=total,
            page=req.page,
            page_size=req.page_size,
            columns=list(rows.columns),
        )

    def filter_options(
        self,
        dataset_id: str,
        field: str,
        filters: list[FilterCondition],
        search: str | None = None,
        limit: int = 200,
    ) -> FilterOptionsResponse:
        cfg = self.ensure_loaded(dataset_id)
        table = cfg.table
        columns = self._columns_for(table)

        if field not in columns:
            return FilterOptionsResponse(field=field, options=[], total=0)

        cur = self._cursor()

        # Apply filters except those targeting the same field (so options stay broad)
        scoped = [f for f in filters if f.field != field]
        where_sql, params = build_where(scoped)

        if search:
            where_sql += (" AND " if where_sql else " WHERE ") + f'CAST("{field}" AS VARCHAR) ILIKE ?'
            params.append(f"%{search}%")

        count_sql = f'SELECT COUNT(DISTINCT "{field}") FROM {table}{where_sql}'
        total = int(self._run(cur, count_sql, params).fetchone()[0])

        options_sql = (
            f'SELECT DISTINCT "{field}" AS value FROM {table}{where_sql} '
            f"ORDER BY value NULLS LAST LIMIT ?"
        )
        result = self._run(cur, options_sql, params + [limit]).fetchall()
        options = [row[0] for row in result if row[0] is not None]

        return FilterOptionsResponse(field=field, options=options, total=total)

    def data_quality(
        self,
        dataset_id: str,
        filters: list[FilterCondition],
    ) -> DataQualityResponse:
        cfg = self.ensure_loaded(dataset_id)
        table = cfg.table
        columns = self._columns_for(table)
        cur = self._cursor()

        where_sql, params = build_where(filters)

        sql = build_null_count_sql(table, columns, where_sql)
        row = self._run(cur, sql, params).fetchone()

        filtered_count = int(row[0])
        total_count = self._count(cur, table)

        column_stats = []
        for idx, col in enumerate(columns, start=1):
            non_null = int(row[idx])
            null_count = filtered_count - non_null
            null_pct = (null_count / filtered_count * 100) if filtered_count > 0 else 0
            meta = get_column_meta(col, self._dtypes[table][col])
            column_stats.append(
                {
                    "id": col,
                    "label": meta["label"],
                    "null_pct": round(null_pct, 1),
                    "category": categorize_column(col),
                }
            )

        return DataQualityResponse(
            total_rows=total_count,
            filtered_rows=filtered_count,
            columns=column_stats,
        )

    def weekly_breakdown(
        self, dataset_id: str, req: WeeklyBreakdownRequest
    ) -> WeeklyBreakdownResponse:
        """One row per group (e.g. per player), one column per week for a
        chosen stat, and every other requested stat summed across the whole
        filtered range — the pivot behind the Players page's weekly view.
        """
        cfg = self.ensure_loaded(dataset_id)
        table = cfg.table
        columns = self._columns_for(table)
        cur = self._cursor()

        if "week" not in columns:
            raise ValueError("This dataset has no week column to break out")

        group_cols = [c for c in req.group_columns if c in columns]
        if not group_cols:
            raise ValueError("group_columns must reference real columns")
        if req.weekly_field not in columns:
            raise ValueError(f"Unknown weekly_field: {req.weekly_field}")
        agg_cols = [
            c
            for c in req.agg_columns
            if c in columns and c not in group_cols and c not in ("week", req.weekly_field)
        ]

        where_sql, params = build_where(req.filters)

        weeks_sql = f'SELECT DISTINCT "week" FROM {table}{where_sql} ORDER BY "week"'
        weeks = [int(row[0]) for row in self._run(cur, weeks_sql, params).fetchall() if row[0] is not None]
        if not weeks:
            return WeeklyBreakdownResponse(rows=[], weeks=[], total=0, page=req.page, page_size=req.page_size)

        group_sql = ", ".join(quote_identifier(c) for c in group_cols)
        weekly_field_q = quote_identifier(req.weekly_field)
        week_aliases = [f"week_{w}" for w in weeks]
        week_exprs = [
            f'SUM(CASE WHEN "week" = {w} THEN {weekly_field_q} END) AS "{alias}"'
            for w, alias in zip(weeks, week_aliases)
        ]
        agg_exprs = [f"SUM({quote_identifier(c)}) AS {quote_identifier(c)}" for c in agg_cols]
        select_sql = ", ".join([group_sql] + week_exprs + agg_exprs)

        valid_sort_fields = set(group_cols) | set(agg_cols) | set(week_aliases)
        sort = [s for s in req.sort if s.field in valid_sort_fields]
        order_sql = build_order(sort)

        count_sql = f"SELECT COUNT(*) FROM (SELECT {group_sql} FROM {table}{where_sql} GROUP BY {group_sql}) t"
        total = int(self._run(cur, count_sql, params).fetchone()[0])

        offset = (req.page - 1) * req.page_size
        data_sql = (
            f"SELECT {select_sql} FROM {table}{where_sql} GROUP BY {group_sql}{order_sql} LIMIT ? OFFSET ?"
        )
        rows = self._run(cur, data_sql, params + [req.page_size, offset]).fetchdf()
        records = self._records(rows)

        return WeeklyBreakdownResponse(
            rows=records, weeks=weeks, total=total, page=req.page, page_size=req.page_size,
        )

    # -- export ------------------------------------------------------------

    def export_row_count(self, dataset_id: str, req: ExportRequest) -> int:
        cfg = self.ensure_loaded(dataset_id)
        where_sql, params = build_where(req.filters)
        cur = self._cursor()
        sql = f"SELECT COUNT(*) FROM {cfg.table}{where_sql}"
        return int(self._run(cur, sql, params).fetchone()[0])

    def export_stream(
        self,
        dataset_id: str,
        req: ExportRequest,
        max_rows: int = EXPORT_MAX_ROWS,
    ) -> Iterator[str]:
        """Return the export as batches instead of building it all in memory.

        The SQL is built and executed eagerly so a bad column name surfaces as
        a 400 here, rather than mid-stream once the response has already begun.
        """
        cfg = self.ensure_loaded(dataset_id)
        columns = self._columns_for(cfg.table)

        where_sql, params = build_where(req.filters)
        order_sql = build_order(req.sort or self._default_sort(cfg, columns))
        select_sql = build_select_columns(req.columns, columns)

        cur = self._cursor()
        sql = f"SELECT {select_sql} FROM {cfg.table}{where_sql}{order_sql} LIMIT ?"
        self._run(cur, sql, params + [max_rows])

        if req.format == "json":
            return self._stream_json(cur)
        return self._stream_csv(cur)

    def _batches(self, cur: duckdb.DuckDBPyConnection):
        while True:
            batch = cur.fetchmany(EXPORT_CHUNK_ROWS)
            if not batch:
                return
            yield batch

    def _stream_csv(self, cur: duckdb.DuckDBPyConnection) -> Iterator[str]:
        import csv
        import io

        headers = [d[0] for d in cur.description]
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(headers)
        yield buf.getvalue()

        for batch in self._batches(cur):
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            for row in batch:
                writer.writerow(["" if v is None else v for v in row])
            yield buf.getvalue()

    def _stream_json(self, cur: duckdb.DuckDBPyConnection) -> Iterator[str]:
        headers = [d[0] for d in cur.description]
        yield "["
        first = True
        for batch in self._batches(cur):
            records = [
                json.dumps(dict(zip(headers, row)), default=str) for row in batch
            ]
            if records:
                yield ("" if first else ",") + ",".join(records)
                first = False
        yield "]"


store = DataStore()
