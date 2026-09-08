"""The six endpoints behind the player cockpit.

Thin, like `routers/coverage.py`: every query lives in `app.repo.players` and
`app.repo.percentiles`, and this module's only jobs are the HTTP contract and the
response models.

Two of those jobs are load-bearing.

**Every endpoint declares a response model.** The frontend's TypeScript types are
generated from this schema, so an endpoint that returned a bare dict would arrive on
the other side as an untyped hole.

**Optional blocks are omitted, not emptied.** The repo leaves a block out of its dict
when the player has no data for it, and `response_model_exclude_unset=True` carries
that through serialisation: a key that was never set does not appear in the JSON. A
key the repo *did* set to `null` — a stat nobody charted, a score for a game not yet
played — is kept, because "we know there is nothing here" and "we never looked" are
different answers and the page renders them differently.

Not yet wired into `routers/__init__.py::ALL_ROUTERS` — that file is shared across
packages and this one does not own it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from ..loader import SeasonBusy
from ..repo import percentiles as percentiles_repo
from ..repo import players as players_repo

router = APIRouter(prefix="/api", tags=["players"])

_SEASON_BUSY = (
    "Another play-by-play season is still loading. Try again in a few seconds."
)


def _guard(call, *args, **kwargs):
    """Run a repo call, turning a busy play-by-play cache into an honest 503.

    `SeasonBusy` means two older seasons are already materialising and a third was
    asked for. That is a wait, not a failure and certainly not an empty result, so
    it becomes a 503 with a plain sentence rather than a 500 or a page of blanks.
    """
    try:
        return call(*args, **kwargs)
    except SeasonBusy:
        raise HTTPException(status_code=503, detail=_SEASON_BUSY) from None


def _found(payload: Any) -> Any:
    if payload is None:
        raise HTTPException(status_code=404, detail="No player with that id.")
    return payload


# --- shared model pieces ---------------------------------------------------------


class Headline(BaseModel):
    id: str | None = None
    label: str | None = None
    value: float | None = None
    unit: str | None = None
    source: str | None = None
    note: str | None = None


class DraftLine(BaseModel):
    season: int
    round: int | None = None
    pick: int | None = None
    team_code: str | None = None
    team: str | None = None
    team_href: str | None = None
    class_href: str | None = None


class SourceWindow(BaseModel):
    """One dataset's window *for this player*, beside the dataset's own."""

    source: str
    name: str
    declared_first_season: int | None = None
    available: bool
    rows: int
    first_season: int | None = None
    last_season: int | None = None
    note: str | None = None


class StatColumn(BaseModel):
    id: str
    label: str
    unit: str
    kind: str | None = None
    first_season: int | None = None


# --- GET /api/players -------------------------------------------------------------


class IndexDraft(BaseModel):
    season: int
    round: int | None = None
    pick: int | None = None


class IndexRow(BaseModel):
    gsis_id: str
    display_name: str | None = None
    slug: str | None = None
    href: str
    position: str | None = None
    position_group: str | None = None
    latest_team: str | None = None
    first_season: int | None = None
    last_season: int | None = None
    status: str | None = None
    active: bool
    college: str | None = None
    games: float | None = None
    teams: list[str]
    draft: IndexDraft | None = None
    headline: Headline


class IndexRules(BaseModel):
    active: str
    season_filter: str
    headline: str


class IndexFilters(BaseModel):
    q: str | None = None
    position: str | None = None
    team: str | None = None
    season: int | None = None
    college: str | None = None
    draft_year: int | None = None
    status: str | None = None


class PlayerIndexResponse(BaseModel):
    rows: list[IndexRow]
    total: int
    page: int
    page_size: int
    sort: str
    filters: IndexFilters
    rules: IndexRules
    snap_counts_first_season: int


@router.get("/players", response_model=PlayerIndexResponse)
def get_players(
    q: str | None = Query(default=None, description="Name search, accent-insensitive."),
    position: str | None = Query(default=None, description="Position group (QB, WR, DB) or exact position."),
    team: str | None = Query(default=None, description="Current franchise code; matches any team he has a season with."),
    season: int | None = Query(default=None, description="Season the player was on file as active in."),
    college: str | None = Query(default=None),
    draft_year: int | None = Query(default=None),
    status: str | None = Query(default=None, description="'active' or 'retired'; the rule is returned in `rules`."),
    sort: str = Query(default="recent", pattern="^(recent|name|games)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=players_repo.DEFAULT_PAGE_SIZE, ge=1, le=players_repo.MAX_PAGE_SIZE),
) -> Any:
    return _guard(
        players_repo.player_index,
        q=q, position=position, team=team, season=season, college=college,
        draft_year=draft_year, status=status, sort=sort, page=page, page_size=page_size,
    )


# --- GET /api/players/{gsis_id} ----------------------------------------------------


class Identity(BaseModel):
    gsis_id: str
    display_name: str | None = None
    slug: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None
    position_group: str | None = None
    jersey_number: int | None = None
    height: float | None = None
    weight: float | None = None
    birth_date: str | None = None
    age: float | None = None
    headshot_url: str | None = None
    college: str | None = None
    college_conference: str | None = None
    rookie_season: int | None = None
    last_season: int | None = None
    years_of_experience: float | None = None
    status: str | None = None
    status_label: str
    team: str | None = None
    team_href: str | None = None


class Honors(BaseModel):
    hof: bool | None = None
    pro_bowls: float | None = None
    all_pros: float | None = None
    weighted_career_av: float | None = None
    draft_av: float | None = None
    seasons_started: float | None = None
    av_label: str
    source_note: str


class Tile(BaseModel):
    id: str
    label: str
    value: float | None = None
    unit: str | None = None
    context: str
    computed_by_us: bool


class CareerRow(BaseModel):
    season: int
    team: str | None = None
    team_href: str | None = None
    code_in_season: str | None = None
    teams: list[str] | None = None
    team_label: str | None = None
    is_combined: bool
    games: float | None = None
    stats: dict[str, float | None]
    led_league: list[str]


class CareerTotal(BaseModel):
    seasons: int
    first_season: int
    last_season: int
    games: float | None = None
    stats: dict[str, float | None]


class CareerTable(BaseModel):
    columns: list[StatColumn]
    rows: list[CareerRow]
    total: CareerTotal
    leader_note: str | None = None
    note: str | None = None


class RecentGame(BaseModel):
    season: int
    week: int | None = None
    team: str | None = None
    opponent: str | None = None
    game_id: str | None = None
    game_href: str | None = None
    gameday: str | None = None
    home_away: str | None = None
    team_score: float | None = None
    opp_score: float | None = None
    result: str | None = None


class AvailableTabs(BaseModel):
    gamelog: bool
    splits: bool
    splits_note: str | None = None
    advanced: bool


class Era(BaseModel):
    stats_first_season: int | None = None
    note: str


class PlayerHubResponse(BaseModel):
    identity: Identity
    era: Era
    draft: DraftLine | None = None
    honors: Honors | None = None
    tiles: list[Tile] | None = None
    career_regular: CareerTable | None = None
    career_postseason: CareerTable | None = None
    last_games: list[RecentGame] | None = None
    coverage: list[SourceWindow]
    available_tabs: AvailableTabs


@router.get(
    "/players/{gsis_id}",
    response_model=PlayerHubResponse,
    response_model_exclude_unset=True,
)
def get_player(gsis_id: str = Path(description="nflverse gsis_id, e.g. 00-0033873")) -> Any:
    return _found(_guard(players_repo.player_hub, gsis_id))


# --- GET /api/players/{gsis_id}/percentiles ----------------------------------------


class Cohort(BaseModel):
    position_group: str | None = None
    season: int | None = None
    n: int
    qualification: str
    computed_by_us: bool


class MetricBar(BaseModel):
    id: str
    label: str
    unit: str
    value: float | None = None
    higher_is_better: bool
    n: int
    median: float | None = None
    percentile: float | None = None
    computed_by_us: bool
    coverage_note: str | None = None
    note: str | None = None
    first_season: int | None = None


class SourceWindowNote(BaseModel):
    first_season: int | None = None
    note: str


class PercentilesResponse(BaseModel):
    gsis_id: str
    scope: str
    season: int | None = None
    position_group: str | None = None
    cohort: Cohort
    in_cohort: bool | None = None
    source_window: SourceWindowNote | None = None
    metrics: list[MetricBar] | None = None
    note: str | None = None


@router.get(
    "/players/{gsis_id}/percentiles",
    response_model=PercentilesResponse,
    response_model_exclude_unset=True,
)
def get_player_percentiles(
    gsis_id: str,
    season: str = Query(
        default=percentiles_repo.CAREER,
        description="A season number, or 'career' to pool every season on file.",
    ),
    position_group: str | None = Query(
        default=None, description="Override the cohort's position group."
    ),
) -> Any:
    if season != percentiles_repo.CAREER and not season.isdigit():
        raise HTTPException(status_code=422, detail="season must be a year or 'career'.")
    return _guard(
        percentiles_repo.player_percentiles,
        gsis_id,
        season=season,
        position_group=position_group,
    )


# --- GET /api/players/{gsis_id}/gamelog --------------------------------------------


class GameRow(BaseModel):
    season: int
    week: int | None = None
    season_type: str | None = None
    game_id: str | None = None
    game_href: str | None = None
    gameday: str | None = None
    game_type: str | None = None
    team: str | None = None
    team_href: str | None = None
    opponent: str | None = None
    opponent_href: str | None = None
    home_away: str | None = None
    team_score: float | None = None
    opp_score: float | None = None
    result: str | None = None
    roof: str | None = None
    surface: str | None = None
    div_game: bool | None = None
    age: float | None = None
    stats: dict[str, float | None]
    offense_snaps: float | None = None
    offense_pct: float | None = None
    defense_snaps: float | None = None
    st_snaps: float | None = None
    started_proxy: bool | None = None
    epa: float | None = None
    plays: int | None = None
    success_rate: float | None = None
    fantasy_standard: float | None = None
    fantasy_ppr: float | None = None
    fantasy_half: float | None = None


class SplitsSummary(BaseModel):
    games: int
    home: int
    away: int
    wins: int
    losses: int
    ties: int


class StartedProxy(BaseModel):
    rule: str
    why: str
    computed_by_us: bool
    first_season: int


class FantasyNote(BaseModel):
    computed_by_us: bool
    formats: list[str]
    columns_used: list[str]
    components_missing: list[str]
    note: str


class GameLogResponse(BaseModel):
    gsis_id: str
    display_name: str | None = None
    position_group: str | None = None
    season: int | None = None
    season_type: str | None = None
    columns: list[StatColumn] | None = None
    rows: list[GameRow]
    games: int | None = None
    totals: dict[str, float | None] | None = None
    averages: dict[str, float | None] | None = None
    splits_summary: SplitsSummary | None = None
    started_proxy: StartedProxy | None = None
    fantasy: FantasyNote | None = None
    note: str | None = None


@router.get(
    "/players/{gsis_id}/gamelog",
    response_model=GameLogResponse,
    response_model_exclude_unset=True,
)
def get_player_gamelog(
    gsis_id: str,
    season: int | None = Query(default=None, description="One season; omit for every season."),
    type: str = Query(default="all", pattern="^(all|reg|post)$", alias="type"),
) -> Any:
    return _found(
        _guard(players_repo.player_gamelog, gsis_id, season=season, season_type=type)
    )


# --- GET /api/players/{gsis_id}/splits ---------------------------------------------


class BucketRow(BaseModel):
    bucket: str
    label: str
    plays: int
    yards: float | None = None
    touchdowns: int | None = None
    first_downs: int | None = None
    epa: float | None = None
    epa_per_play: float | None = None
    success_rate: float | None = None
    yards_per_play: float | None = None
    low_sample: bool
    first_season: int
    last_season: int


class RoleSplits(BaseModel):
    role: str
    label: str
    buckets: list[BucketRow]


class ContextRow(BaseModel):
    group: str
    bucket: str | None = None
    games: int
    passing_yards: float | None = None
    rushing_yards: float | None = None
    receiving_yards: float | None = None
    fantasy_standard: float | None = None
    opponent: str | None = None
    opponent_href: str | None = None


class SplitsUnavailable(BaseModel):
    reason: str
    why: str
    roles: list[str]


class SplitsResponse(BaseModel):
    gsis_id: str
    display_name: str | None = None
    position_group: str | None = None
    scope: str
    season: int | None = None
    season_type: str
    small_sample_plays: int
    method_note: str
    computed_by_us: bool
    unavailable: SplitsUnavailable | None = None
    situation: list[RoleSplits] | None = None
    low_sample_note: str | None = None
    buckets_overlap_note: str | None = None
    game_context: list[ContextRow] | None = None
    opponents: list[ContextRow] | None = None
    note: str | None = None


@router.get(
    "/players/{gsis_id}/splits",
    response_model=SplitsResponse,
    response_model_exclude_unset=True,
)
def get_player_splits(
    gsis_id: str,
    season: str = Query(
        default=percentiles_repo.CAREER,
        description="A season number, or 'career' to sum every season on file.",
    ),
    type: str = Query(default="reg", pattern="^(reg|post)$", alias="type"),
) -> Any:
    if season != percentiles_repo.CAREER and not season.isdigit():
        raise HTTPException(status_code=422, detail="season must be a year or 'career'.")
    return _found(
        _guard(players_repo.player_splits, gsis_id, season=season, season_type=type)
    )


# --- GET /api/players/{gsis_id}/advanced -------------------------------------------


class AdvancedBlock(BaseModel):
    source: str
    name: str
    declared_first_season: int | None = None
    first_season: int | None = None
    last_season: int | None = None
    columns: list[str]
    #: Row shapes differ per source and are passed through as published, so the
    #: page can render whatever the file actually carries rather than a subset we
    #: guessed at.
    rows: list[dict[str, Any]]


class SnapSeason(BaseModel):
    season: int
    games: int
    offense_snaps: float | None = None
    offense_share: float | None = None
    share_note: str


class AdvancedResponse(BaseModel):
    gsis_id: str
    display_name: str | None = None
    position_group: str | None = None
    season: int | None = None
    ngs: list[AdvancedBlock] | None = None
    advstats: list[AdvancedBlock] | None = None
    qbr: AdvancedBlock | None = None
    snaps: list[SnapSeason] | None = None
    coverage: list[SourceWindow]
    coverage_note: str
    note: str | None = None


@router.get(
    "/players/{gsis_id}/advanced",
    response_model=AdvancedResponse,
    response_model_exclude_unset=True,
)
def get_player_advanced(
    gsis_id: str,
    season: int | None = Query(default=None, description="One season; omit for every season."),
) -> Any:
    return _found(_guard(players_repo.player_advanced, gsis_id, season=season))
