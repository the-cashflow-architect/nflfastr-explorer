from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point the module-level store at a scratch file before app.data_store is
# imported, so merely importing the app never writes into the repo.
os.environ.setdefault(
    "DUCKDB_PATH", str(Path(tempfile.mkdtemp(prefix="nflfastr-test-")) / "import.duckdb")
)
os.environ.setdefault("PRELOAD_ON_STARTUP", "false")

from app import data_store as ds_module  # noqa: E402


def make_frame(rows: int = 60) -> pl.DataFrame:
    """Small stand-in for an nflverse frame, with a deliberately null column."""
    return pl.DataFrame(
        {
            "season": [2024 + (i % 2) for i in range(rows)],
            "week": [(i % 18) + 1 for i in range(rows)],
            "team": [["KC", "BUF", "SF"][i % 3] for i in range(rows)],
            "player_display_name": [f"Player {i % 10}" for i in range(rows)],
            "passing_yards": [float(i * 3) for i in range(rows)],
            # Null for exactly half the rows, so null_pct must come out at 50.0
            "cpoe": [None if i % 2 else float(i) for i in range(rows)],
        }
    )


@pytest.fixture
def store_factory(tmp_path, monkeypatch):
    """Build DataStores backed by a temp DuckDB file, with no network access."""
    calls: dict[str, int] = {}

    def fake_fetch(self, dataset_id: str) -> pl.DataFrame:
        calls[dataset_id] = calls.get(dataset_id, 0) + 1
        return make_frame()

    monkeypatch.setattr(ds_module.DataStore, "_fetch_frame", fake_fetch)

    db_path = tmp_path / "test.duckdb"

    def factory() -> ds_module.DataStore:
        return ds_module.DataStore(path=str(db_path))

    factory.calls = calls  # type: ignore[attr-defined]
    factory.db_path = db_path  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def store(store_factory):
    return store_factory()
