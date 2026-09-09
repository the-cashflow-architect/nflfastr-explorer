"""The two endpoints behind the draft pages: the class index and one class board.

Thin, like `routers/coverage.py`: every query lives in `app.repo.draft`, and this
module's only jobs are the HTTP contract and the response models. See that module's
docstring for the join rules (PFR team codes, the pfr_id-only combine join, why
car_av never appears) — nothing here re-derives them.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from ..repo import draft as draft_repo

router = APIRouter(prefix="/api", tags=["draft"])


# --- GET /api/draft ------------------------------------------------------------


class FirstOverall(BaseModel):
    player: str | None = None
    gsis_id: str | None = None
    player_href: str | None = None
    team: str | None = None
    team_href: str | None = None


class DraftYear(BaseModel):
    year: int
    href: str
    picks: int
    first_overall: FirstOverall | None = None


class DraftIndexResponse(BaseModel):
    years: list[DraftYear]
    first_season: int
    coverage_note: str


@router.get("/draft", response_model=DraftIndexResponse)
def get_draft_index() -> object:
    return draft_repo.draft_index()


# --- GET /api/draft/{year} ------------------------------------------------------


class CombineMeasurables(BaseModel):
    forty: float | None = None
    bench: float | None = None
    vertical: float | None = None
    broad: float | None = None
    cone: float | None = None
    shuttle: float | None = None


class DraftPick(BaseModel):
    round: int
    pick: int
    team: str | None = None
    team_href: str | None = None
    # The raw code draft_picks itself carries — Pro-Football-Reference's, not the
    # current franchise code — kept so a pick with an unresolved `team` still
    # shows *something* rather than a blank cell.
    pfr_team_code: str | None = None
    gsis_id: str | None = None
    pfr_player_id: str | None = None
    player: str | None = None
    player_href: str | None = None
    position: str | None = None
    college: str | None = None
    age: int | None = None
    last_season_played: int | None = None
    games: int | None = None
    seasons_started: int | None = None
    allpro: int | None = None
    probowls: int | None = None
    hof: bool
    w_av: int | None = None
    dr_av: int | None = None
    combine: CombineMeasurables | None = None
    combine_match_confidence: str | None = None


class ClassSummary(BaseModel):
    picks: int
    pro_bowlers: int
    all_pros: int
    hof: int
    median_games: float | None = None


class BestValueEntry(BaseModel):
    round: int
    pick: int
    gsis_id: str | None = None
    player: str | None = None
    player_href: str | None = None
    w_av: int
    slot_median_av: float
    delta: float


class BestValueCohort(BaseModel):
    first_season: int
    last_season: int
    as_of_season: int
    note: str


class TeamFilter(BaseModel):
    team: str
    team_href: str | None = None


class DraftClassResponse(BaseModel):
    year: int
    prev_year: int | None = None
    next_year: int | None = None
    rounds: list[int]
    team_filters: list[TeamFilter]
    summary: ClassSummary
    picks: list[DraftPick]
    best_value: list[BestValueEntry]
    best_value_cohort: BestValueCohort
    coverage_note: str
    av_note: str
    combine_note: str


@router.get("/draft/{year}", response_model=DraftClassResponse)
def get_draft_class(
    year: int = Path(description="Draft year, e.g. 2017."),
    team: str | None = Query(default=None, description="Current franchise code; filters the picks list only."),
    round: int | None = Query(default=None, ge=1, description="Round number; filters the picks list only."),
) -> object:
    payload = draft_repo.draft_class(year, team=team, round=round)
    if payload is None:
        raise HTTPException(status_code=404, detail="No draft class on file for that year.")
    return payload
