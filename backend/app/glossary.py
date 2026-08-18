"""Human-readable stat definitions sourced from nflfastR / nflverse documentation."""

from __future__ import annotations

GLOSSARY: dict[str, dict[str, str]] = {
    # Identity & context
    "player_id": {
        "label": "Player ID",
        "description": "Unique GSIS player identifier used across nflverse datasets.",
        "formula": "Mapped from NFL Game Statistics & Information System (GSIS).",
    },
    "player_name": {
        "label": "Player",
        "description": "Short player name as reported in official NFL stats.",
    },
    "player_display_name": {
        "label": "Display Name",
        "description": "Formatted player name for display (typically First Last).",
    },
    "position": {
        "label": "Position",
        "description": "Primary offensive/defensive/special teams position (QB, WR, CB, K, etc.).",
    },
    "position_group": {
        "label": "Position Group",
        "description": "Grouped position bucket: QB, RB, WR, TE, OL, DL, LB, DB, K, P, etc.",
    },
    "team": {
        "label": "Team",
        "description": "Three-letter team abbreviation for the player's team on the given row.",
    },
    "season": {
        "label": "Season",
        "description": "Four-digit NFL season year (regular season starts in the calendar year after the label).",
    },
    "week": {
        "label": "Week",
        "description": "NFL week number. Regular season is weeks 1–18; postseason uses higher week numbers.",
    },
    "season_type": {
        "label": "Season Type",
        "description": "REG (regular season), POST (playoffs), or PRE (preseason).",
    },
    "opponent_team": {
        "label": "Opponent",
        "description": "Three-letter abbreviation of the opposing team.",
    },
    # Passing
    "completions": {
        "label": "Completions",
        "description": "Pass attempts that resulted in a completion.",
        "formula": "Count of completed pass attempts.",
    },
    "attempts": {
        "label": "Pass Attempts",
        "description": "Total pass attempts including completions, incompletions, and sacks (sacks counted separately).",
    },
    "passing_yards": {
        "label": "Passing Yards",
        "description": "Net passing yards gained on completed passes (includes YAC).",
        "formula": "Sum of yards on completed passes.",
    },
    "passing_tds": {
        "label": "Passing TDs",
        "description": "Touchdowns scored via pass completion.",
    },
    "interceptions": {
        "label": "Interceptions",
        "description": "Passes thrown that were intercepted by the defense.",
    },
    "sacks": {
        "label": "Sacks Taken",
        "description": "Times the passer was sacked (team-level in some views).",
    },
    "sack_yards": {
        "label": "Sack Yards Lost",
        "description": "Total yards lost on sacks.",
    },
    "passing_air_yards": {
        "label": "Air Yards",
        "description": "Total intended air yards on pass attempts — distance from line of scrimmage to target point.",
        "formula": "Sum of air yards on pass attempts (nflfastR charting).",
    },
    "passing_yards_after_catch": {
        "label": "YAC",
        "description": "Yards after catch — yards gained by the receiver after securing the pass.",
        "formula": "Sum of yards after catch on completions.",
    },
    "passing_first_downs": {
        "label": "Passing 1st Downs",
        "description": "First downs gained via pass (completion or defensive penalty).",
    },
    "passing_epa": {
        "label": "Passing EPA",
        "description": "Expected Points Added on dropbacks — measures play value vs. baseline expectation.",
        "formula": "Sum of EPA on pass attempts and sacks. EPA compares down/distance/field position before and after the play.",
    },
    "passing_2pt_conversions": {
        "label": "Passing 2PT",
        "description": "Successful two-point conversion passes.",
    },
    "pacr": {
        "label": "PACR",
        "description": "Passing Air Conversion Ratio — receiving yards divided by air yards.",
        "formula": "passing_yards / passing_air_yards (when air yards > 0).",
    },
    "dakota": {
        "label": "DakOTA",
        "description": "Adjusted EPA per dropback metric that blends EPA and CPOE for quarterback evaluation.",
        "formula": "nflfastR proprietary composite of EPA and completion probability over expected.",
    },
    "cpoe": {
        "label": "CPOE",
        "description": "Completion Percentage Over Expected — actual completion rate minus model-predicted rate.",
        "formula": "Actual completions / attempts − expected completion probability (nflfastR model).",
    },
    # Rushing
    "carries": {
        "label": "Carries",
        "description": "Rush attempts including kneels and scrambles counted as rushes.",
    },
    "rushing_yards": {
        "label": "Rushing Yards",
        "description": "Total yards gained on rushing plays.",
    },
    "rushing_tds": {
        "label": "Rushing TDs",
        "description": "Touchdowns scored on rushing plays.",
    },
    "rushing_fumbles": {
        "label": "Rush Fumbles",
        "description": "Fumbles on rushing plays (lost or recovered).",
    },
    "rushing_fumbles_lost": {
        "label": "Rush Fumbles Lost",
        "description": "Rushing fumbles recovered by the defense.",
    },
    "rushing_first_downs": {
        "label": "Rushing 1st Downs",
        "description": "First downs gained on rushing plays.",
    },
    "rushing_epa": {
        "label": "Rushing EPA",
        "description": "Expected Points Added on designed runs and scrambles attributed to the rusher.",
    },
    "rushing_2pt_conversions": {
        "label": "Rushing 2PT",
        "description": "Successful two-point conversion rushes.",
    },
    # Receiving
    "receptions": {
        "label": "Receptions",
        "description": "Completed passes caught by this player.",
    },
    "targets": {
        "label": "Targets",
        "description": "Pass attempts where this player was the intended receiver.",
    },
    "receiving_yards": {
        "label": "Receiving Yards",
        "description": "Total yards gained on receptions (includes YAC).",
    },
    "receiving_tds": {
        "label": "Receiving TDs",
        "description": "Touchdowns scored on receptions.",
    },
    "receiving_air_yards": {
        "label": "Receiving Air Yards",
        "description": "Air yards on targets — distance ball traveled in the air toward this receiver.",
    },
    "receiving_yards_after_catch": {
        "label": "Receiving YAC",
        "description": "Yards after catch on this player's receptions.",
    },
    "receiving_first_downs": {
        "label": "Receiving 1st Downs",
        "description": "First downs gained via receptions.",
    },
    "receiving_epa": {
        "label": "Receiving EPA",
        "description": "Expected Points Added on targets to this receiver.",
    },
    "receiving_fumbles": {
        "label": "Rec Fumbles",
        "description": "Fumbles after a reception.",
    },
    "receiving_fumbles_lost": {
        "label": "Rec Fumbles Lost",
        "description": "Reception fumbles lost to the defense.",
    },
    "receiving_2pt_conversions": {
        "label": "Receiving 2PT",
        "description": "Successful two-point conversion receptions.",
    },
    "racr": {
        "label": "RACR",
        "description": "Receiver Air Conversion Ratio — receiving yards divided by air yards.",
        "formula": "receiving_yards / receiving_air_yards.",
    },
    "target_share": {
        "label": "Target Share",
        "description": "Share of team pass targets on the field for this player.",
        "formula": "Player targets / team targets (when player on field).",
    },
    "air_yards_share": {
        "label": "Air Yards Share",
        "description": "Share of team air yards on the player's targets.",
    },
    "wopr": {
        "label": "WOPR",
        "description": "Weighted Opportunity Rating — combines target share and air yards share.",
        "formula": "1.5 × target_share + 0.7 × air_yards_share (Josh Hermsmeyer).",
    },
    # Defense / misc
    "def_tackles_solo": {
        "label": "Solo Tackles",
        "description": "Solo defensive tackles.",
    },
    "def_tackles_with_assist": {
        "label": "Assisted Tackles",
        "description": "Defensive tackles with an assist.",
    },
    "def_tackle_assists": {
        "label": "Tackle Assists",
        "description": "Assisted tackles credited to the player.",
    },
    "def_tackles_for_loss": {
        "label": "TFL",
        "description": "Tackles for loss.",
    },
    "def_sacks": {
        "label": "Def Sacks",
        "description": "Sacks recorded by the defender.",
    },
    "def_qb_hits": {
        "label": "QB Hits",
        "description": "Quarterback hits (sacks plus hits without takedown).",
    },
    "def_interceptions": {
        "label": "Def INTs",
        "description": "Interceptions made by the defender.",
    },
    "def_pass_defended": {
        "label": "Pass Breakups",
        "description": "Passes defensed (PBU) by the defender.",
    },
    "def_tds": {
        "label": "Def TDs",
        "description": "Defensive or special teams touchdowns scored.",
    },
    "def_fumbles_forced": {
        "label": "Forced Fumbles",
        "description": "Fumbles forced by the defender.",
    },
    "def_fumble_recoveries": {
        "label": "Fumble Recoveries",
        "description": "Fumbles recovered by the defender.",
    },
    "def_safety": {
        "label": "Safeties",
        "description": "Safeties recorded.",
    },
    # EPA aggregates
    "epa": {
        "label": "Total EPA",
        "description": "Total Expected Points Added across all phases attributed to the player.",
        "formula": "Sum of EPA on all plays involving the player.",
    },
    "fantasy_points": {
        "label": "Fantasy Pts",
        "description": "Standard fantasy points (PPR scoring in nflfastR default).",
        "formula": "Passing/receiving/rushing production converted via standard scoring rules.",
    },
    "fantasy_points_ppr": {
        "label": "Fantasy Pts (PPR)",
        "description": "PPR fantasy points including 1 point per reception.",
    },
    # Play-by-play fields
    "play_type": {
        "label": "Play Type",
        "description": "Category of play: pass, run, punt, field_goal, kickoff, extra_point, qb_kneel, etc.",
    },
    "posteam": {
        "label": "Offense",
        "description": "Team with possession on the play (posteam = possession team).",
    },
    "defteam": {
        "label": "Defense",
        "description": "Team on defense for the play.",
    },
    "down": {
        "label": "Down",
        "description": "Current down (1–4).",
    },
    "ydstogo": {
        "label": "Yards to Go",
        "description": "Yards needed for a first down or touchdown.",
    },
    "yardline_100": {
        "label": "Field Position",
        "description": "Yards from opponent end zone (1 = goal line, 99 = far end). Lower = better for offense.",
    },
    "qtr": {
        "label": "Quarter",
        "description": "Quarter of the game (1–4; 5+ for overtime).",
    },
    "game_seconds_remaining": {
        "label": "Game Clock",
        "description": "Seconds remaining in the game at the snap.",
    },
    "score_differential": {
        "label": "Score Diff",
        "description": "Offense score minus defense score at time of play.",
    },
    "wp": {
        "label": "Win Probability",
        "description": "Estimated probability the posteam wins before the play.",
        "formula": "nflfastR win probability model at snap.",
    },
    "wpa": {
        "label": "WPA",
        "description": "Win Probability Added — change in win probability from the play.",
        "formula": "WP after play − WP before play.",
    },
    "air_yards": {
        "label": "Air Yards (Play)",
        "description": "Air yards on an individual pass attempt.",
    },
    "yards_gained": {
        "label": "Yards Gained",
        "description": "Net yards gained on the play.",
    },
    "touchdown": {
        "label": "Touchdown",
        "description": "Whether the play resulted in a touchdown (1/0).",
    },
    "pass_touchdown": {
        "label": "Pass TD",
        "description": "Touchdown scored via pass on this play.",
    },
    "rush_touchdown": {
        "label": "Rush TD",
        "description": "Touchdown scored via rush on this play.",
    },
    "passer_player_name": {
        "label": "Passer",
        "description": "Name of the passing player on the play.",
    },
    "receiver_player_name": {
        "label": "Receiver",
        "description": "Name of the targeted receiver on the play.",
    },
    "rusher_player_name": {
        "label": "Rusher",
        "description": "Name of the rushing player on the play.",
    },
    "desc": {
        "label": "Description",
        "description": "Human-readable play description from NFL data.",
    },
}


def get_column_meta(column: str, dtype: str) -> dict:
    entry = GLOSSARY.get(column, {})
    return {
        "id": column,
        "label": entry.get("label", column.replace("_", " ").title()),
        "description": entry.get("description", f"Stat column `{column}` from nflfastR / nflverse."),
        "formula": entry.get("formula"),
        "dtype": dtype,
    }
