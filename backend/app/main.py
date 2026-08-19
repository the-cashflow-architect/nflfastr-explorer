from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from .data_store import store
from .models import DataQualityResponse, ExportRequest, FilterOptionsRequest, QueryRequest

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="nflfastR Explorer API",
    description="Query nflverse / nflfastR data with smart filtering",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


@app.post("/api/datasets/{dataset_id}/data-quality")
def data_quality(dataset_id: str, body: QueryRequest):
    try:
        return store.data_quality(dataset_id, body.filters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc


@app.post("/api/datasets/{dataset_id}/export")
def export_dataset(dataset_id: str, body: ExportRequest):
    try:
        result = store.query(dataset_id, body, export_all=True)
        if body.format == "json":
            import json
            json_content = json.dumps(result.to_dict(orient="records"), default=str)
            filename = f"{dataset_id}_export.json"
            return Response(
                content=json_content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        else:
            csv_content = result.to_csv(index=False)
            filename = f"{dataset_id}_export.csv"
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
