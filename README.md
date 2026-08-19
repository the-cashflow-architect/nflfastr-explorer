# nflfastR Explorer

Interactive explorer for [nflfastR](https://www.nflfastr.com/) / [nflverse](https://www.nflverse.com/) data with smart filtering, sortable tables, and stat glossary tooltips.

## Datasets

- **Weekly Player Stats** — game-week player stats (2022–2025)
- **Season Player Stats** — regular-season aggregates
- **Play Explorer** — play-by-play rows (2024–2025)

Data is loaded via [nflreadpy](https://nflreadpy.nflverse.com/) and queried locally with DuckDB.

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

- **Smart filters** — season → week → team → player cascade; filter options update as you select
- **Stat tooltips** — hover column headers for definitions and formulas (EPA, CPOE, WOPR, etc.)
- **Column picker** — show/hide any stat column by category
- **Sortable table** — click headers to sort; paginated results

## Configuration

All backend settings are environment variables; see `backend/.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORS_ORIGINS` | *(empty)* | Comma-separated origins allowed to call the API. **The deployed frontend URL must be listed here** — localhost is always allowed, so a missing value works in dev and fails in production. |
| `CORS_ORIGIN_REGEX` | *(empty)* | Regex for preview deploy URLs, e.g. `https://.*\.vercel\.app`. |
| `DUCKDB_PATH` | `data/nflfastr.duckdb` | Where the cached data lives. Persisting it means a restart re-opens the tables instead of re-downloading them. |
| `PLAYER_SEASONS` | `2022,2023,2024,2025` | Seasons loaded for the player tables. |
| `PBP_SEASONS` | `2025` | Seasons loaded for play-by-play. This is the largest table by far — add seasons only if the instance has the memory. |
| `DATA_MAX_AGE_HOURS` | `24` | Re-download a cached table once it is older than this. `0` disables. |
| `EXPORT_MAX_ROWS` | `100000` | Hard ceiling on an export. Responses are streamed, and a capped export sets `X-Export-Truncated`. |
| `PRELOAD_ON_STARTUP` | `true` | Warm the datasets in a background thread so the first request isn't stuck behind a download. |

### Deploying

Datasets load lazily and one at a time, so memory stays near the size of the
largest single table rather than all three at once. On a 512 MB instance keep
`PBP_SEASONS` to one season.

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

- Backend: FastAPI, nflreadpy, DuckDB, Polars
- Frontend: React, TanStack Query & Table, Tailwind CSS
