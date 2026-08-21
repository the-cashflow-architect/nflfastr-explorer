from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Any, Iterator

import duckdb
import requests

from .config import (
    DATA_MAX_AGE_HOURS,
    DOWNLOAD_TIMEOUT,
    DUCKDB_MEMORY_LIMIT,
    DUCKDB_THREADS,
    EXPORT_CHUNK_ROWS,
    EXPORT_MAX_ROWS,
    PBP_SEASONS,
    PLAYER_SEASONS,
    duckdb_path,
)
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

logger = logging.getLogger(__name__)

# nflreadpy's downloader buffers each file in memory, parses it into a polars
# frame, and hands back every column; we then copy that into DuckDB. That is
# three full copies of the data, and it cost ~518 MB for the weekly player
# table alone — enough to take down a small instance. These are the same
# nflverse release files, streamed to disk and read by DuckDB directly, which
# measures at roughly zero resident cost.
NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
PBP_URL = f"{NFLVERSE_RELEASE}/pbp/play_by_play_{{season}}.parquet"
PLAYER_WEEK_URL = f"{NFLVERSE_RELEASE}/stats_player/stats_player_week_{{season}}.parquet"
PLAYER_REG_URL = f"{NFLVERSE_RELEASE}/stats_player/stats_player_reg_{{season}}.parquet"

PBP_COLUMNS = [
    "season",
    "week",
    "game_id",
    "play_id",
    "season_type",
    "posteam",
    "defteam",
    "down",
    "ydstogo",
    "yardline_100",
    "qtr",
    "game_seconds_remaining",
    "score_differential",
    "play_type",
    "pass",
    "rush",
    "desc",
    "passer_player_name",
    "receiver_player_name",
    "rusher_player_name",
    "yards_gained",
    "air_yards",
    "yards_after_catch",
    "epa",
    "wp",
    "wpa",
    "cpoe",
    "touchdown",
    "pass_touchdown",
    "rush_touchdown",
    "interception",
    "complete_pass",
    "sack",
    "first_down",
]


@dataclass
class DatasetConfig:
    table: str
    name: str
    description: str
    source: str
    filters: list[FilterDef]
    default_columns: list[str]
    default_sort: list[SortSpec]
    url_template: str
    seasons: list[int]
    # Restrict to these columns when the source file is much wider than what
    # the app exposes. None keeps every column.
    columns: list[str] | None = None

    def urls(self) -> list[str]:
        return [self.url_template.format(season=s) for s in self.seasons]


DATASETS: dict[str, DatasetConfig] = {
    "player_weekly": DatasetConfig(
        table="player_weekly",
        name="Weekly Player Stats",
        description="Player game-week statistics from nflfastR calculate_stats(), ideal for game logs and weekly leaders.",
        source="nflverse stats_player (summary_level=week)",
        filters=PLAYER_WEEKLY_FILTERS,
        default_columns=DEFAULT_PLAYER_WEEKLY_COLUMNS,
        default_sort=DEFAULT_PLAYER_WEEKLY_SORT,
        url_template=PLAYER_WEEK_URL,
        seasons=PLAYER_SEASONS,
    ),
    "player_season": DatasetConfig(
        table="player_season",
        name="Season Player Stats",
        description="Regular-season aggregated player statistics — season totals and rates.",
        source="nflverse stats_player (summary_level=reg)",
        filters=PLAYER_SEASON_FILTERS,
        default_columns=DEFAULT_PLAYER_SEASON_COLUMNS,
        default_sort=DEFAULT_PLAYER_SEASON_SORT,
        url_template=PLAYER_REG_URL,
        seasons=PLAYER_SEASONS,
    ),
    "play_by_play": DatasetConfig(
        table="play_by_play",
        name="Play Explorer",
        description="Individual play-by-play rows from nflfastR — filter down to specific situations, players, and outcomes.",
        source="nflverse pbp (recent seasons)",
        filters=PBP_FILTERS,
        default_columns=DEFAULT_PBP_COLUMNS,
        default_sort=DEFAULT_PBP_SORT,
        url_template=PBP_URL,
        seasons=PBP_SEASONS,
        columns=PBP_COLUMNS,
    ),
}


class DataStore:
    """Disk-backed DuckDB store with lazy, per-dataset loading.

    Two things matter for correctness here:

    * FastAPI runs sync endpoints in a threadpool, so several requests can be
      in this object at once. A DuckDB connection is not safe to share across
      threads, so every query runs on its own ``conn.cursor()`` (a separate
      connection to the same database).
    * Loading is guarded by a per-dataset lock. Without it, two concurrent
      first requests both pass the "not loaded" check and the second
      ``CREATE TABLE`` fails.
    """

    LOAD_LOG = "_load_log"

    def __init__(self, path: str | None = None, max_age_hours: int | None = None) -> None:
        db_path = path or duckdb_path()
        self.conn = duckdb.connect(db_path)
        # Must be set before any bulk load: DuckDB's default limit is derived
        # from host RAM, which on a container is not the memory we actually
        # have. Spill to disk beside the database rather than failing.
        self.conn.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
        self.conn.execute(f"SET threads = {max(1, DUCKDB_THREADS)}")
        # Bulk loads buffer far less without it, and nothing here depends on
        # table row order — every query sorts explicitly.
        self.conn.execute("SET preserve_insertion_order = false")
        self.conn.execute(
            f"SET temp_directory = '{os.path.join(os.path.dirname(db_path) or '.', 'duckdb_tmp')}'"
        )
        self.max_age_hours = (
            DATA_MAX_AGE_HOURS if max_age_hours is None else max_age_hours
        )
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.LOAD_LOG} "
            "(table_name VARCHAR PRIMARY KEY, loaded_at TIMESTAMP)"
        )
        self._columns: dict[str, list[str]] = {}
        self._dtypes: dict[str, dict[str, str]] = {}
        self._locks: dict[str, threading.Lock] = {
            ds_id: threading.Lock() for ds_id in DATASETS
        }
        self._state_lock = threading.Lock()

    # -- loading -----------------------------------------------------------

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        return self.conn.cursor()

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

    def _table_exists(self, cur: duckdb.DuckDBPyConnection, table: str) -> bool:
        row = cur.execute(
            "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = ?", [table]
        ).fetchone()
        return bool(row and row[0])

    def ensure_loaded(self, dataset_id: str) -> DatasetConfig:
        """Make sure one dataset's table exists, downloading it if needed."""
        cfg = DATASETS[dataset_id]

        with self._state_lock:
            if cfg.table in self._columns:
                return cfg

        with self._locks[dataset_id]:
            # Re-check: another thread may have loaded it while we waited.
            with self._state_lock:
                if cfg.table in self._columns:
                    return cfg

            cur = self._cursor()
            exists = self._table_exists(cur, cfg.table)
            if exists and self._is_fresh(cur, cfg.table):
                # Left over from an earlier run — the whole point of the
                # persisted database file. No download needed.
                logger.info("Reusing persisted table %s", cfg.table)
            else:
                try:
                    # Build into a staging table first: a network failure must
                    # not destroy a stale-but-serviceable copy.
                    staging = f"{cfg.table}__staging"
                    cur.execute(f"DROP TABLE IF EXISTS {staging}")
                    self._create_table(cur, dataset_id, staging)
                except Exception:
                    cur.execute(f"DROP TABLE IF EXISTS {cfg.table}__staging")
                    if not exists:
                        raise
                    logger.exception(
                        "Refresh of %s failed; serving the cached copy", cfg.table
                    )
                else:
                    cur.execute(f"DROP TABLE IF EXISTS {cfg.table}")
                    cur.execute(f"ALTER TABLE {staging} RENAME TO {cfg.table}")
                    self._record_load(cur, cfg.table)
                    logger.info("Loaded %s", cfg.table)

            info = cur.execute(f"DESCRIBE {cfg.table}").fetchall()
            with self._state_lock:
                self._columns[cfg.table] = [row[0] for row in info]
                self._dtypes[cfg.table] = {row[0]: row[1] for row in info}

        return cfg

    def _is_fresh(self, cur: duckdb.DuckDBPyConnection, table: str) -> bool:
        """Is the persisted copy young enough to serve?

        Without an age check the database file would pin the app to whatever
        nflverse published the first time it ever ran.
        """
        if self.max_age_hours <= 0:
            return True
        row = cur.execute(
            f"SELECT loaded_at FROM {self.LOAD_LOG} WHERE table_name = ?", [table]
        ).fetchone()
        if not row or row[0] is None:
            return False
        age = cur.execute(
            "SELECT date_diff('hour', ?, now()::TIMESTAMP)", [row[0]]
        ).fetchone()[0]
        return int(age) < self.max_age_hours

    def _record_load(self, cur: duckdb.DuckDBPyConnection, table: str) -> None:
        cur.execute(f"DELETE FROM {self.LOAD_LOG} WHERE table_name = ?", [table])
        cur.execute(
            f"INSERT INTO {self.LOAD_LOG} VALUES (?, now()::TIMESTAMP)", [table]
        )

    def _create_table(
        self, cur: duckdb.DuckDBPyConnection, dataset_id: str, table: str
    ) -> None:
        """Materialise one dataset into `table` without buffering it in Python.

        Each season's parquet is streamed to disk in fixed-size chunks, then
        DuckDB reads the files directly. Column projection is pushed into the
        parquet reader, so a table like play-by-play never materialises the
        ~380 columns we don't expose.
        """
        cfg = DATASETS[dataset_id]
        logger.info("Downloading %s for seasons %s", dataset_id, cfg.seasons)

        paths: list[str] = []
        try:
            for url in cfg.urls():
                paths.append(self._download_parquet(url))

            select_sql = self._projection(cur, paths[0], cfg.columns)
            files = ", ".join(f"'{p}'" for p in paths)
            cur.execute(
                f"CREATE TABLE {table} AS "
                f"SELECT {select_sql} FROM read_parquet([{files}], union_by_name = true)"
            )
        finally:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _projection(
        self,
        cur: duckdb.DuckDBPyConnection,
        sample_path: str,
        columns: list[str] | None,
    ) -> str:
        """Build the SELECT list, keeping only columns the files really have."""
        if not columns:
            return "*"
        available = {
            row[0]
            for row in cur.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{sample_path}')"
            ).fetchall()
        }
        keep = [c for c in columns if c in available]
        if not keep:
            raise ValueError("source parquet has none of the expected columns")
        return ", ".join(f'"{c}"' for c in keep)

    def _download_parquet(self, url: str) -> str:
        """Stream a remote parquet to a temp file using constant memory."""
        fd, path = tempfile.mkstemp(suffix=".parquet")
        try:
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
                resp.raise_for_status()
                with os.fdopen(fd, "wb") as handle:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        if chunk:
                            handle.write(chunk)
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return path

    def preload(self) -> None:
        """Load every dataset, one at a time so peak memory stays low."""
        for dataset_id in DATASETS:
            try:
                self.ensure_loaded(dataset_id)
            except Exception:
                logger.exception("Preload failed for %s", dataset_id)

    def is_loaded(self, dataset_id: str) -> bool:
        with self._state_lock:
            return DATASETS[dataset_id].table in self._columns

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
        """Cheap listing: never triggers a download.

        ``row_count`` is null until the dataset has been loaded, so the
        catalogue renders immediately on a cold start.
        """
        cur = self._cursor()
        out = []
        for ds_id, cfg in DATASETS.items():
            loaded = self.is_loaded(ds_id)
            out.append(
                {
                    "id": ds_id,
                    "name": cfg.name,
                    "description": cfg.description,
                    "source": cfg.source,
                    "row_count": self._count(cur, cfg.table) if loaded else None,
                    "loaded": loaded,
                }
            )
        return out

    def _count(self, cur: duckdb.DuckDBPyConnection, table: str) -> int:
        return int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def get_schema(self, dataset_id: str) -> DatasetMeta:
        cfg = self.ensure_loaded(dataset_id)
        columns = self._columns_for(cfg.table)
        dtypes = self._dtypes[cfg.table]

        column_meta = []
        for col in columns:
            meta = get_column_meta(col, dtypes[col])
            meta["category"] = categorize_column(col)
            column_meta.append(meta)

        available_filters = [
            f for f in cfg.filters if f.field in columns or f.type == "range"
        ]

        return DatasetMeta(
            id=dataset_id,
            name=cfg.name,
            description=cfg.description,
            source=cfg.source,
            row_count=self._count(self._cursor(), cfg.table),
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
