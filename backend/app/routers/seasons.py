"""The four endpoints behind the season cockpit: index, hub, standings, week.

Thin, like every other package's router: every query lives in `app.repo.seasons`
(and, for standings, `app.repo.standings` beneath it), and this module's only jobs
are the HTTP contract and the response models.

**Every endpoint declares a response model.** The frontend's TypeScript types are
generated from this OpenAPI schema, so an endpoint returning a bare dict becomes an
untyped hole on the other side.

**`response_model_exclude_unset=True` everywhere here.** The repo layer leaves a key
out of its dict entirely when a block does not apply — a leader category with no
matching column in this deployment, a bracket for a season with no postseason games
yet — and `exclude_unset` carries that through serialisation as a genuinely absent
key rather than a `null` one. A key the repo *did* set to `null` — an unseeded club,
an unplayed game's score — stays in the response, because "there is nothing here"
and "we never computed this" are different answers (mirrors `routers/players.py`).

Not yet wired into `routers/__init__.py::ALL_ROUTERS` — that file is shared across
packages and owned by the integrator.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from ..loader import SeasonBusy
from ..repo import seasons as seasons_repo

router = APIRouter(prefix="/api/seasons", tags=["seasons"])


# --- shared pieces -------------------------------------------------------------


class Colors(BaseModel):
    primary: str | None = None
    secondary: str | None = None


class BrandTeam(BaseModel):
    abbr: str
    name: str | None = None
    logo: str | None = None


# --- GET /api/seasons ----------------------------------------------------------


class SeasonSummary(BaseModel):
    season: int
    href: str
    champion: str | None = None
    champion_href: str | None = None
    top_scoring_team: str | None = None
    top_scoring_team_href: str | None = None
    complete: bool


class SeasonIndex(BaseModel):
    seasons: list[SeasonSummary]
    coverage_href: str


# --- standings (shared by the hub and the standings endpoint) ------------------


class StandingsTeamRow(BaseModel):
    season: int
    team: str
    abbr: str
    code_in_season: str
    conference: str
    division: str
    division_label: str
    games: int
    w: int
    l: int
    t: int
    pct: float | None = None
    pf: int
    pa: int
    diff: int
    mov: float | None = None
    home: str
    away: str
    neutral: str
    neutral_games: int
    neutral_note: str | None = None
    div: str
    conf: str
    home_pct: float | None = None
    away_pct: float | None = None
    div_pct: float | None = None
    conf_pct: float | None = None
    streak: str | None = None
    streak_kind: str | None = None
    streak_length: int | None = None
    longest_win_streak: int | None = None
    division_rank: int
    won_division: bool
    division_title_basis: str | None = None
    seed: int | None = None
    seed_basis: str | None = None
    projected: bool
    tiebreak_note: str | None = None
    tiebreak_ladder: str | None = None
    tiebreak_rules_applied: list[str] | None = None
    made_playoffs: bool
    playoff_round: str | None = None
    playoff_result: str | None = None
    playoff_wins: int
    playoff_losses: int
    srs: float | None = None
    osrs: float | None = None
    dsrs: float | None = None
    sos: float | None = None
    pythagorean_wins: float | None = None
    season_completed: bool
    ranks: dict[str, int | None] = {}


class StandingsGroup(BaseModel):
    label: str
    conference: str | None = None
    division: str | None = None
    teams: list[StandingsTeamRow]


class StandingsPayload(BaseModel):
    season: int
    grouping: str
    view: str | None = None
    groups: list[StandingsGroup]
    teams: int | None = None
    projected: bool
    season_completed: bool
    playoff_seeds: int
    tiebreak_rules_implemented: dict[str, list[str]]
    formulas: dict[str, str]
    note: str


# --- playoff bracket -------------------------------------------------------


class BracketTeam(BaseModel):
    abbr: str
    code_in_season: str
    name: str | None = None
    logo: str | None = None
    seed: int | None = None


class BracketGame(BaseModel):
    game_id: str
    href: str
    home: BracketTeam
    away: BracketTeam
    home_score: int
    away_score: int
    winner: str | None = None


class BracketRound(BaseModel):
    round: str
    round_label: str
    games: list[BracketGame]


class Bracket(BaseModel):
    rounds: list[BracketRound]


# --- EPA quadrant ------------------------------------------------------------


class EpaQuadrantPoint(BaseModel):
    team: str
    logo: str | None = None
    off_epa: float | None = None
    def_epa: float | None = None
    href: str


# --- league leaders ----------------------------------------------------------


class LeaderRow(BaseModel):
    rank: int
    gsis_id: str
    href: str
    player: str
    position: str | None = None
    team: str | None = None
    value: float | None = None
    support: dict[str, float | None] = {}
    note: str | None = None
    computed_by_us: bool | None = None


class SeasonLeaders(BaseModel):
    passing: list[LeaderRow] | None = None
    rushing: list[LeaderRow] | None = None
    receiving: list[LeaderRow] | None = None
    scoring: list[LeaderRow] | None = None
    defense: list[LeaderRow] | None = None
    epa: list[LeaderRow] | None = None


# --- GET /api/seasons/{season} ------------------------------------------------


class SeasonHub(BaseModel):
    season: int
    weeks: list[int]
    standings: StandingsPayload
    bracket: Bracket | None = None
    leaders: SeasonLeaders
    epa_quadrant: list[EpaQuadrantPoint]
    draft_href: str


# --- GET /api/seasons/{season}/week/{week} ------------------------------------


class BiggestPlay(BaseModel):
    description: str | None = None
    wpa: float | None = None
    computed_by_us: bool = True


class WeekGame(BaseModel):
    game_id: str
    href: str
    game_type: str
    played: bool
    home: BrandTeam
    away: BrandTeam
    home_score: int | None = None
    away_score: int | None = None
    overtime: bool | None = None
    div_game: bool | None = None
    spread_line: float | None = None
    ats_result: str | None = None
    wp_sparkline: list[list[float | None]] | None = None
    biggest_play: BiggestPlay | None = None


class WeekLeaders(BaseModel):
    by_epa: list[LeaderRow] | None = None
    by_fantasy: list[LeaderRow] | None = None


class WeekScoreboard(BaseModel):
    season: int
    week: int
    week_type: str | None = None
    week_label: str
    games: list[WeekGame]
    bye_teams: list[str]
    week_leaders: WeekLeaders
    note: str | None = None


# --- endpoints ---------------------------------------------------------------


def _guard(call):
    """Turn the repo's refusals into status codes, and nothing else into one."""
    try:
        return call()
    except seasons_repo.SeasonOutOfWindow as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SeasonBusy as exc:
        # Another season's play-by-play is already materialising. An honest wait,
        # not a failure and not an empty result (SPEC 0.9).
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=SeasonIndex)
def get_season_index() -> Any:
    return _guard(lambda: seasons_repo.season_index())


@router.get(
    "/{season}", response_model=SeasonHub, response_model_exclude_unset=True
)
def get_season_hub(
    season: int = Path(description="Season, e.g. 2024."),
) -> Any:
    return _guard(lambda: seasons_repo.season_hub(season))


@router.get(
    "/{season}/standings",
    response_model=StandingsPayload,
    response_model_exclude_unset=True,
)
def get_season_standings(
    season: int = Path(description="Season, e.g. 2024."),
    view: str = Query(
        default="division",
        description="'division' (eight, or six before 2002, division tables) or "
        "'conference' (two tables in seed order).",
    ),
) -> Any:
    return _guard(lambda: seasons_repo.full_standings(season, view=view))


@router.get(
    "/{season}/week/{week}",
    response_model=WeekScoreboard,
    response_model_exclude_unset=True,
)
def get_week_scoreboard(
    season: int = Path(description="Season, e.g. 2024."),
    week: int = Path(description="Week number — postseason weeks continue the count."),
) -> Any:
    return _guard(lambda: seasons_repo.week_scoreboard(season, week))
