from __future__ import annotations

from .models import FilterDef, SortSpec

COLUMN_CATEGORIES: dict[str, str] = {
    "player_id": "identity",
    "player_name": "identity",
    "player_display_name": "identity",
    "position": "identity",
    "position_group": "identity",
    "team": "team",
    "opponent_team": "team",
    "season": "time",
    "week": "time",
    "season_type": "time",
    "game_id": "time",
    "play_type": "situation",
    "posteam": "team",
    "defteam": "team",
    "down": "situation",
    "ydstogo": "situation",
    "yardline_100": "situation",
    "qtr": "situation",
    "score_differential": "situation",
    "desc": "situation",
}

STAT_PREFIX_CATEGORIES = {
    "passing_": "passing",
    "rushing_": "rushing",
    "receiving_": "receiving",
    "def_": "defense",
    "fantasy_": "fantasy",
    "special_teams_": "special_teams",
}


def categorize_column(name: str) -> str:
    if name in COLUMN_CATEGORIES:
        return COLUMN_CATEGORIES[name]
    for prefix, category in STAT_PREFIX_CATEGORIES.items():
        if name.startswith(prefix):
            return category
    if name in {"epa", "wpa", "wp", "cpoe", "pacr", "racr", "wopr", "dakota"}:
        return "advanced"
    return "other"


PLAYER_WEEKLY_FILTERS: list[FilterDef] = [
    FilterDef(
        id="season",
        field="season",
        label="Season",
        type="multi_select",
        category="time",
        depends_on=[],
        description="Filter by NFL season year.",
    ),
    FilterDef(
        id="week",
        field="week",
        label="Week",
        type="range",
        category="time",
        depends_on=["season"],
        description="Week range within selected season(s).",
    ),
    FilterDef(
        id="season_type",
        field="season_type",
        label="Season Type",
        type="multi_select",
        category="time",
        depends_on=["season"],
        description="Regular season, postseason, or preseason.",
    ),
    FilterDef(
        id="team",
        field="team",
        label="Team",
        type="multi_select",
        category="team",
        depends_on=["season"],
        description="Filter to players on selected team(s).",
    ),
    FilterDef(
        id="opponent_team",
        field="opponent_team",
        label="Opponent",
        type="multi_select",
        category="team",
        depends_on=["season", "team"],
        description="Filter to games vs. specific opponent(s).",
    ),
    FilterDef(
        id="position",
        field="position",
        label="Position",
        type="multi_select",
        category="identity",
        depends_on=["season"],
        description="Primary position (QB, WR, RB, etc.).",
    ),
    FilterDef(
        id="position_group",
        field="position_group",
        label="Position Group",
        type="multi_select",
        category="identity",
        depends_on=["season"],
        description="Grouped position bucket.",
    ),
    FilterDef(
        id="player",
        field="player_display_name",
        label="Player",
        type="search",
        category="identity",
        depends_on=["season", "team", "position"],
        description="Search by player name.",
    ),
    FilterDef(
        id="min_pass_yards",
        field="passing_yards",
        label="Min Pass Yds",
        type="range",
        category="passing",
        depends_on=["position"],
        description="Minimum passing yards in the row.",
    ),
    FilterDef(
        id="min_rush_yards",
        field="rushing_yards",
        label="Min Rush Yds",
        type="range",
        category="rushing",
        depends_on=["position"],
        description="Minimum rushing yards in the row.",
    ),
    FilterDef(
        id="min_rec_yards",
        field="receiving_yards",
        label="Min Rec Yds",
        type="range",
        category="receiving",
        depends_on=["position"],
        description="Minimum receiving yards in the row.",
    ),
]

PLAYER_SEASON_FILTERS = [
    f for f in PLAYER_WEEKLY_FILTERS if f.id not in {"week"}
]

PBP_FILTERS: list[FilterDef] = [
    FilterDef(
        id="season",
        field="season",
        label="Season",
        type="multi_select",
        category="time",
        depends_on=[],
    ),
    FilterDef(
        id="week",
        field="week",
        label="Week",
        type="range",
        category="time",
        depends_on=["season"],
    ),
    FilterDef(
        id="posteam",
        field="posteam",
        label="Offense",
        type="multi_select",
        category="team",
        depends_on=["season"],
    ),
    FilterDef(
        id="defteam",
        field="defteam",
        label="Defense",
        type="multi_select",
        category="team",
        depends_on=["season", "posteam"],
    ),
    FilterDef(
        id="play_type",
        field="play_type",
        label="Play Type",
        type="multi_select",
        category="situation",
        depends_on=["season"],
        description="pass, run, punt, field_goal, kickoff, etc.",
    ),
    FilterDef(
        id="down",
        field="down",
        label="Down",
        type="multi_select",
        category="situation",
        depends_on=["play_type"],
    ),
    FilterDef(
        id="qtr",
        field="qtr",
        label="Quarter",
        type="multi_select",
        category="situation",
        depends_on=["season"],
    ),
    FilterDef(
        id="passer",
        field="passer_player_name",
        label="Passer",
        type="search",
        category="identity",
        depends_on=["season", "posteam", "play_type"],
    ),
    FilterDef(
        id="receiver",
        field="receiver_player_name",
        label="Receiver",
        type="search",
        category="identity",
        depends_on=["season", "posteam", "play_type"],
    ),
    FilterDef(
        id="rusher",
        field="rusher_player_name",
        label="Rusher",
        type="search",
        category="identity",
        depends_on=["season", "posteam", "play_type"],
    ),
    FilterDef(
        id="min_epa",
        field="epa",
        label="Min EPA",
        type="range",
        category="advanced",
        depends_on=["play_type"],
    ),
    FilterDef(
        id="score_diff",
        field="score_differential",
        label="Score Diff",
        type="range",
        category="situation",
        depends_on=["season"],
    ),
]

DEFAULT_PLAYER_WEEKLY_COLUMNS = [
    "season",
    "week",
    "player_display_name",
    "position",
    "team",
    "opponent_team",
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "fantasy_points_ppr",
    "epa",
]

DEFAULT_PLAYER_SEASON_COLUMNS = [
    col for col in DEFAULT_PLAYER_WEEKLY_COLUMNS if col != "week"
]

DEFAULT_PBP_COLUMNS = [
    "season",
    "week",
    "posteam",
    "defteam",
    "down",
    "ydstogo",
    "yardline_100",
    "play_type",
    "desc",
    "passer_player_name",
    "receiver_player_name",
    "rusher_player_name",
    "yards_gained",
    "epa",
    "wp",
    "wpa",
]

DEFAULT_PLAYER_WEEKLY_SORT = [
    SortSpec(field="season", direction="desc"),
    SortSpec(field="week", direction="desc"),
    SortSpec(field="epa", direction="desc"),
]

DEFAULT_PLAYER_SEASON_SORT = [
    SortSpec(field="season", direction="desc"),
    SortSpec(field="epa", direction="desc"),
]

DEFAULT_PBP_SORT = [
    SortSpec(field="season", direction="desc"),
    SortSpec(field="week", direction="desc"),
    SortSpec(field="epa", direction="desc"),
]
