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

First startup downloads parquet files from nflverse (may take a minute).

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

## Stack

- Backend: FastAPI, nflreadpy, DuckDB, Polars
- Frontend: React, TanStack Query & Table, Tailwind CSS
