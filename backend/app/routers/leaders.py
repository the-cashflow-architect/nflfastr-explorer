"""The two leaderboard endpoints: the hub, and one board.

Thin, like every other package's router. All the querying lives in
`app.repo.leaders`; this module owns the HTTP contract and the response models.

**Every endpoint declares a response model.** The frontend's TypeScript types are
generated from this OpenAPI schema, so an endpoint returning a bare dict becomes an
untyped hole on the other side.

**`response_model_exclude_unset=True` on both.** The repo leaves a key out of its
dict entirely when a block does not apply — a board whose columns this deployment has
not loaded has no `rows` key at all, rather than an empty list that a page would
render as a leaderboard nobody is on. `exclude_unset` carries that absence through
serialisation instead of turning it into `null`. A key the repo *did* set to `null` —
a player with no position on file, a game with no id to link to — stays in the
response, because "there is nothing here" and "we never computed this" are different
answers.

Not yet wired into `routers/__init__.py::ALL_ROUTERS` — that file is shared across
packages and is owned by the integrator.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from ..loader import SeasonBusy
from ..repo import leaders as leaders_repo

router = APIRouter(prefix="/api/leaders", tags=["leaders"])


# --- shared pieces -----------------------------------------------------------------


class Era(BaseModel):
    """The window a board covers. Present on every board, without exception."""

    model_config = ConfigDict(populate_by_name=True)

    #: `from` is a Python keyword, so the field is aliased rather than renamed: the
    #: payload the frontend types itself against keeps the word the spec uses.
    first_season: int = Field(alias="from")
    last_season: int | None = Field(default=None, alias="to")
    note: str
    source: str | None = None


class Option(BaseModel):
    id: str
    label: str


# --- GET /api/leaders ---------------------------------------------------------------


class HubStat(BaseModel):
    id: str
    category: str
    label: str
    definition: str
    unit: str
    higher_is_better: bool
    scopes: list[str]
    default_scope: str
    href: str
    era: Era
    computed_by_us: bool
    formula: str | None = None
    note: str | None = None
    qualification: str | None = None
    components_missing: list[str] | None = None
    glossary_key: str | None = None


class HubCategory(BaseModel):
    id: str
    label: str
    description: str
    default_stat: str
    href: str
    stats: list[HubStat]


class UnavailableBoard(BaseModel):
    category: str
    stat: str
    label: str
    reason: str


class LeadersIndex(BaseModel):
    era: Era
    scopes: list[Option]
    scoring_formats: list[Option]
    default_scoring: str
    categories: list[HubCategory]
    note: str
    unavailable: list[UnavailableBoard] | None = None


@router.get("", response_model=LeadersIndex, response_model_exclude_unset=True)
def get_leaders_index() -> Any:
    """Every board this deployment can serve, each with the window it covers."""
    try:
        return leaders_repo.leaders_index()
    except SeasonBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- GET /api/leaders/{category}/{stat} ---------------------------------------------


class StatSummary(BaseModel):
    id: str
    label: str
    definition: str
    unit: str
    higher_is_better: bool
    computed_by_us: bool
    formula: str | None = None
    note: str | None = None
    scoring_format: str | None = None
    scoring_label: str | None = None
    components_used: list[str] | None = None
    components_missing: list[str] | None = None
    components_note: str | None = None
    glossary_key: str | None = None


class Qualification(BaseModel):
    """Always the rule in words, never a bare flag: a rate board without a stated
    minimum is a list of players who attempted three passes."""

    applied: bool
    rule_text: str
    threshold: float | None = None
    #: Season scope qualifies each season against its own length, so the board
    #: carries one threshold per season rather than a single number for all of them.
    thresholds_by_season: dict[str, float] | None = None
    column: str | None = None
    computed_by_us: bool


class BoardFilters(BaseModel):
    position: str | None = None
    season_min: int | None = None
    season_max: int | None = None
    active_only: bool
    team: str | None = None
    qualified: bool
    scoring: str | None = None


class LeaderRow(BaseModel):
    rank: int
    tied: bool
    tied_count: int
    gsis_id: str
    href: str
    player: str
    position: str | None = None
    team: str | None = None
    value: float | None = None
    seasons: int | None = None
    first_season: int | None = None
    last_season: int | None = None
    games: float | None = None
    season: int | None = None
    week: int | None = None
    opponent: str | None = None
    game_id: str | None = None
    game_href: str | None = None
    support: dict[str, float | None] | None = None


class CategoryRef(BaseModel):
    id: str
    label: str


class Leaderboard(BaseModel):
    category: CategoryRef
    stat: StatSummary
    scope: str
    scope_label: str
    era: Era
    available: bool
    note: str | None = None
    supported_scopes: list[str] | None = None
    qualification: Qualification | None = None
    filters: BoardFilters | None = None
    seasons_in_scope: list[int] | None = None
    support_columns: list[Option] | None = None
    rows: list[LeaderRow] | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    rules: dict[str, str] | None = None


@router.get(
    "/{category}/{stat}",
    response_model=Leaderboard,
    response_model_exclude_unset=True,
)
def get_leaderboard(
    category: str = Path(description="Leaderboard category id, from GET /api/leaders."),
    stat: str = Path(description="Stat id within that category."),
    scope: str = Query(
        default="career",
        pattern="^(career|season|game)$",
        description="Career, one season, or one game.",
    ),
    position: str | None = Query(
        default=None, description="Position or position group, e.g. QB or WR."
    ),
    season_min: int | None = Query(
        default=None, description="First season to include; clamped to the board's window."
    ),
    season_max: int | None = Query(
        default=None, description="Last season to include; clamped to the board's window."
    ),
    active_only: bool = Query(
        default=False, description="Only players whose final season on file is the newest one."
    ),
    team: str | None = Query(
        default=None,
        description="Franchise code. On a career board this narrows the totals to that club.",
    ),
    qualified: bool = Query(
        default=True,
        description="Apply the board's minimum volume. The rule is stated either way.",
    ),
    scoring: str = Query(
        default=leaders_repo.DEFAULT_SCORING,
        pattern="^(standard|half|ppr)$",
        description="Fantasy scoring format. Ignored by every board but Fantasy.",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=leaders_repo.DEFAULT_PAGE_SIZE, ge=1, le=leaders_repo.MAX_PAGE_SIZE),
) -> Any:
    """One ranked board, with its era window and its qualification rule attached."""
    try:
        return leaders_repo.leaderboard(
            category,
            stat,
            scope=scope,
            position=position,
            season_min=season_min,
            season_max=season_max,
            active_only=active_only,
            team=team,
            qualified=qualified,
            scoring=scoring,
            page=page,
            page_size=page_size,
        )
    except leaders_repo.UnknownBoard as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0] if exc.args else exc)) from exc
    except SeasonBusy as exc:
        # Not a failure: a season's plays are being materialised and the answer
        # exists a few seconds from now. Saying so beats an empty leaderboard.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
