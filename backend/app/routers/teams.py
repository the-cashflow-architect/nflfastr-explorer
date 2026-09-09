"""The four team endpoints: index, franchise hub, team-season cockpit, roster.

All the querying is in `app.repo.teams`; this module declares the response models
and translates the repo's three refusals into status codes. Every endpoint has a
response model on purpose — the frontend's TypeScript types are generated from
this OpenAPI schema, so an endpoint returning a bare dict becomes an untyped hole
on the other side.

The models are deliberately permissive about *absence* and strict about *shape*:
a block with no data is missing from the payload rather than present and empty, so
almost every block is optional and none of them is a list that can be empty and
mean something. `None` is always "we do not know", never zero.

Not yet wired into `routers/__init__.py::ALL_ROUTERS` — that file is shared across
packages and owned elsewhere; see this package's return notes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..loader import SeasonBusy
from ..repo import teams as teams_repo

router = APIRouter(prefix="/api/teams", tags=["teams"])


# --- shared pieces -----------------------------------------------------------


class Colors(BaseModel):
    primary: str | None = None
    secondary: str | None = None


class Record(BaseModel):
    w: int | None = None
    l: int | None = None
    t: int | None = None
    pct: float | None = None
    pf: int | None = None
    pa: int | None = None
    diff: int | None = None


class TeamCard(BaseModel):
    abbr: str
    #: What this club actually played under that season — STL, not LA, in 2001.
    code_in_season: str
    name: str | None = None
    nick: str | None = None
    logo: str | None = None
    logo_espn: str | None = None
    wordmark: str | None = None
    colors: Colors
    href: str
    franchise_href: str
    record: Record | None = None
    division_finish: int | None = None
    won_division: bool | None = None
    made_playoffs: bool | None = None
    playoff_result: str | None = None
    seed: int | None = None


class DivisionPanel(BaseModel):
    division: str
    label: str
    teams: list[TeamCard]


class ConferencePanel(BaseModel):
    conference: str
    divisions: list[DivisionPanel]


class Window(BaseModel):
    first_season: int
    last_season: int


class TeamIndex(BaseModel):
    season: int
    teams: int
    divisions: int
    season_completed: bool
    window: Window
    structure_note: str
    conferences: list[ConferencePanel]
    note: str | None = None


# --- franchise hub -----------------------------------------------------------


class FranchiseTeam(BaseModel):
    abbr: str
    aliases: list[str]
    name: str | None = None
    nick: str | None = None
    logo: str | None = None
    logo_espn: str | None = None
    wordmark: str | None = None
    colors: Colors
    href: str


class Era(BaseModel):
    seasons_from: int
    draft_from: int
    note: str


class FranchiseSummary(BaseModel):
    seasons: int
    games: int
    w: int
    l: int
    t: int
    pct: float | None = None
    points_for: int
    points_against: int
    playoff_appearances: int
    division_titles: int
    postseason_w: int
    postseason_l: int
    super_bowls: int
    best_season: int | None = None
    worst_season: int | None = None


class FranchiseSeason(BaseModel):
    season: int
    href: str
    label: str | None = None
    code_in_season: str
    conference: str | None = None
    division: str | None = None
    w: int
    l: int
    t: int
    pct: float | None = None
    pf: int
    pa: int
    diff: int
    srs: float | None = None
    sos: float | None = None
    division_finish: int | None = None
    won_division: bool | None = None
    made_playoffs: bool | None = None
    playoff_result: str | None = None
    seed: int | None = None
    coach: str | None = None
    coaches: list[str] = Field(default_factory=list)


class CoachRecord(BaseModel):
    coach: str
    seasons: list[int]
    seasons_count: int
    first_season: int
    last_season: int
    w: int
    l: int
    t: int
    playoff_w: int
    playoff_l: int


class CareerLeader(BaseModel):
    rank: int
    gsis_id: str | None = None
    player: str | None = None
    href: str
    value: float | None = None
    first_season: int | None = None
    last_season: int | None = None
    seasons: int | None = None


class SeasonLeader(BaseModel):
    rank: int
    gsis_id: str | None = None
    player: str | None = None
    href: str
    season: int
    value: float | None = None


class LeaderBoard(BaseModel):
    stat: str
    label: str
    career: list[CareerLeader]
    single_season: list[SeasonLeader]


class Leaders(BaseModel):
    since_1999: bool
    first_season: int
    categories: dict[str, list[LeaderBoard]]


class DraftPick(BaseModel):
    season: int
    round: int | None = None
    pick: int | None = None
    player: str | None = None
    gsis_id: str | None = None
    href: str | None = None
    class_href: str
    position: str | None = None
    college: str | None = None
    #: PFR's weighted career Approximate Value. `car_av` is empty in every row
    #: nflverse ships and is deliberately absent here (SPEC 0.4).
    w_av: float | None = None
    dr_av: float | None = None
    seasons_started: int | None = None
    probowls: int | None = None
    allpro: int | None = None
    hof: bool | None = None
    games: int | None = None
    last_season: int | None = None


class DraftHistory(BaseModel):
    first_season: int
    picks: list[DraftPick]
    av_note: str
    note: str | None = None


class Franchise(BaseModel):
    team: FranchiseTeam
    era: Era
    summary: FranchiseSummary
    seasons: list[FranchiseSeason]
    formulas: dict[str, str]
    coaches: list[CoachRecord] | None = None
    coaches_note: str | None = None
    leaders: Leaders | None = None
    leaders_note: str | None = None
    draft: DraftHistory | None = None


# --- team season -------------------------------------------------------------


class SeasonTeam(BaseModel):
    abbr: str
    code_in_season: str
    name: str | None = None
    nick: str | None = None
    logo: str | None = None
    logo_espn: str | None = None
    wordmark: str | None = None
    colors: Colors
    href: str


class RatingTile(BaseModel):
    id: str
    label: str
    value: float | None = None
    rank: int | None = None
    #: How many clubs this rank was taken against. Equal to `league_teams` on a
    #: complete season; smaller only on a partially loaded database.
    of: int
    league_teams: int
    higher_is_better: bool
    computed_by_us: bool
    allowed_side: bool
    formula: str | None = None


class ScheduleRow(BaseModel):
    game_id: str
    game_href: str
    game_type: str
    week: int | None = None
    gameday: str | None = None
    weekday: str | None = None
    gametime: str | None = None
    roof: str | None = None
    surface: str | None = None
    div_game: bool | None = None
    home_away: str
    opponent: str
    opponent_code_in_season: str
    opponent_href: str
    result: str | None = None
    points_for: int | None = None
    points_against: int | None = None
    running_record: str | None = None
    plays: int | None = None
    yards: float | None = None
    turnovers: int | None = None
    first_downs: int | None = None
    epa_per_play: float | None = None
    success_rate: float | None = None
    #: [seconds remaining, this club's win probability], downsampled server-side.
    wp_sparkline: list[list[float]] | None = None
    wp_sparkline_points: int | None = None
    wp_sparkline_side: str | None = None


class TeamStatRow(BaseModel):
    stat: str
    label: str
    offense: float | None = None
    offense_rank: int | None = None
    allowed: float | None = None
    allowed_rank: int | None = None
    of: int
    higher_is_better: bool
    offense_source: str
    allowed_source: str
    allowed_computed_by_us: bool


class AllowedCoverage(BaseModel):
    team_weeks: int
    opponent_rows_matched: int
    complete: bool
    note: str


class TeamStats(BaseModel):
    rows: list[TeamStatRow]
    computed_by_us: list[str]
    method: str
    league_teams: int
    allowed_coverage: AllowedCoverage | None = None


class DriveSide(BaseModel):
    drives: int
    games: int
    drives_per_game: float | None = None
    plays_per_drive: float | None = None
    seconds_per_drive: float | None = None
    #: Yards from the opponent's goal line, the nflfastR convention: a drive
    #: starting on its own 25 reads 75.
    avg_start_yardline_100: float | None = None
    result_mix: dict[str, int]


class DriveProfile(BaseModel):
    computed_by_us: bool
    method: str
    regular_season_only: bool
    team: DriveSide | None = None
    opponent: DriveSide | None = None
    opponent_computed_by_us: bool | None = None


class DriveLogRow(BaseModel):
    game_id: str
    game_href: str
    week: int | None = None
    drive: int | None = None
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


class StatLeader(BaseModel):
    stat: str
    label: str
    gsis_id: str | None = None
    player: str | None = None
    position: str | None = None
    href: str
    value: float | None = None


class SnapLeader(BaseModel):
    pfr_id: str
    player: str | None = None
    games: int
    offense_snaps: float | None = None
    offense_share: float | None = None
    defense_snaps: float | None = None
    defense_share: float | None = None
    st_snaps: float | None = None
    st_share: float | None = None


class SnapCoverage(BaseModel):
    first_season: int
    available: bool
    note: str


class RosterLeaders(BaseModel):
    by_stat: list[StatLeader] | None = None
    by_snap_share: list[SnapLeader] | None = None
    snap_share_coverage: SnapCoverage | None = None


class SpecialTeamsRow(BaseModel):
    stat: str
    label: str
    value: float | None = None


class SpecialTeams(BaseModel):
    rows: list[SpecialTeamsRow]
    #: Named gaps rather than empty charts — the honest empty state.
    not_available: list[str]


class InjuryCoverage(BaseModel):
    first_season: int
    available: bool
    note: str


class InjuryRow(BaseModel):
    gsis_id: str | None = None
    player: str | None = None
    href: str | None = None
    weeks_listed: int
    weeks_out: int
    weeks_doubtful: int
    weeks_questionable: int


class InjurySummary(BaseModel):
    coverage: InjuryCoverage
    rows: list[InjuryRow] | None = None


class SeasonRecord(BaseModel):
    """The standings columns this page shows. Mirrors `repo.teams._RECORD_FIELDS`."""

    games: int | None = None
    w: int | None = None
    l: int | None = None
    t: int | None = None
    pct: float | None = None
    pf: int | None = None
    pa: int | None = None
    diff: int | None = None
    mov: float | None = None
    home: str | None = None
    away: str | None = None
    div: str | None = None
    conf: str | None = None
    streak: str | None = None
    division_rank: int | None = None
    won_division: bool | None = None
    made_playoffs: bool | None = None
    playoff_result: str | None = None
    playoff_wins: int | None = None
    playoff_losses: int | None = None
    seed: int | None = None
    seed_basis: str | None = None
    projected: bool | None = None
    srs: float | None = None
    osrs: float | None = None
    dsrs: float | None = None
    sos: float | None = None
    pythagorean_wins: float | None = None
    ranks: dict[str, int | None] = Field(default_factory=dict)


class SeasonWindows(BaseModel):
    stats_from: int
    charting_from: int
    snap_counts_from: int
    injuries_from: int


class TeamSeason(BaseModel):
    team: SeasonTeam
    season: int
    label: str | None = None
    conference: str
    division: str
    division_label: str
    record: SeasonRecord | None = None
    division_finish: int | None = None
    playoff_result: str | None = None
    coach: str | None = None
    coaches: list[str] = Field(default_factory=list)
    prev_season: int | None = None
    next_season: int | None = None
    roster_href: str
    season_completed: bool
    formulas: dict[str, str]
    windows: SeasonWindows
    allowed_side_method: str
    ratings: list[RatingTile] | None = None
    schedule: list[ScheduleRow] | None = None
    team_stats: TeamStats | None = None
    drive_profile: DriveProfile | None = None
    drive_log: list[DriveLogRow] | None = None
    roster_leaders: RosterLeaders | None = None
    special_teams: SpecialTeams | None = None
    injuries: InjurySummary | None = None


# --- roster ------------------------------------------------------------------


class RosterTeam(BaseModel):
    abbr: str
    code_in_season: str
    name: str | None = None
    logo: str | None = None
    colors: Colors
    href: str


class RosterCoverage(BaseModel):
    snaps_from: int
    snaps_available: bool
    injuries_from: int
    injuries_available: bool
    note: str


class RosterRow(BaseModel):
    gsis_id: str | None = None
    href: str | None = None
    number: int | None = None
    name: str | None = None
    position: str | None = None
    position_group: str | None = None
    depth_chart_position: str | None = None
    status: str | None = None
    age: int | None = None
    age_computed_by_us: bool
    height: float | None = None
    weight: float | None = None
    college: str | None = None
    years_exp: int | None = None
    entry_year: int | None = None
    draft_club: str | None = None
    draft_number: int | None = None
    headshot_url: str | None = None
    stat_line: dict[str, float] | None = None
    injury_status: str | None = None
    snap_rank: int | None = None
    snap_games: int | None = None
    offense_snaps: float | None = None
    offense_share: float | None = None
    defense_snaps: float | None = None
    defense_share: float | None = None
    st_snaps: float | None = None
    st_share: float | None = None
    #: Present, and non-null, only for a player no snap-count row matched. His
    #: share is unknown, which is not the same as zero.
    snap_note: str | None = None


class Roster(BaseModel):
    team: RosterTeam
    season: int
    label: str | None = None
    season_href: str
    position_group: str
    position_groups: list[str]
    counts: dict[str, int]
    coverage: RosterCoverage
    rows: list[RosterRow]
    unmatched_snap_players: int | None = None


# --- endpoints ---------------------------------------------------------------


def _guard(call):
    """Turn the repo's refusals into status codes, and nothing else into one."""
    try:
        return call()
    except teams_repo.UnknownTeam as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except teams_repo.SeasonOutOfWindow as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except teams_repo.SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SeasonBusy as exc:
        # Two older play-by-play seasons are already materialising. Honest wait,
        # not a failure and not an empty result.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=TeamIndex)
def get_team_index(
    season: int | None = Query(
        default=None,
        description="Season to show records for. Defaults to the latest completed season.",
    ),
) -> Any:
    return _guard(lambda: teams_repo.team_index(season))


@router.get("/{abbr}", response_model=Franchise)
def get_franchise(
    abbr: str = Path(description="Team code, current or historical — STL answers as the Rams."),
) -> Any:
    return _guard(lambda: teams_repo.franchise(abbr))


@router.get("/{abbr}/{season}", response_model=TeamSeason)
def get_team_season(
    abbr: str = Path(description="Team code, current or historical."),
    season: int = Path(description="Season."),
) -> Any:
    payload = _guard(lambda: teams_repo.team_season(abbr, season))
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"{abbr.upper()} was not in the league in {season}.",
        )
    return payload


@router.get("/{abbr}/{season}/roster", response_model=Roster)
def get_team_roster(
    abbr: str = Path(description="Team code, current or historical."),
    season: int = Path(description="Season."),
    position_group: str | None = Query(
        default=None,
        description="offense, defense, special_teams or all.",
    ),
) -> Any:
    return _guard(
        lambda: teams_repo.team_roster(abbr, season, position_group=position_group)
    )
