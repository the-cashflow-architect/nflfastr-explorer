"""GET /api/coverage — the honesty payload every era badge and footline cites.

All the work is in `app.repo.coverage`; this module is deliberately thin,
which is the shape every later router should copy.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..repo import coverage as coverage_repo

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


@router.get("")
def get_coverage() -> dict:
    return coverage_repo.build_coverage()
