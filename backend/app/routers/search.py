"""GET /api/search — the one global search the whole product navigates through.

All the work is in `app.repo.search`; this module stays as thin as
`routers/coverage.py`. Not yet wired into `routers/__init__.py::ALL_ROUTERS` —
that file is shared across packages and is owned elsewhere; see this package's
return notes for what still needs mounting.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..repo import search as search_repo

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def get_search(
    q: str = Query(default="", description="Search text; queries under two characters answer empty."),
    limit: int = Query(default=search_repo.DEFAULT_LIMIT, ge=1, le=50, description="Max results per group."),
) -> dict:
    return search_repo.search(q, limit)
