"""The catalogue of everything we load, and the rules for keeping it fresh.

One registry, read by the loader, by `/api/coverage`, and by the glossary. A
dataset's season window is declared here exactly once; no page, endpoint or piece
of frontend copy is allowed to hardcode a coverage year, because the moment two
places disagree the site starts lying about what it knows.

Two ideas do most of the work:

* **A completed season never changes.** The 2014 season is finished; re-downloading
  it on a 24-hour clock is pure cost. Only the current season and the schedule file
  carry a TTL. This is what makes covering 27 seasons cheaper per day than covering
  four was.
* **Projection is declared, not discovered.** Play-by-play is 372 columns wide and we
  read 77 of them. The projection is pushed into the parquet reader, so the columns
  we skip are never decompressed, never allocated, and never counted against the
  128 MB DuckDB budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .etl.alignment import FIRST_SEASON

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
NFLDATA_RAW = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"
NFLFASTR_RAW = "https://raw.githubusercontent.com/nflverse/nflfastR-data/master"

Grain = Literal["single", "season"]


@dataclass(frozen=True)
class Source:
    """One nflverse file, or one per-season family of files."""

    id: str
    table: str
    name: str
    description: str
    url: str
    grain: Grain
    #: Inclusive season window this source actually covers. `None` for `single`
    #: files whose rows span every season (players, draft picks, NGS).
    first_season: int | None = None
    last_season: int | None = None
    #: Columns to read. `None` reads the file as published.
    columns: tuple[str, ...] | None = None
    #: Hours before a *current-season* file is re-fetched. Completed seasons are
    #: fetched once and never again; `single` files use this as their whole policy.
    ttl_hours: int = 24
    #: Files whose absence is expected rather than an error (a season that has not
    #: started, a source that begins later than our floor).
    optional: bool = False
    #: Human-readable caveat surfaced by `/api/coverage` and the era badges.
    coverage_note: str = ""
    format: Literal["parquet", "csv"] = "parquet"
    #: Columns holding a team code, rewritten to the current franchise code as the
    #: file loads. Sources disagree about whether a 1999 row says STL or LA;
    #: normalising here means nothing downstream has to know or care.
    team_columns: tuple[str, ...] = ()
    #: Applied as a WHERE clause at load. Used to drop the single unattributed
    #: row nflverse emits in each weekly team and player file.
    where_sql: str | None = None
    #: Extra columns copied from an existing one under a second name, as
    #: (source column, alias). The season player files call the team column
    #: `recent_team` while the weekly file calls it `team`; rather than make
    #: every query that touches both remember which is which — and fail with a
    #: binder error the first time it forgets — the alias is added here so every
    #: table answers to `team`. The original name is kept, because `recent_team`
    #: carries a real caveat (for a player traded mid-season it is the *last*
    #: team, not the one he played each game for) that the glossary explains.
    alias_columns: tuple[tuple[str, str], ...] = ()

    def url_for(self, season: int | None = None) -> str:
        return self.url.format(season=season) if self.grain == "season" else self.url

    def seasons(self, through: int) -> list[int]:
        if self.grain != "season":
            return []
        first = self.first_season or FIRST_SEASON
        last = min(self.last_season or through, through)
        return list(range(first, last + 1))


# --- Play-by-play projection -------------------------------------------------
#
# 77 of 372 columns, verified present in every season from 1999 to 2025. Every one
# is used by a derived table or the play log; adding a column here means adding the
# ETL that consumes it, or it is dead weight on every season we read.
PBP_COLUMNS: tuple[str, ...] = (
    # where and when
    "season", "week", "game_id", "play_id", "season_type",
    "posteam", "defteam", "home_team", "away_team",
    "down", "ydstogo", "yardline_100", "qtr",
    "quarter_seconds_remaining", "half_seconds_remaining", "game_seconds_remaining",
    "score_differential", "total_home_score", "total_away_score",
    # what happened
    "play_type", "pass", "rush", "special", "desc",
    # who did it — ids, not just names: every derived table keys on gsis_id
    "passer_player_id", "passer_player_name",
    "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",
    "interception_player_id", "fumbled_1_player_id",
    "td_player_id", "td_player_name", "td_team",
    "penalty_player_id", "penalty_team", "penalty_yards", "penalty_type",
    # how well
    "yards_gained", "air_yards", "yards_after_catch",
    "epa", "qb_epa", "wp", "home_wp", "wpa", "cpoe",
    "success", "series", "series_success",
    # outcomes
    "touchdown", "pass_touchdown", "rush_touchdown", "interception",
    "complete_pass", "sack", "first_down", "fumble_lost", "safety",
    "two_point_attempt", "field_goal_attempt", "field_goal_result",
    "punt_attempt", "kickoff_attempt", "extra_point_attempt", "sp",
    # drives
    "fixed_drive", "fixed_drive_result", "drive_play_count",
    "drive_time_of_possession", "drive_first_downs",
    "drive_start_yard_line", "drive_end_yard_line",
    "drive_game_clock_start", "drive_inside20", "drive_ended_with_score",
)

# Air yards were not charted before 2006. Everything downstream of them is NULL for
# 1999-2005 and must be written as NULL, never zero — a zero would read as "he threw
# it at the line of scrimmage" instead of "nobody wrote it down".
CHARTING_FIRST_SEASON = 2006
AIR_YARDS_DEPENDENT = ("air_yards", "yards_after_catch", "cpoe")

# Next Gen Stats begin in 2016; PFR's charting-based advanced stats in 2018.
NGS_FIRST_SEASON = 2016
ADVSTATS_FIRST_SEASON = 2018
SNAP_COUNTS_FIRST_SEASON = 2012
INJURIES_FIRST_SEASON = 2009
QBR_FIRST_SEASON = 2006
# The draft file starts in 1980, not at the first NFL draft. It is still the only
# block on the site that reaches before 1999.
DRAFT_FIRST_SEASON = 1980


SOURCES: tuple[Source, ...] = (
    Source(
        id="games",
        table="games",
        name="Games & schedules",
        description=(
            "Every scheduled and completed game since 1999 with scores, coaches, "
            "starting quarterbacks, officials, venue, weather and closing betting lines. "
            "The spine of standings, schedules, game pages and every date on the site."
        ),
        url=f"{NFLDATA_RAW}/games.csv",
        grain="single",
        format="csv",
        first_season=FIRST_SEASON,
        ttl_hours=12,
        team_columns=("home_team", "away_team"),
        coverage_note="Includes future scheduled games, which have no score yet.",
    ),
    Source(
        id="teams_meta",
        table="teams_meta",
        name="Team identity",
        description="Team names, colours and logos. Current membership only — never used to group a historical season.",
        url=f"{NFLFASTR_RAW}/teams_colors_logos.csv",
        grain="single",
        format="csv",
        ttl_hours=24 * 30,
        coverage_note="Division shown here is the present-day one; historical alignment comes from our own season table.",
    ),
    Source(
        id="players",
        table="players",
        name="Player biographies",
        description="Birth date, height, weight, college, jersey, draft line, rookie and final season, and cross-system ids for every player nflverse knows.",
        url=f"{RELEASE}/players/players.parquet",
        grain="single",
        columns=(
            "gsis_id", "display_name", "first_name", "last_name", "football_name",
            "position", "position_group", "jersey_number", "birth_date", "height",
            "weight", "headshot", "college_name", "college_conference",
            "rookie_season", "last_season", "latest_team", "status",
            "years_of_experience", "draft_year", "draft_round", "draft_pick",
            "draft_team", "pfr_id", "espn_id",
        ),
        coverage_note="pfr_id — the key that reaches snap counts and PFR advanced stats — is present for about 91% of players.",
    ),
    Source(
        id="draft_picks",
        table="draft_picks",
        name="Draft picks",
        description="Every pick since 1936 with the career that followed it: games, seasons started, Pro Bowls, All-Pros, Hall of Fame, and PFR's weighted Approximate Value.",
        url=f"{RELEASE}/draft_picks/draft_picks.parquet",
        grain="single",
        first_season=DRAFT_FIRST_SEASON,
        columns=(
            "season", "round", "pick", "team", "gsis_id", "pfr_player_id",
            "pfr_player_name", "hof", "position", "category", "side", "college",
            "age", "to", "allpro", "probowls", "seasons_started", "w_av", "dr_av",
            "games", "pass_completions", "pass_attempts", "pass_yards", "pass_tds",
            "pass_ints", "rush_atts", "rush_yards", "rush_tds", "receptions",
            "rec_yards", "rec_tds", "def_solo_tackles", "def_ints", "def_sacks",
        ),
        coverage_note=(
            "The only block on the site with pre-1999 history: 1980 onward. Team codes "
            "here are Pro-Football-Reference's, and three of them mean different "
            "franchises in different decades, so they are resolved by season rather "
            "than mapped blindly. car_av is empty in the "
            "source for every row; w_av (weighted career AV) is the usable figure and "
            "exists for drafted players only."
        ),
    ),
    Source(
        id="combine",
        table="combine",
        name="Scouting combine",
        description="Measurables and workout numbers for combine invitees.",
        url=f"{RELEASE}/combine/combine.parquet",
        grain="single",
        coverage_note="Joined on pfr_id, which about 83% of combine rows carry. Rows without it are not matched rather than guessed.",
    ),
    Source(
        id="player_season_reg",
        table="player_season_reg",
        name="Player season stats (regular season)",
        description="Regular-season totals and rates per player-season, from nflfastR's calculated stats.",
        url=f"{RELEASE}/stats_player/stats_player_reg_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        # The season files call the team column `recent_team`; only the weekly
        # file has `team`. Naming the wrong one here was a silent no-op — the
        # projection skips a column the file does not have — which left the
        # relocated franchises keyed on codes no other table uses.
        team_columns=("recent_team", "team"),
        alias_columns=(("recent_team", "team"),),
    ),
    Source(
        id="player_season_post",
        table="player_season_post",
        name="Player season stats (postseason)",
        description="Postseason totals per player-season.",
        url=f"{RELEASE}/stats_player/stats_player_post_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        optional=True,
        alias_columns=(("recent_team", "team"),),
        team_columns=("recent_team", "team"),
    ),
    Source(
        id="player_week",
        table="player_week",
        name="Player game stats",
        description="One row per player per game — the game log, and the base for every weekly leader and split.",
        url=f"{RELEASE}/stats_player/stats_player_week_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        team_columns=("team", "opponent_team"),
        where_sql='"team" IS NOT NULL',
    ),
    Source(
        id="team_season",
        table="team_season",
        name="Team season stats",
        description="Team regular-season totals, including defensive production, kicking and punting.",
        url=f"{RELEASE}/stats_team/stats_team_reg_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        coverage_note=(
            "def_* columns are what a defence produced (sacks, interceptions, tackles) — "
            "not what it allowed. Allowed-side figures are computed by summing opponents' "
            "offensive rows."
        ),
        team_columns=("team",),
        where_sql='"team" IS NOT NULL',
    ),
    Source(
        id="team_week",
        table="team_week",
        name="Team game stats",
        description="Team totals per game, and the source of every allowed-side figure via a self-join on opponents.",
        url=f"{RELEASE}/stats_team/stats_team_week_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        team_columns=("team", "opponent_team"),
        where_sql='"team" IS NOT NULL',
    ),
    Source(
        id="rosters",
        table="rosters",
        name="Rosters",
        description="Season rosters with jersey, depth-chart position, physicals, college and entry year.",
        url=f"{RELEASE}/rosters/roster_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        team_columns=("team", "draft_club"),
        columns=(
            "season", "team", "position", "depth_chart_position", "jersey_number",
            "status", "full_name", "gsis_id", "pfr_id", "birth_date", "height",
            "weight", "college", "years_exp", "entry_year", "draft_club",
            "draft_number", "headshot_url",
        ),
    ),
    Source(
        id="snap_counts",
        table="snap_counts",
        name="Snap counts",
        description="Offensive, defensive and special-teams snaps and shares per player per game.",
        url=f"{RELEASE}/snap_counts/snap_counts_{{season}}.parquet",
        grain="season",
        first_season=SNAP_COUNTS_FIRST_SEASON,
        coverage_note="From 2012. Matched to players through pfr_id, which resolves about 99.8% of rows.",
        team_columns=("team", "opponent"),
    ),
    Source(
        id="injuries",
        table="injuries",
        name="Injury reports",
        description="Weekly practice and game-status designations.",
        url=f"{RELEASE}/injuries/injuries_{{season}}.parquet",
        grain="season",
        first_season=INJURIES_FIRST_SEASON,
        coverage_note="From 2009.",
        team_columns=("team",),
    ),
    Source(
        id="ngs_passing",
        table="ngs_passing",
        name="Next Gen Stats — passing",
        description="Time to throw, aggressiveness, expected completion percentage and completion percentage above expectation.",
        url=f"{RELEASE}/nextgen_stats/ngs_passing.parquet",
        grain="single",
        first_season=NGS_FIRST_SEASON,
        coverage_note="From 2016. All seasons ship in one file; there is no per-season variant.",
    ),
    Source(
        id="ngs_rushing",
        table="ngs_rushing",
        name="Next Gen Stats — rushing",
        description="Efficiency, time behind the line, yards over expected.",
        url=f"{RELEASE}/nextgen_stats/ngs_rushing.parquet",
        grain="single",
        first_season=NGS_FIRST_SEASON,
        coverage_note="From 2016.",
    ),
    Source(
        id="ngs_receiving",
        table="ngs_receiving",
        name="Next Gen Stats — receiving",
        description="Separation, cushion, share of intended air yards, catch percentage above expectation.",
        url=f"{RELEASE}/nextgen_stats/ngs_receiving.parquet",
        grain="single",
        first_season=NGS_FIRST_SEASON,
        coverage_note="From 2016.",
    ),
    Source(
        id="advstats_pass",
        table="advstats_pass",
        name="Advanced passing (PFR charting)",
        description="Pressure rate, pocket time, drops, bad throws, on-target throws, play-action and RPO splits.",
        url=f"{RELEASE}/pfr_advstats/advstats_season_pass.parquet",
        grain="single",
        first_season=ADVSTATS_FIRST_SEASON,
        coverage_note="From 2018. Charted by Pro-Football-Reference and republished by nflverse.",
    ),
    Source(
        id="advstats_rush",
        table="advstats_rush",
        name="Advanced rushing (PFR charting)",
        description="Yards before and after contact, broken tackles.",
        url=f"{RELEASE}/pfr_advstats/advstats_season_rush.parquet",
        grain="single",
        first_season=ADVSTATS_FIRST_SEASON,
        coverage_note="From 2018.",
    ),
    Source(
        id="advstats_rec",
        table="advstats_rec",
        name="Advanced receiving (PFR charting)",
        description="Drops, contested catches, yards before and after catch per reception.",
        url=f"{RELEASE}/pfr_advstats/advstats_season_rec.parquet",
        grain="single",
        first_season=ADVSTATS_FIRST_SEASON,
        coverage_note="From 2018.",
    ),
    Source(
        id="advstats_def",
        table="advstats_def",
        name="Advanced defence (PFR charting)",
        description="Targets, completions allowed, yards allowed per coverage snap, missed tackles.",
        url=f"{RELEASE}/pfr_advstats/advstats_season_def.parquet",
        grain="single",
        first_season=ADVSTATS_FIRST_SEASON,
        coverage_note="From 2018.",
    ),
    Source(
        id="qbr_season",
        table="qbr_season",
        name="ESPN Total QBR (season)",
        description="ESPN's Total QBR with points added and expected points contributions.",
        url=f"{RELEASE}/espn_data/qbr_season_level.parquet",
        grain="single",
        first_season=QBR_FIRST_SEASON,
        coverage_note="ESPN's own metric, republished by nflverse. From 2006.",
    ),
    Source(
        id="officials",
        table="officials",
        name="Officials",
        description="Officiating crew assignments per game.",
        url=f"{RELEASE}/officials/officials.parquet",
        grain="single",
    ),
    Source(
        id="pbp",
        table="pbp",
        name="Play-by-play",
        description="Every play since 1999 with expected points, win probability and success, projected to the 77 columns the site uses.",
        url=f"{RELEASE}/pbp/play_by_play_{{season}}.parquet",
        grain="season",
        first_season=FIRST_SEASON,
        team_columns=("posteam", "defteam", "home_team", "away_team", "td_team", "penalty_team"),
        columns=PBP_COLUMNS,
        coverage_note=(
            "Expected points and win probability run from 1999. Air yards, yards after "
            "catch and CPOE were not charted before 2006 and are empty, not zero, in "
            "those seasons."
        ),
    ),
)

BY_ID: dict[str, Source] = {s.id: s for s in SOURCES}


def get(source_id: str) -> Source:
    try:
        return BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown source {source_id!r}") from exc
