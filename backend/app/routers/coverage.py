"""GET /api/coverage — the honesty payload every era badge and footline cites.

All the work is in `app.repo.coverage`; this module is deliberately thin, which
is the shape every later router copies.

The response model is declared rather than returned as a bare dict, and that is
not bookkeeping. The frontend's types are generated from this schema, so an
undeclared shape reaches the client as `{}` — every field access unchecked, and
a wrong one a runtime crash instead of a build failure. That is exactly how the
footer's coverage line came to read a key the payload does not have and take the
whole application down with it.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..repo import coverage as coverage_repo

from fastapi import APIRouter

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


class CoverageWindow(BaseModel):
    """One named boundary in the data, and why it is where it is."""

    first_season: int
    last_season: int | None = None
    note: str | None = None


class DatasetCoverage(BaseModel):
    id: str
    name: str
    label: str
    description: str
    source_url: str | None = None
    #: What is actually loaded, which is not always what was declared.
    season_min: int | None = None
    season_max: int | None = None
    declared_first_season: int | None = None
    declared_last_season: int | None = None
    row_count: int | None = None
    loaded_at: str | None = None
    #: Empty for a source with no caveat, and null for one that never declared
    #: the field — both mean "nothing to warn about" and neither is a string.
    coverage_note: str | None = None
    status: str


class NotBuilding(BaseModel):
    what: str
    why: str


class CoverageResponse(BaseModel):
    datasets: list[DatasetCoverage]
    #: Keyed by boundary name — stats, charting, next_gen_stats, pfr_advanced,
    #: snap_counts, injuries, draft. A dict rather than fixed fields because the
    #: set grows with the data, and a page that cites one looks it up by name.
    coverage_windows: dict[str, CoverageWindow]
    not_building: list[NotBuilding]
    #: The newest season with a played Super Bowl. Distinct from the next field:
    #: from week one of a new season those two differ, and a footline that
    #: conflates them claims coverage of a season barely under way.
    latest_completed_season: int | None = None
    latest_season_with_games: int | None = None
    disk_usage_bytes: int | None = None
    generated_at: str | None = None


@router.get("", response_model=CoverageResponse)
def get_coverage() -> CoverageResponse:
    return CoverageResponse(**coverage_repo.build_coverage())
