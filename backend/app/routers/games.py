"""The two game endpoints: the cockpit, and the play log behind it.

All the querying is in `app.repo.games`; this module declares the response models
and turns the repo's refusals into status codes. Every endpoint declares a model
on purpose — the frontend's TypeScript types are generated from this OpenAPI
schema, so an endpoint returning a bare dict becomes an untyped hole on the other
side.

The models are permissive about *absence* and strict about *shape*. Almost every
block is optional, and both endpoints are served with
`response_model_exclude_unset=True`, so a block the repo left out of the payload
is missing from the JSON rather than present and null — which is the difference
between "this game predates snap counts" and "this game had no snaps". `None` is
always "we do not know", never zero.

`SeasonBusy` from the loader — two older seasons already materialising — becomes a
503 with a sentence naming the season the visitor is waiting on. It is never an
empty play list, which would read as "this game had no plays".

Not wired into `routers/__init__.py::ALL_ROUTERS` — that file is shared across
packages and this one does not own it; see this package's return notes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from ..loader import SeasonBusy
from ..repo import games as games_repo

router = APIRouter(prefix="/api", tags=["games"])


# --- shared pieces -----------------------------------------------------------


class Colors(BaseModel):
    primary: str | None = None
    secondary: str | None = None


class Record(BaseModel):
    w: int
    l: int
    t: int


class TeamSide(BaseModel):
    side: str
    abbr: str | None = None
    #: What this club actually played under that season — STL, not LA, in 2001.
    code_in_season: str | None = None
    name: str | None = None
    nick: str | None = None
    logo: str | None = None
    logo_espn: str | None = None
    wordmark: str | None = None
    colors: Colors
    score: int | None = None
    href: str | None = None
    franchise_href: str | None = None
    coach: str | None = None
    starting_qb: str | None = None
    record_entering: Record | None = None


class Header(BaseModel):
    """Only the fields the schedule file actually carries.

    Attendance, game duration and TV network are in no verified source, so they
    are absent here rather than present and empty.
    """

    game_id: str
    season: int | None = None
    week: int | None = None
    game_type: str | None = None
    gameday: str | None = None
    weekday: str | None = None
    gametime: str | None = None
    location: str | None = None
    stadium: str | None = None
    stadium_id: str | None = None
    roof: str | None = None
    surface: str | None = None
    temp: float | None = None
    wind: float | None = None
    referee: str | None = None
    div_game: bool | None = None
    overtime: bool | None = None
    away_rest: int | None = None
    home_rest: int | None = None
    home: TeamSide
    away: TeamSide
    record_note: str | None = None


class Status(BaseModel):
    played: bool
    label: str
    note: str | None = None


class Final(BaseModel):
    home: int
    away: int
    winner: str | None = None
    tie: bool
    margin: int


class Coverage(BaseModel):
    first_season: int
    last_season: int
    charting_first_season: int
    air_yards_charted: bool
    snap_counts_first_season: int
    snap_counts_available: bool
    note: str


# --- line score and scoring --------------------------------------------------


class Period(BaseModel):
    period: int
    label: str
    home: int
    away: int


class LineScore(BaseModel):
    periods: list[Period]
    home_total: int
    away_total: int
    final_home: int | None = None
    final_away: int | None = None
    source: str
    #: Set only when the scoring plays do not add up to the schedule file's final.
    note: str | None = None


class ScoringPlay(BaseModel):
    play_id: int | None = None
    quarter: int | None = None
    period_label: str
    clock: str | None = None
    seconds_remaining: int | None = None
    team: str | None = None
    posteam: str | None = None
    scoring_type: str | None = None
    play_type: str | None = None
    description: str | None = None
    scorer: str | None = None
    scorer_href: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    anchor: str


# --- win probability ---------------------------------------------------------


class WpPoint(BaseModel):
    play_id: int | None = None
    secs: int | None = None
    home_wp: float | None = None
    home_score: int | None = None
    away_score: int | None = None


class WpMarker(BaseModel):
    play_id: int | None = None
    secs: int | None = None
    team: str | None = None
    scoring_type: str | None = None
    label: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class BiggestSwing(BaseModel):
    play_id: int | None = None
    secs: int | None = None
    delta: float | None = None
    home_wp_before: float | None = None
    home_wp_after: float | None = None
    description: str | None = None
    computed_by_us: bool
    note: str


class WinProbability(BaseModel):
    points: list[WpPoint]
    points_stored: int
    markers: list[WpMarker]
    biggest_swing: BiggestSwing | None = None
    note: str


# --- team stats --------------------------------------------------------------


class StatContext(BaseModel):
    """A single game's standing among that season's team-games — never 1-of-32."""

    percentile: float | None = None
    n: int
    season: int


class TeamStatRow(BaseModel):
    stat: str
    label: str
    unit: str
    higher_is_better: bool
    home: float | None = None
    away: float | None = None
    home_context: StatContext | None = None
    away_context: StatContext | None = None


class TeamStats(BaseModel):
    rows: list[TeamStatRow]
    team_games_in_season: int
    computed_by_us: bool
    percentile_method: str
    note: str


# --- drives ------------------------------------------------------------------


class Drive(BaseModel):
    drive: int | None = None
    team: str | None = None
    opponent: str | None = None
    plays: int | None = None
    time_of_possession: str | None = None
    top_seconds: int | None = None
    first_downs: int | None = None
    result: str | None = None
    scored: bool | None = None
    start_yard_line: str | None = None
    end_yard_line: str | None = None
    start_yardline_100: int | None = None
    end_yardline_100: int | None = None
    #: Computed by us from the two resolved yard lines; see the drives note.
    net_yards: int | None = None


# --- box score and snaps -----------------------------------------------------


class BoxColumn(BaseModel):
    id: str
    label: str


class BoxRow(BaseModel):
    player_id: str | None = None
    name: str | None = None
    position: str | None = None
    team: str | None = None
    href: str | None = None
    values: dict[str, float | None]


class BoxCategory(BaseModel):
    id: str
    label: str
    columns: list[BoxColumn]
    home: list[BoxRow]
    away: list[BoxRow]


class BoxScore(BaseModel):
    categories: list[BoxCategory]
    charting_note: str | None = None
    note: str


class SnapRow(BaseModel):
    gsis_id: str | None = None
    href: str | None = None
    name: str | None = None
    position: str | None = None
    team: str | None = None
    offense_snaps: float | None = None
    offense_pct: float | None = None
    defense_snaps: float | None = None
    defense_pct: float | None = None
    st_snaps: float | None = None
    st_pct: float | None = None


class Snaps(BaseModel):
    home: list[SnapRow]
    away: list[SnapRow]
    #: Players no pfr_id matched. They keep their snaps and lose their link.
    unmatched_players: int | None = None
    first_season: int
    note: str


# --- betting, officials, play log --------------------------------------------


class Betting(BaseModel):
    spread_line: float | None = None
    total_line: float | None = None
    home_moneyline: float | None = None
    away_moneyline: float | None = None
    home_spread_odds: float | None = None
    away_spread_odds: float | None = None
    over_odds: float | None = None
    under_odds: float | None = None
    home_margin: int | None = None
    total_points: int | None = None
    ats_result: str | None = None
    ou_result: str | None = None
    computed_by_us: list[str] | None = None
    note: str


class Official(BaseModel):
    name: str
    position: str | None = None
    jersey_number: str | None = None


class PlayLogInfo(BaseModel):
    href: str
    source: str
    ready: bool
    #: Absent until the season's plays are reachable without a download.
    total_plays: int | None = None
    note: str | None = None


class Game(BaseModel):
    game_id: str
    season: int
    week: int | None = None
    header: Header
    status: Status
    coverage: Coverage
    season_href: str
    week_href: str | None = None
    final: Final | None = None
    line_score: LineScore | None = None
    scoring: list[ScoringPlay] | None = None
    win_probability: WinProbability | None = None
    team_stats: TeamStats | None = None
    drives: list[Drive] | None = None
    box_score: BoxScore | None = None
    snaps: Snaps | None = None
    betting: Betting | None = None
    officials: list[Official] | None = None
    play_log: PlayLogInfo | None = None


# --- play log ----------------------------------------------------------------


class Play(BaseModel):
    play_id: int | None = None
    quarter: int | None = None
    period_label: str
    clock: str | None = None
    seconds_remaining: int | None = None
    down: int | None = None
    ydstogo: int | None = None
    yardline_100: int | None = None
    posteam: str | None = None
    defteam: str | None = None
    play_type: str | None = None
    description: str | None = None
    yards_gained: float | None = None
    epa: float | None = None
    wpa: float | None = None
    wp: float | None = None
    success: bool | None = None
    first_down: bool | None = None
    touchdown: bool | None = None
    drive: int | None = None
    anchor: str
    #: Present only from the charting era; before it nobody wrote air yards down.
    air_yards: float | None = None


class FilterOptions(BaseModel):
    teams: list[str]
    quarters: list[int]
    downs: list[int]
    play_types: list[str]


class PlayLog(BaseModel):
    game_id: str
    season: int
    played: bool
    page: int
    page_size: int
    source: str
    coverage: Coverage
    #: Absent for a game that has not been played — an empty list would read as
    #: "this game had no plays".
    rows: list[Play] | None = None
    total: int | None = None
    filters_applied: dict[str, Any] | None = None
    filter_options: FilterOptions | None = None
    coverage_note: str | None = None
    note: str | None = None


# --- endpoints ---------------------------------------------------------------


def _guard(call):
    """Turn the repo's refusals into status codes, and nothing else into one."""
    try:
        return call()
    except games_repo.UnknownGame as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except games_repo.SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except games_repo.SeasonLoading as exc:
        # The season's plays are materialising. An honest wait with the season
        # named — never a failure, and never an empty result.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SeasonBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/games/{game_id}",
    response_model=Game,
    response_model_exclude_unset=True,
    summary="Everything on the game page except the play log",
)
def get_game(
    game_id: str = Path(description="Schedule id, e.g. 2024_01_BAL_KC."),
) -> Any:
    return _guard(lambda: games_repo.game(game_id))


@router.get(
    "/games/{game_id}/plays",
    response_model=PlayLog,
    response_model_exclude_unset=True,
    summary="The filterable play log, loaded separately because it is large",
)
def get_game_plays(
    game_id: str = Path(description="Schedule id, e.g. 2024_01_BAL_KC."),
    team: str | None = Query(
        default=None,
        description="Only plays with this club on offence. Historical codes resolve.",
    ),
    quarter: int | None = Query(default=None, ge=1, le=6),
    down: int | None = Query(default=None, ge=1, le=4),
    play_type: str | None = Query(
        default=None, description="nflfastR play type, e.g. pass, run, punt."
    ),
    min_abs_epa: float | None = Query(
        default=None,
        ge=0,
        description="Only plays whose EPA is at least this far from zero. A play "
        "with no EPA is excluded rather than counted as zero.",
    ),
    drive: int | None = Query(
        default=None, ge=1, description="Only this drive, as numbered in the game."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=games_repo.DEFAULT_PAGE_SIZE, ge=1, le=games_repo.MAX_PAGE_SIZE
    ),
) -> Any:
    return _guard(
        lambda: games_repo.plays(
            game_id,
            team=team,
            quarter=quarter,
            down=down,
            play_type=play_type,
            min_abs_epa=min_abs_epa,
            drive=drive,
            page=page,
            page_size=page_size,
        )
    )
