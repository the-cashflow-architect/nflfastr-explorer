from __future__ import annotations

from .models import FilterDef, SortSpec

COLUMN_CATEGORIES: dict[str, str] = {
    "player_id": "identity",
    "player_name": "identity",
    "player_display_name": "identity",
    "position": "identity",
    "position_group": "identity",
    "team": "team",
    "recent_team": "team",
    "opponent_team": "team",
    "games": "other",
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
    "play_id": "situation",
    "game_seconds_remaining": "situation",
    "passer_player_name": "identity",
    "receiver_player_name": "identity",
    "rusher_player_name": "identity",
    "yards_gained": "play",
    "air_yards": "play",
    "yards_after_catch": "play",
    "touchdown": "play",
    "pass_touchdown": "play",
    "rush_touchdown": "play",
    "interception": "play",
    "complete_pass": "play",
    "sack": "play",
    "first_down": "play",
    "pass": "play",
    "rush": "play",
    # Core counting stats that don't carry their category's prefix.
    "completions": "passing",
    "attempts": "passing",
    "carries": "rushing",
    "receptions": "receiving",
    "targets": "receiving",
    # Sack production is recorded under the passer's line, not a "sacks_"
    # prefix, so it needs an explicit entry.
    "sacks_suffered": "passing",
    "sack_yards_lost": "passing",
    "sack_fumbles": "passing",
    "sack_fumbles_lost": "passing",
    # Efficiency shares, alongside pacr/racr/wopr below.
    "target_share": "advanced",
    "air_yards_share": "advanced",
    # Return production doesn't carry a shared prefix with special_teams_tds.
    "punt_returns": "returns",
    "punt_return_yards": "returns",
    "kickoff_returns": "returns",
    "kickoff_return_yards": "returns",
    "special_teams_tds": "returns",
    "penalties": "penalties",
    "penalty_yards": "penalties",
    # Fumble stats not already covered by a passing/rushing/receiving prefix.
    "fumble_recovery_own": "ball_security",
    "fumble_recovery_yards_own": "ball_security",
    "fumble_recovery_opp": "ball_security",
    "fumble_recovery_yards_opp": "ball_security",
    "fumble_recovery_tds": "ball_security",
    "fumbles_forced_by_opp": "ball_security",
    "fumbles_not_forced": "ball_security",
    "fumbles_out_of_bounds": "ball_security",
    "fumbles_total": "ball_security",
    "fumbles_lost_total": "ball_security",
    "misc_yards": "other",
    # A portrait URL, not a stat — never offered in a column/stat picker.
    "headshot_url": "meta",
    # nflverse encodes these as delimited strings (e.g. field-goal distances
    # per kick), not a single scalar, so they don't belong in a stat table.
    "fg_made_list": "meta",
    "fg_missed_list": "meta",
    "fg_blocked_list": "meta",
    "gwfg_distance_list": "meta",
}

STAT_PREFIX_CATEGORIES = {
    "passing_": "passing",
    "rushing_": "rushing",
    "receiving_": "receiving",
    "def_": "defense",
    "fantasy_": "fantasy",
    "special_teams_": "returns",
    "fg_": "kicking",
    "pat_": "kicking",
    "gwfg_": "kicking",
    "pt_": "punting",
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
        type="multi_select",
        category="time",
        depends_on=["season"],
        description="Pick any combination of weeks — a full season, a single week, a range, or a scattered set.",
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
    # Numeric stat filters (passing yards, TDs, tackles, ...) are no longer
    # hand-curated here — the frontend generates one for every numeric
    # column on the dataset, so any stat can be filtered, not just the
    # three someone thought to add.
]


def _for_season(f: FilterDef) -> FilterDef:
    # player_season has no per-game opponent, and its team column is named
    # "recent_team" (a player can change teams mid-season) rather than
    # "team" — remap so the same filter id still points at a real column.
    if f.id == "team":
        return FilterDef(**{**f.model_dump(), "field": "recent_team"})
    return f


PLAYER_SEASON_FILTERS = [
    _for_season(f) for f in PLAYER_WEEKLY_FILTERS if f.id not in {"week", "opponent_team"}
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
        type="multi_select",
        category="time",
        depends_on=["season"],
        description="Pick any combination of weeks — a full season, a single week, a range, or a scattered set.",
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

# A neutral, position-agnostic box score. This is the fallback before any
# stat view is chosen on the frontend, so it deliberately excludes fantasy
# points and advanced efficiency metrics — those live in their own views.
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
    "passing_interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
]

# player_season has no per-game opponent, and its team column is
# "recent_team" rather than "team" — see PLAYER_SEASON_FILTERS above.
DEFAULT_PLAYER_SEASON_COLUMNS = [
    "recent_team" if col == "team" else col
    for col in DEFAULT_PLAYER_WEEKLY_COLUMNS
    if col not in {"week", "opponent_team"}
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

# Neutral chronological order — there's no single stat that ranks a QB
# against a WR fairly, so the default avoids picking one (previously
# fantasy_points_ppr, which favored skill-position players and baked a
# fantasy-football lens into the very first thing anyone saw). The frontend
# applies a position-appropriate sort once a stat view is chosen.
DEFAULT_PLAYER_WEEKLY_SORT = [
    SortSpec(field="season", direction="desc"),
    SortSpec(field="week", direction="desc"),
]

DEFAULT_PLAYER_SEASON_SORT = [
    SortSpec(field="season", direction="desc"),
]

DEFAULT_PBP_SORT = [
    SortSpec(field="season", direction="desc"),
    SortSpec(field="week", direction="desc"),
    SortSpec(field="epa", direction="desc"),
]
