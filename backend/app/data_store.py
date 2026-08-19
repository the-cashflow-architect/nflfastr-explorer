from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import duckdb
import nflreadpy as nfl
import polars as pl

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
    DatasetMeta,
    FilterCondition,
    FilterDef,
    FilterOptionsResponse,
    QueryRequest,
    QueryResponse,
    SortSpec,
)
from .query_builder import build_order, build_select_columns, build_where

logger = logging.getLogger(__name__)

DEFAULT_SEASONS = [2022, 2023, 2024, 2025]
PBP_SEASONS = [2024, 2025]

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


DATASETS: dict[str, DatasetConfig] = {
    "player_weekly": DatasetConfig(
        table="player_weekly",
        name="Weekly Player Stats",
        description="Player game-week statistics from nflfastR calculate_stats(), ideal for game logs and weekly leaders.",
        source="nflverse stats_player (summary_level=week)",
        filters=PLAYER_WEEKLY_FILTERS,
        default_columns=DEFAULT_PLAYER_WEEKLY_COLUMNS,
        default_sort=DEFAULT_PLAYER_WEEKLY_SORT,
    ),
    "player_season": DatasetConfig(
        table="player_season",
        name="Season Player Stats",
        description="Regular-season aggregated player statistics — season totals and rates.",
        source="nflverse stats_player (summary_level=reg)",
        filters=PLAYER_SEASON_FILTERS,
        default_columns=DEFAULT_PLAYER_SEASON_COLUMNS,
        default_sort=DEFAULT_PLAYER_SEASON_SORT,
    ),
    "play_by_play": DatasetConfig(
        table="play_by_play",
        name="Play Explorer",
        description="Individual play-by-play rows from nflfastR — filter down to specific situations, players, and outcomes.",
        source="nflverse pbp (recent seasons)",
        filters=PBP_FILTERS,
        default_columns=DEFAULT_PBP_COLUMNS,
        default_sort=DEFAULT_PBP_SORT,
    ),
}


class DataStore:
    def __init__(self) -> None:
        self.conn = duckdb.connect(":memory:")
        self._loaded = False
        self._columns: dict[str, list[str]] = {}
        self._dtypes: dict[str, dict[str, str]] = {}

    def load(self) -> None:
        if self._loaded:
            return

        logger.info("Loading player weekly stats for seasons %s", DEFAULT_SEASONS)
        weekly = nfl.load_player_stats(DEFAULT_SEASONS, summary_level="week")
        self._register_frame("player_weekly", weekly)

        logger.info("Loading player season stats for seasons %s", DEFAULT_SEASONS)
        season = nfl.load_player_stats(DEFAULT_SEASONS, summary_level="reg")
        self._register_frame("player_season", season)

        logger.info("Loading play-by-play for seasons %s", PBP_SEASONS)
        pbp = nfl.load_pbp(PBP_SEASONS)
        existing = [c for c in PBP_COLUMNS if c in pbp.columns]
        pbp = pbp.select(existing)
        self._register_frame("play_by_play", pbp)

        self._loaded = True
        logger.info("Data load complete")

    def _register_frame(self, table: str, frame: pl.DataFrame) -> None:
        self.conn.register("tmp_frame", frame.to_arrow())
        self.conn.execute(f"CREATE TABLE {table} AS SELECT * FROM tmp_frame")
        self.conn.unregister("tmp_frame")

        info = self.conn.execute(f"DESCRIBE {table}").fetchall()
        self._columns[table] = [row[0] for row in info]
        self._dtypes[table] = {row[0]: row[1] for row in info}

    def list_datasets(self) -> list[dict[str, Any]]:
        self.load()
        return [
            {
                "id": ds_id,
                "name": cfg.name,
                "description": cfg.description,
                "source": cfg.source,
                "row_count": self._count(cfg.table),
            }
            for ds_id, cfg in DATASETS.items()
        ]

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def get_schema(self, dataset_id: str) -> DatasetMeta:
        self.load()
        cfg = DATASETS[dataset_id]
        columns = self._columns[cfg.table]
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
            row_count=self._count(cfg.table),
            columns=column_meta,
            filters=available_filters,
            default_columns=[c for c in cfg.default_columns if c in columns],
            default_sort=cfg.default_sort,
        )

    def query(self, dataset_id: str, req: QueryRequest, export_all: bool = False):
        self.load()
        cfg = DATASETS[dataset_id]
        table = cfg.table
        columns = self._columns[table]

        where_sql, params = build_where(req.filters)
        order_sql = build_order(req.sort or cfg.default_sort)
        select_sql = build_select_columns(req.columns, columns)

        if export_all:
            data_sql = f"SELECT {select_sql} FROM {table}{where_sql}{order_sql}"
            df = self.conn.execute(data_sql, params).fetchdf()
            return df

        count_sql = f"SELECT COUNT(*) FROM {table}{where_sql}"
        total = int(self.conn.execute(count_sql, params).fetchone()[0])

        offset = (req.page - 1) * req.page_size
        data_sql = (
            f"SELECT {select_sql} FROM {table}{where_sql}{order_sql} "
            f"LIMIT ? OFFSET ?"
        )
        rows = self.conn.execute(data_sql, params + [req.page_size, offset]).fetchdf()
        records = rows.where(rows.notna(), None).to_dict(orient="records")

        output_cols = list(rows.columns)
        return QueryResponse(
            rows=records,
            total=total,
            page=req.page,
            page_size=req.page_size,
            columns=output_cols,
        )

    def filter_options(
        self,
        dataset_id: str,
        field: str,
        filters: list[FilterCondition],
        search: str | None = None,
        limit: int = 200,
    ) -> FilterOptionsResponse:
        self.load()
        cfg = DATASETS[dataset_id]
        table = cfg.table
        columns = self._columns[table]

        if field not in columns:
            return FilterOptionsResponse(field=field, options=[], total=0)

        # Apply filters except those targeting the same field (so options stay broad)
        scoped = [f for f in filters if f.field != field]
        where_sql, params = build_where(scoped)

        if search:
            where_sql += (" AND " if where_sql else " WHERE ") + f'CAST("{field}" AS VARCHAR) ILIKE ?'
            params.append(f"%{search}%")

        count_sql = f'SELECT COUNT(DISTINCT "{field}") FROM {table}{where_sql}'
        total = int(self.conn.execute(count_sql, params).fetchone()[0])

        options_sql = (
            f'SELECT DISTINCT "{field}" AS value FROM {table}{where_sql} '
            f'ORDER BY value NULLS LAST LIMIT ?'
        )
        result = self.conn.execute(options_sql, params + [limit]).fetchall()
        options = [row[0] for row in result if row[0] is not None]

        return FilterOptionsResponse(field=field, options=options, total=total)


    def data_quality(
        self,
        dataset_id: str,
        filters: list[FilterCondition],
    ) -> DataQualityResponse:
        self.load()
        cfg = DATASETS[dataset_id]
        table = cfg.table
        columns = self._columns[table]

        where_sql, params = build_where(filters)
        
        count_sql = f'SELECT COUNT(*) FROM {table}{where_sql}'
        filtered_count = int(self.conn.execute(count_sql, params).fetchone()[0])

        total_sql = f'SELECT COUNT(*) FROM {table}'
        total_count = int(self.conn.execute(total_sql).fetchone()[0])

        # Compute null percentages for numeric columns
        column_stats = []
        for col in columns:
            null_count_sql = f'SELECT COUNT(*) FROM {table}{where_sql} WHERE "{col}" IS NULL'
            null_count = int(self.conn.execute(null_count_sql, params).fetchone()[0])
            null_pct = (null_count / filtered_count * 100) if filtered_count > 0 else 0
            meta = get_column_meta(col, self._dtypes[table][col])
            column_stats.append({
                "id": col,
                "label": meta["label"],
                "null_pct": round(null_pct, 1),
                "category": categorize_column(col),
            })

        return DataQualityResponse(
            total_rows=total_count,
            filtered_rows=filtered_count,
            columns=column_stats,
        )


store = DataStore()
