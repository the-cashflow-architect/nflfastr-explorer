"""Runtime configuration, driven by environment variables.

Every knob here exists because the defaults have to work on a small
container (Render's free tier is 512 MB) without the operator editing code.
"""

from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _seasons_env(name: str, default: list[int]) -> list[int]:
    raw = os.environ.get(name)
    if not raw:
        return default
    seasons = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                seasons.append(int(part))
            except ValueError:
                continue
    return seasons or default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Origins allowed to call the API. Comma-separated; the local dev server is
# always included so `npm run dev` works without extra setup.
LOCAL_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    configured = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return list(dict.fromkeys(configured + LOCAL_ORIGINS))


def cors_origin_regex() -> str | None:
    """Optional regex for preview deploys (e.g. Vercel/Render branch URLs)."""
    return os.environ.get("CORS_ORIGIN_REGEX") or None


# Persisted DuckDB file. Keeping the data on disk rather than in :memory:
# means a restart re-opens the existing tables instead of re-downloading
# every parquet file from nflverse, and keeps resident memory flat.
def duckdb_path() -> str:
    raw = os.environ.get("DUCKDB_PATH", "data/nflfastr.duckdb")
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


# Seasons pulled from nflverse. Play-by-play is by far the largest table
# (~50k rows x 35 columns per season, with a wide `desc` string), so it
# defaults to a single season.
PLAYER_SEASONS = _seasons_env("PLAYER_SEASONS", [2022, 2023, 2024, 2025])
PBP_SEASONS = _seasons_env("PBP_SEASONS", [2025])

# DuckDB sizes its buffer pool from total host RAM by default and cannot see a
# container's cgroup limit, so on a small instance it happily over-allocates
# and gets OOM-killed. Pin it, and give it a temp dir to spill into.
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "128MB")
DUCKDB_THREADS = _int_env("DUCKDB_THREADS", 1)

# Seconds to wait on an nflverse parquet download.
DOWNLOAD_TIMEOUT = _int_env("DOWNLOAD_TIMEOUT", 180)

# Hard ceiling on an export. Without this, an unfiltered play-by-play export
# materialises the entire table in memory and takes the process down.
EXPORT_MAX_ROWS = _int_env("EXPORT_MAX_ROWS", 100_000)

# Rows per batch when streaming an export response.
EXPORT_CHUNK_ROWS = _int_env("EXPORT_CHUNK_ROWS", 5_000)

# How long a persisted table stays usable before it is re-downloaded. The
# database file survives restarts, so without this an nflverse update would
# never be picked up. 0 disables the check.
DATA_MAX_AGE_HOURS = _int_env("DATA_MAX_AGE_HOURS", 24)

# Load datasets in a background thread at startup so the first user request
# isn't stuck behind a multi-minute download. Disable to load fully lazily.
PRELOAD_ON_STARTUP = _bool_env("PRELOAD_ON_STARTUP", True)
