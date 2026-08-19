from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point the module-level store at a scratch file before app.data_store is
# imported, so merely importing the app never writes into the repo.
os.environ.setdefault(
    "DUCKDB_PATH", str(Path(tempfile.mkdtemp(prefix="nflfastr-test-")) / "import.duckdb")
)
os.environ.setdefault("PRELOAD_ON_STARTUP", "false")

from app import data_store as ds_module  # noqa: E402


def write_fixture_parquet(path: str, rows: int = 60) -> str:
    """Write a small stand-in for an nflverse parquet file.

    Deliberately includes a column that is null in half the rows, and one
    extra column no dataset config asks for, so column projection is
    exercised for real.
    """
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT
            2024 + (i % 2)                         AS season,
            (i % 18) + 1                           AS week,
            ['KC','BUF','SF'][(i % 3) + 1]         AS team,
            'Player ' || (i % 10)                  AS player_display_name,
            (i * 3)::DOUBLE                        AS passing_yards,
            CASE WHEN i % 2 = 0 THEN i::DOUBLE END AS cpoe,
            'unused'                               AS a_column_we_never_select
          FROM range({rows}) t(i)
        ) TO '{path}' (FORMAT PARQUET)
        """
    )
    con.close()
    return path


@pytest.fixture
def store_factory(tmp_path, monkeypatch):
    """Build DataStores whose downloads resolve to a local parquet file.

    Only the network fetch is stubbed — the real projection, read_parquet,
    staging-table swap, and freshness logic all run.
    """
    calls: dict[str, int] = {}
    source = write_fixture_parquet(str(tmp_path / "source.parquet"))

    def fake_download(self, url: str) -> str:
        # Copy so the caller's unlink() cannot delete the shared fixture.
        target = tempfile.mkstemp(suffix=".parquet", dir=str(tmp_path))[1]
        with open(source, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
        return target

    real_create = ds_module.DataStore._create_table

    def counting_create(self, cur, dataset_id, table):
        calls[dataset_id] = calls.get(dataset_id, 0) + 1
        return real_create(self, cur, dataset_id, table)

    monkeypatch.setattr(ds_module.DataStore, "_download_parquet", fake_download)
    monkeypatch.setattr(ds_module.DataStore, "_create_table", counting_create)

    # One season file per dataset keeps the expected row counts obvious.
    for cfg in ds_module.DATASETS.values():
        monkeypatch.setattr(cfg, "seasons", [2025])

    db_path = tmp_path / "test.duckdb"

    def factory() -> ds_module.DataStore:
        return ds_module.DataStore(path=str(db_path))

    factory.calls = calls  # type: ignore[attr-defined]
    factory.db_path = db_path  # type: ignore[attr-defined]
    factory.source = source  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def store(store_factory):
    return store_factory()
