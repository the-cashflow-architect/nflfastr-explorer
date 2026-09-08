"""Getting nflverse files onto disk and into DuckDB, and keeping them current.

The loader owns the one DuckDB connection in the process. Everything else asks it
for a cursor. That is not a stylistic preference: DuckDB permits a single writing
process per database file, and opening a second connection to the same path from
the same process fails outright.

Three rules shape the design.

**A finished season is immutable.** 2014 will not change again, so it is fetched
once and never re-checked. Only the current season and the schedule file carry a
TTL. This is what makes 27 seasons cost less per day than the four the app used to
reload nightly.

**Nothing wide is ever held in Python.** Files are streamed to disk in fixed-size
chunks and read by DuckDB directly, with the column projection pushed into the
parquet reader. The 295 play-by-play columns we do not use are never decompressed.

**Play-by-play is not like the others.** Twenty-seven seasons of it is roughly
1.4 GB unprojected, and even projected it dwarfs everything else combined. Recent
seasons live in a permanent table; older ones are materialised on demand into
their own attached database file and evicted by deleting that file. `DROP TABLE`
would not do — DuckDB never returns freed pages to the operating system, so a
dropped table shrinks nothing.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import duckdb
import requests

from . import sources
from .config import (
    DOWNLOAD_RETRIES,
    DOWNLOAD_TIMEOUT,
    DUCKDB_BUILD_MEMORY_LIMIT,
    DUCKDB_MEMORY_LIMIT,
    DUCKDB_THREADS,
    PBP_CACHE_SEASONS,
    PBP_RESIDENT_SEASONS,
    data_dir,
    duckdb_path,
    latest_season,
)
from .etl.alignment import canonical_team_sql
from .sources import Source

logger = logging.getLogger(__name__)

# Distinct from the legacy `_load_log` the old three-dataset store writes: that
# table has a different shape, and `CREATE TABLE IF NOT EXISTS` would silently
# adopt it while the two coexist.
LOAD_LOG = "_source_log"


class SeasonBusy(RuntimeError):
    """Two seasons are already materialising and a third was asked for.

    Surfaced to the caller as a 503 with a plain-language message rather than
    queued, because queueing a third simultaneous download on a 512 MB instance is
    how the process gets killed.
    """


@dataclass(frozen=True)
class LoadRecord:
    source_id: str
    season: int | None
    loaded_at: datetime
    row_count: int


class Loader:
    """Owns the database connection, the download path, and the refresh policy."""

    def __init__(self, path: str | None = None, *, building: bool = False) -> None:
        self.db_path = path or duckdb_path()
        self.building = building
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = duckdb.connect(self.db_path)
        # Pinned before any bulk load. DuckDB sizes its buffer pool from *host*
        # RAM and cannot see a container's cgroup limit, so on a small instance it
        # over-allocates and gets OOM-killed. One thread, because more threads
        # means more concurrent buffers against the same small budget.
        # Building and serving have different appetites. Reading a page is cheap;
        # writing twenty-seven seasons into columnar storage is not, and squeezing
        # the build into the serving budget fails at commit time rather than
        # streaming. The build is a separate job, so it gets a separate number.
        self.conn.execute(
            f"SET memory_limit = '{DUCKDB_BUILD_MEMORY_LIMIT if building else DUCKDB_MEMORY_LIMIT}'"
        )
        self.conn.execute(f"SET threads = {max(1, DUCKDB_THREADS)}")
        self.conn.execute("SET preserve_insertion_order = false")
        self._tmp_dir = os.path.join(data_dir(), "duckdb_tmp")
        os.makedirs(self._tmp_dir, exist_ok=True)
        self.conn.execute(f"SET temp_directory = '{self._tmp_dir}'")
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {LOAD_LOG} ("
            "  source_id VARCHAR NOT NULL, season INTEGER, loaded_at TIMESTAMP,"
            "  row_count BIGINT)"
        )

        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._loaded: set[str] = set()
        # Attached play-by-play seasons, most recently used last.
        self._attached: OrderedDict[int, str] = OrderedDict()
        self._attach_guard = threading.Lock()
        self._season_locks: dict[int, threading.Lock] = {}

    # -- connection ---------------------------------------------------------

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """A private connection to the same database, safe to use on one thread.

        FastAPI runs sync endpoints in a threadpool, so several requests can be
        inside this object at once; a DuckDB connection is not shareable across
        threads, but a cursor is a cheap separate one onto the same database.
        """
        return self.conn.cursor()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    # -- freshness ----------------------------------------------------------

    def _record(self, cur, source_id: str, season: int | None, rows: int) -> None:
        cur.execute(
            f"DELETE FROM {LOAD_LOG} WHERE source_id = ? AND season IS NOT DISTINCT FROM ?",
            [source_id, season],
        )
        cur.execute(
            f"INSERT INTO {LOAD_LOG} VALUES (?, ?, ?, ?)",
            [source_id, season, datetime.now(timezone.utc).replace(tzinfo=None), rows],
        )

    def _loaded_at(self, cur, source_id: str, season: int | None) -> datetime | None:
        row = cur.execute(
            f"SELECT loaded_at FROM {LOAD_LOG} "
            "WHERE source_id = ? AND season IS NOT DISTINCT FROM ?",
            [source_id, season],
        ).fetchone()
        return row[0] if row else None

    def _is_current(self, source: Source, season: int | None) -> bool:
        """Could this file still change upstream?

        A season file stops changing once its postseason is over. We treat only
        the latest season as live, which errs one season on the safe side and
        costs one small download a day.
        """
        if source.grain == "season":
            return season is not None and season >= latest_season()
        return True

    def _needs_refresh(self, cur, source: Source, season: int | None) -> bool:
        loaded_at = self._loaded_at(cur, source.id, season)
        if loaded_at is None:
            return True
        if not self._is_current(source, season):
            return False  # Finished seasons are never re-fetched.
        if source.ttl_hours <= 0:
            return False
        age_hours = (
            datetime.now(timezone.utc).replace(tzinfo=None) - loaded_at
        ).total_seconds() / 3600
        return age_hours >= source.ttl_hours

    # -- downloading --------------------------------------------------------

    def download(self, url: str) -> str:
        """Stream a remote file to a temp path using constant memory.

        Retries on the failures a long build actually hits: GitHub's asset CDN
        returns the occasional 502, and a connection can drop mid-transfer. A
        forty-file build that dies on one flaky download and has to start over is
        the difference between a three-minute job and a manual one.
        """
        suffix = ".csv" if url.endswith(".csv") else ".parquet"
        last: Exception | None = None
        for attempt in range(DOWNLOAD_RETRIES):
            fd, path = tempfile.mkstemp(suffix=suffix, dir=self._tmp_dir)
            try:
                with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
                    if resp.status_code == 404:
                        resp.raise_for_status()  # Not transient — let it through.
                    if resp.status_code >= 500 or resp.status_code == 429:
                        raise requests.HTTPError(
                            f"{resp.status_code} from {url}", response=resp
                        )
                    resp.raise_for_status()
                    with os.fdopen(fd, "wb") as handle:
                        for chunk in resp.iter_content(chunk_size=1 << 20):
                            if chunk:
                                handle.write(chunk)
                return path
            except (requests.RequestException, OSError) as exc:
                _unlink(path)
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 404:
                    raise
                last = exc
                if attempt + 1 < DOWNLOAD_RETRIES:
                    delay = 2 ** attempt
                    logger.warning(
                        "Download failed (%s), retrying in %ss: %s", exc, delay, url
                    )
                    time.sleep(delay)
            except BaseException:
                _unlink(path)
                raise
        raise RuntimeError(f"Could not download {url} after {DOWNLOAD_RETRIES} attempts") from last

    @contextmanager
    def _fetched(self, url: str) -> Iterator[str]:
        path = self.download(url)
        try:
            yield path
        finally:
            _unlink(path)

    def _reader(self, source: Source, path: str) -> str:
        if source.format == "csv":
            return f"read_csv_auto('{path}', sample_size = -1)"
        return f"read_parquet('{path}', union_by_name = true)"

    def _projection(self, cur, source: Source, path: str) -> str:
        """SELECT list restricted to columns the file has, with team codes fixed.

        Upstream adds and renames columns between seasons, so we intersect rather
        than assume: asking for an absent column turns a load into a 500 for the
        whole dataset.

        Team codes are canonicalised here, once, rather than in every query that
        joins two sources. nflverse writes `LA` into 1999 play-by-play and `STL`
        into the same season's schedule; a join across that pair silently loses
        three franchises for every pre-relocation season.
        """
        available = {
            row[0]
            for row in cur.execute(
                f"DESCRIBE SELECT * FROM {self._reader(source, path)}"
            ).fetchall()
        }
        team_cols = [c for c in source.team_columns if c in available]

        if not source.columns:
            if not team_cols:
                return "*"
            fixes = ", ".join(
                f'{canonical_team_sql(chr(34) + c + chr(34))} AS "{c}"' for c in team_cols
            )
            return f"* REPLACE ({fixes})"

        keep = [c for c in source.columns if c in available]
        if not keep:
            raise ValueError(f"{source.id}: source file has none of the expected columns")
        parts = []
        for c in keep:
            if c in team_cols:
                parts.append(f'{canonical_team_sql(chr(34) + c + chr(34))} AS "{c}"')
            else:
                parts.append(f'"{c}"')
        return ", ".join(parts)

    def _where(self, source: Source) -> str:
        return f" WHERE {source.where_sql}" if source.where_sql else ""

    def _widen(self, cur, source: Source, reader: str, projection: str) -> None:
        """Add columns a later season introduced that the table does not have yet.

        The table's shape comes from whichever season loaded first, and upstream
        genuinely adds fields over time — the 2020 roster file carries
        `draft_number`, the 1999 one does not. Without this, loading seasons in
        order builds a narrow table and then fails on the first season that got
        wider, which reads like a corrupt download rather than an upstream change.
        """
        existing = {
            row[0] for row in cur.execute(f"DESCRIBE {source.table}").fetchall()
        }
        incoming = cur.execute(f"DESCRIBE SELECT {projection} FROM {reader} LIMIT 0").fetchall()
        for name, dtype, *_ in incoming:
            if name not in existing:
                cur.execute(f'ALTER TABLE {source.table} ADD COLUMN "{name}" {dtype}')
                logger.info("%s gained column %s (%s) from a later season", source.table, name, dtype)

    # -- loading ------------------------------------------------------------

    def ensure(self, source_id: str, through: int | None = None) -> None:
        """Make one source's table exist and be current.

        Season-grained sources land in a single table with a `season` column;
        each season is fetched and appended independently so a finished season is
        never re-downloaded to refresh the live one.
        """
        source = sources.get(source_id)
        if source.id == "pbp":
            self.ensure_pbp_resident()
            return

        with self._lock_for(f"src:{source.id}"):
            cur = self.cursor()
            if source.grain == "single":
                if self._needs_refresh(cur, source, None):
                    self._load_single(cur, source)
            else:
                for season in source.seasons(through or latest_season()):
                    if self._needs_refresh(cur, source, season):
                        self._load_season(cur, source, season)
            self._loaded.add(source.id)

    def _load_single(self, cur, source: Source) -> None:
        staging = f"{source.table}__staging"
        try:
            with self._fetched(source.url_for()) as path:
                cur.execute(f"DROP TABLE IF EXISTS {staging}")
                cur.execute(
                    f"CREATE TABLE {staging} AS "
                    f"SELECT {self._projection(cur, source, path)} "
                    f"FROM {self._reader(source, path)}{self._where(source)}"
                )
        except Exception:
            cur.execute(f"DROP TABLE IF EXISTS {staging}")
            if _table_exists(cur, source.table):
                # A network failure must never destroy a stale but serviceable copy.
                logger.exception("Refresh of %s failed; serving the cached copy", source.id)
                return
            raise
        cur.execute(f"DROP TABLE IF EXISTS {source.table}")
        cur.execute(f"ALTER TABLE {staging} RENAME TO {source.table}")
        rows = cur.execute(f"SELECT count(*) FROM {source.table}").fetchone()[0]
        self._record(cur, source.id, None, rows)
        self._checkpoint(cur)
        logger.info("Loaded %s (%s rows)", source.id, rows)

    def _load_season(self, cur, source: Source, season: int) -> None:
        try:
            with self._fetched(source.url_for(season)) as path:
                projection = self._projection(cur, source, path)
                reader = self._reader(source, path)
                where = self._where(source)
                if not _table_exists(cur, source.table):
                    cur.execute(
                        f"CREATE TABLE {source.table} AS "
                        f"SELECT {projection} FROM {reader} LIMIT 0"
                    )
                else:
                    self._widen(cur, source, reader, projection)
                cur.execute(f"DELETE FROM {source.table} WHERE season = ?", [season])
                cur.execute(
                    f"INSERT INTO {source.table} BY NAME "
                    f"SELECT {projection} FROM {reader}{where}"
                )
        except requests.HTTPError as exc:
            # A season that has not kicked off yet simply has no file. That is
            # the normal state of the current season every summer, not an error,
            # and it is why the season window can be a date calculation rather
            # than a constant somebody has to remember to bump each year.
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("%s has no file for %s yet", source.id, season)
                return
            raise
        rows = cur.execute(
            f"SELECT count(*) FROM {source.table} WHERE season = ?", [season]
        ).fetchone()[0]
        self._record(cur, source.id, season, rows)
        self._checkpoint(cur)
        logger.info("Loaded %s %s (%s rows)", source.id, season, rows)

    def _checkpoint(self, cur) -> None:
        """Flush written pages to disk and hand their buffers back.

        Without this, loading twenty-seven seasons one statement at a time still
        accumulates dirty blocks until the 128 MB budget is gone and the *commit*
        fails — the load looks like it is streaming when the write side is not.
        Checkpointing between seasons keeps peak memory flat regardless of how
        many seasons a build covers.
        """
        try:
            cur.execute("CHECKPOINT")
        except duckdb.Error:
            # A concurrent reader can legitimately block a checkpoint; the next
            # season will try again, and nothing is lost by skipping one.
            logger.debug("Checkpoint skipped", exc_info=True)

    # -- play-by-play -------------------------------------------------------

    def ensure_pbp_resident(self) -> None:
        """Load the recent seasons that live permanently in the main database."""
        source = sources.get("pbp")
        with self._lock_for("src:pbp"):
            cur = self.cursor()
            for season in _resident_pbp_seasons():
                if self._needs_refresh(cur, source, season):
                    self._load_season(cur, source, season)
            self._loaded.add("pbp")

    def pbp_relation(self, season: int) -> str:
        """A queryable relation name for one season's plays.

        Resident seasons answer from the main table. Older ones are materialised
        into their own attached database — which is what makes eviction able to
        reclaim disk — and referenced as `pbp_1999.plays`.
        """
        if season in _resident_pbp_seasons():
            self.ensure_pbp_resident()
            return f"(SELECT * FROM pbp WHERE season = {int(season)})"
        self._attach_season(season)
        return f"pbp_{season}.plays"

    def _attach_season(self, season: int) -> None:
        with self._attach_guard:
            if season in self._attached:
                self._attached.move_to_end(season)
                return
            in_flight = [s for s in self._season_locks if s not in self._attached]
            if season not in self._season_locks and len(in_flight) >= PBP_CACHE_SEASONS:
                raise SeasonBusy(
                    "Another season is still loading. Try again in a few seconds."
                )
            lock = self._season_locks.setdefault(season, threading.Lock())

        with lock:
            with self._attach_guard:
                if season in self._attached:
                    self._attached.move_to_end(season)
                    return
            path = os.path.join(data_dir(), f"pbp_{season}.duckdb")
            alias = f"pbp_{season}"
            if not os.path.exists(path):
                self._materialise_season(season, path)
            cur = self.cursor()
            cur.execute(f"ATTACH IF NOT EXISTS '{path}' AS {alias} (READ_ONLY)")
            with self._attach_guard:
                self._attached[season] = path
                self._attached.move_to_end(season)
                self._season_locks.pop(season, None)
                self._evict_locked()

    def _materialise_season(self, season: int, path: str) -> None:
        source = sources.get("pbp")
        tmp_path = f"{path}.building"
        _unlink(tmp_path)
        side = duckdb.connect(tmp_path)
        try:
            side.execute(
                f"SET memory_limit = '{DUCKDB_BUILD_MEMORY_LIMIT if self.building else DUCKDB_MEMORY_LIMIT}'"
            )
            side.execute("SET threads = 1")
            side.execute("SET preserve_insertion_order = false")
            with self._fetched(source.url_for(season)) as parquet:
                projection = self._projection(side, source, parquet)
                side.execute(
                    f"CREATE TABLE plays AS SELECT {projection} "
                    f"FROM {self._reader(source, parquet)}{self._where(source)}"
                )
                side.execute("CREATE INDEX plays_game ON plays (game_id)")
        except BaseException:
            side.close()
            _unlink(tmp_path)
            raise
        side.close()
        os.replace(tmp_path, path)
        logger.info("Materialised play-by-play for %s at %s", season, path)

    def _evict_locked(self) -> None:
        """Drop least-recently-used seasons until we are back under the cap.

        Eviction detaches and deletes the file. Dropping a table inside the main
        database would free nothing: DuckDB's file never shrinks.
        """
        while len(self._attached) > PBP_CACHE_SEASONS:
            season, path = self._attached.popitem(last=False)
            try:
                self.cursor().execute(f"DETACH pbp_{season}")
            except duckdb.Error:
                logger.exception("Could not detach play-by-play for %s", season)
                continue
            _unlink(path)
            logger.info("Evicted cached play-by-play for %s", season)

    # -- introspection ------------------------------------------------------

    def load_records(self) -> list[LoadRecord]:
        cur = self.cursor()
        rows = cur.execute(
            f"SELECT source_id, season, loaded_at, row_count FROM {LOAD_LOG} "
            "ORDER BY source_id, season"
        ).fetchall()
        return [LoadRecord(*row) for row in rows]

    def row_count(self, table: str) -> int | None:
        cur = self.cursor()
        if not _table_exists(cur, table):
            return None
        return cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def table_exists(self, table: str) -> bool:
        return _table_exists(self.cursor(), table)

    def disk_usage_bytes(self) -> int:
        total = 0
        for entry in os.scandir(data_dir()):
            if entry.is_file():
                total += entry.stat().st_size
        return total

    def close(self) -> None:
        self.conn.close()


def _resident_pbp_seasons() -> list[int]:
    last = latest_season()
    return list(range(last - PBP_RESIDENT_SEASONS + 1, last + 1))


def _table_exists(cur, table: str) -> bool:
    row = cur.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
