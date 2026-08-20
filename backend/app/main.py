from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import (
    EXPORT_MAX_ROWS,
    PRELOAD_ON_STARTUP,
    cors_origin_regex,
    cors_origins,
)
from .data_store import store
from .models import ExportRequest, FilterOptionsRequest, QueryRequest, WeeklyBreakdownRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the datasets off the request path. It runs in a daemon thread so a
    # slow nflverse download never blocks startup or the health check.
    if PRELOAD_ON_STARTUP:
        thread = threading.Thread(target=store.preload, name="preload", daemon=True)
        thread.start()
        logger.info("Started background dataset preload")
    yield


app = FastAPI(
    title="nflfastR Explorer API",
    description="Query nflverse / nflfastR data with smart filtering",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/datasets")
def list_datasets() -> list[dict]:
    return store.list_datasets()


@app.get("/api/datasets/{dataset_id}/schema")
def get_schema(dataset_id: str):
    try:
        return store.get_schema(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc


@app.post("/api/datasets/{dataset_id}/query")
def query_dataset(dataset_id: str, body: QueryRequest):
    try:
        return store.query(dataset_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/datasets/{dataset_id}/filter-options")
def filter_options(dataset_id: str, body: FilterOptionsRequest):
    try:
        return store.filter_options(
            dataset_id,
            body.field,
            body.filters,
            body.search,
            body.limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/datasets/{dataset_id}/data-quality")
def data_quality(dataset_id: str, body: QueryRequest):
    try:
        return store.data_quality(dataset_id, body.filters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/datasets/{dataset_id}/weekly-breakdown")
def weekly_breakdown(dataset_id: str, body: WeeklyBreakdownRequest):
    try:
        return store.weekly_breakdown(dataset_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/datasets/{dataset_id}/export")
def export_dataset(dataset_id: str, body: ExportRequest):
    try:
        matching = store.export_row_count(dataset_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    limit = min(body.max_rows or EXPORT_MAX_ROWS, EXPORT_MAX_ROWS)
    truncated = matching > limit
    exported = min(matching, limit)

    if body.format == "json":
        media_type = "application/json"
        filename = f"{dataset_id}_export.json"
    else:
        media_type = "text/csv"
        filename = f"{dataset_id}_export.csv"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        # Let the client tell the user their export was capped.
        "X-Export-Rows": str(exported),
        "X-Export-Matching-Rows": str(matching),
        "X-Export-Truncated": "true" if truncated else "false",
        "Access-Control-Expose-Headers": (
            "X-Export-Rows, X-Export-Matching-Rows, X-Export-Truncated, Content-Disposition"
        ),
    }

    try:
        stream = store.export_stream(dataset_id, body, max_rows=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(stream, media_type=media_type, headers=headers)
