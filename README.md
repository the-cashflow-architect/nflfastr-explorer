# nflfastR Explorer

Interactive explorer for [nflfastR](https://www.nflfastr.com/) / [nflverse](https://www.nflverse.com/) data with smart filtering, sortable tables, and stat glossary tooltips.

## Datasets

- **Weekly Player Stats** — game-week player stats (2022–2025)
- **Season Player Stats** — regular-season aggregates
- **Play Explorer** — play-by-play rows (2024–2025)

Data comes from the [nflverse-data](https://github.com/nflverse/nflverse-data) parquet releases and is queried locally with DuckDB. Each file is streamed to disk and read by DuckDB directly, with column projection pushed into the parquet reader, so a season of play-by-play never materialises the ~380 columns the app doesn't expose.

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

First startup downloads parquet files from nflverse (may take a minute). They
are cached in a DuckDB file (`DUCKDB_PATH`), so later starts are immediate.

Copy `backend/.env.example` to `backend/.env` for the full list of settings.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Features

- **Home → drill down** — a landing page with Players / Teams / Plays entry points, quick links (Passing Leaders, Team Defense, ...), and a 32-team jump grid, instead of dropping straight into a dense table
- **Position-aware stat views** — position pills (QB/RB/WR/TE/Defense/K-P) plus Basic/Advanced/Fantasy/Custom tabs, so the columns and default sort match the position instead of one fantasy-flavored table for everyone
- **Team leaderboards** — league-wide offense and defense totals aggregated from real player box scores, sortable, with a click-through to that team's roster
- **Player cockpit** — click any player to see their career table and stat trend charts, with a real headshot
- **Smart filters** — season → week → team → player cascade; filter options update as you select
- **Stat tooltips everywhere** — hover any column header, stat tab, or position pill for a plain-language explanation; tooltips render in a portal so they're never clipped by a scrolling table or panel
- **Focus mode** — an expand button on tables, charts, and filters opens that panel full-screen
- **Column picker** — show/hide any stat column by category, with search
- **Sortable table** — click headers to sort; a pinned player/team column and edge-fade shadows keep you oriented while scrolling a wide table

## Configuration

All backend settings are environment variables; see `backend/.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | *(empty)* | Comma-separated origins allowed to call the API. **The deployed frontend URL must be listed here** — localhost is always allowed, so a missing value works in dev and fails in production. |
| `CORS_ORIGIN_REGEX` | *(empty)* | Regex for preview deploy URLs, e.g. `https://.*\.vercel\.app`. |
| `DUCKDB_PATH` | `data/nflfastr.duckdb` | Where the cached data lives. Persisting it means a restart re-opens the tables instead of re-downloading them. |
| `PLAYER_SEASONS` | `2022,2023,2024,2025` | Seasons loaded for the player tables. |
| `PBP_SEASONS` | `2025` | Seasons loaded for play-by-play. This is the largest table by far — add seasons only if the instance has the memory. |
| `DUCKDB_MEMORY_LIMIT` | `128MB` | DuckDB's buffer pool. It defaults to a share of **host** RAM and cannot see a container's memory limit, so this must be pinned well below the instance size. |
| `DUCKDB_THREADS` | `1` | DuckDB worker threads. More threads means more concurrent buffers. |
| `DOWNLOAD_TIMEOUT` | `180` | Seconds to wait on an nflverse parquet download. |
| `DATA_MAX_AGE_HOURS` | `24` | Re-download a cached table once it is older than this. `0` disables. |
| `EXPORT_MAX_ROWS` | `100000` | Hard ceiling on an export. Responses are streamed, and a capped export sets `X-Export-Truncated`. |
| `PRELOAD_ON_STARTUP` | `true` | Warm the datasets in a background thread so the first request isn't stuck behind a download. |

### Deploying

Datasets load lazily and one at a time. Measured against real nflverse data
with the default settings, loading all three peaks at **~256 MB** — half of a
512 MB instance — and takes about 7 seconds total.

Two settings matter most on a small instance. `DUCKDB_MEMORY_LIMIT` must stay
well below the container limit, because DuckDB sizes its buffer pool from host
RAM and will otherwise over-allocate and be OOM-killed. `PBP_SEASONS` controls
the largest table; each extra season adds to both load time and peak memory.

DuckDB allows a single writing process per database file, so run one uvicorn
worker (the default). If you scale to multiple workers or instances, give each
its own `DUCKDB_PATH`.

## Testing

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest   # no network needed
cd frontend && npx oxlint --deny-warnings && npx tsc -b && npm run build
```

Both run in CI on every push (`.github/workflows/ci.yml`).

## Stack

- Backend: FastAPI, DuckDB
- Frontend: React, TanStack Query & Table, Tailwind CSS
