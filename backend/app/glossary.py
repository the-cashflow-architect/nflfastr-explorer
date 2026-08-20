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
    "recent_team": {
        "label": "Team",
        "description": "The team this player was on most recently in the season — for a player who changed teams mid-season, earlier games may have been with a different one.",
    },
    "games": {
        "label": "Games",
        "description": "Games played that season.",
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
    "interception": {
        "label": "Interception",
        "description": "Whether this pass was intercepted (1) or not (0).",
    },
    "complete_pass": {
        "label": "Completed",
        "description": "Whether this pass attempt was completed (1) or not (0).",
    },
    "sack": {
        "label": "Sack",
        "description": "Whether the passer was sacked on this play (1) or not (0).",
    },
    "first_down": {
        "label": "First Down",
        "description": "Whether this play gained a first down (1) or not (0).",
    },
    "pass": {
        "label": "Pass Play",
        "description": "Whether this play was a pass attempt (1) or not (0), including sacks.",
    },
    "rush": {
        "label": "Rush Play",
        "description": "Whether this play was a designed run (1) or not (0).",
    },
    "yards_after_catch": {
        "label": "YAC (Play)",
        "description": "Yards gained after the catch on this individual play.",
    },
    "play_id": {
        "label": "Play ID",
        "description": "Sequential identifier for the play within its game.",
    },
    "sacks_suffered": {
        "label": "Sacks Taken",
        "description": "Times this player was sacked as the passer.",
    },
    "sack_yards_lost": {
        "label": "Sack Yards Lost",
        "description": "Total yards lost on sacks taken by this player.",
    },
    "sack_fumbles": {
        "label": "Sack Fumbles",
        "description": "Fumbles that occurred on a sack.",
    },
    "sack_fumbles_lost": {
        "label": "Sack Fumbles Lost",
        "description": "Sack fumbles recovered by the defense.",
    },
    "passing_interceptions": {
        "label": "Interceptions",
        "description": "Passes thrown by this player that were intercepted.",
    },
    "passing_cpoe": {
        "label": "CPOE",
        "description": "Completion Percentage Over Expected on this player's pass attempts.",
        "formula": "Actual completion rate minus the nflfastR model's expected completion probability.",
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
        "description": "How much better (or worse) this QB's throws made his team's scoring chances, added up over every dropback. A positive number means his passing is helping the team score; negative means it's hurting.",
        "formula": "Sum of EPA on pass attempts and sacks. EPA compares down/distance/field position before and after the play.",
    },
    "passing_2pt_conversions": {
        "label": "Passing 2PT",
        "description": "Successful two-point conversion passes.",
    },
    "pacr": {
        "label": "PACR",
        "description": "How efficiently a QB turns air yards (distance the ball travels before it's caught) into real yards gained. Above 1.0 means his receivers are gaining extra yards after the catch; below 1.0 means throws aren't converting into as much as their distance implied.",
        "formula": "passing_yards / passing_air_yards (when air yards > 0).",
    },
    "dakota": {
        "label": "DAKOTA",
        "description": "A single \"how good is this QB\" score that blends play value (EPA) with accuracy relative to expectation (CPOE), adjusting for how hard his throws were. Higher is better; it's built to compare quarterbacks more fairly than raw stats alone.",
        "formula": "nflfastR proprietary composite of EPA and completion probability over expected.",
    },
    "cpoe": {
        "label": "CPOE",
        "description": "Is this QB completing more or fewer passes than a typical passer would on the exact same throws (accounting for distance, coverage, etc.)? Positive means more accurate than expected for how hard the throws were; negative means less accurate.",
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
        "description": "How much this player's carries added to (or subtracted from) his team's scoring chances, added up over the season. Positive means his running is helping the team score.",
        "formula": "Sum of EPA on rushing plays (designed runs and QB scrambles) attributed to the rusher.",
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
        "description": "How much this player's targets added to (or subtracted from) his team's scoring chances, added up over the season. Positive means throws his way are helping the team score.",
        "formula": "Sum of EPA on plays where this player was the target.",
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
        "description": "How efficiently a receiver turns the distance the ball traveled through the air into actual yards gained. Above 1.0 means he's adding extra yards after the catch relative to how far the ball was thrown; below 1.0 means less.",
        "formula": "receiving_yards / receiving_air_yards.",
    },
    "target_share": {
        "label": "Target Share",
        "description": "What percentage of his team's pass attempts were aimed at this player. A simple measure of how big a part of the passing offense he is — higher means the offense goes through him more.",
        "formula": "Player targets / team targets (when player on field).",
    },
    "air_yards_share": {
        "label": "Air Yards Share",
        "description": "What percentage of his team's total \"downfield distance thrown\" belongs to this player's targets — a sign of whether he's used on deep, high-value throws versus short, low-value ones.",
    },
    "wopr": {
        "label": "WOPR",
        "description": "A single \"how big is this player's role in the passing game\" score that combines how often he's targeted with how far downfield those targets are. Higher means a bigger, more valuable role in the offense.",
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
    "def_fumbles": {
        "label": "Fumble Recoveries",
        "description": "Fumbles recovered by the defender.",
    },
    "def_safeties": {
        "label": "Safeties",
        "description": "Safeties recorded by the defender.",
    },
    "def_tackles_for_loss_yards": {
        "label": "TFL Yards",
        "description": "Yards lost by the offense on this defender's tackles for loss.",
    },
    "def_sack_yards": {
        "label": "Sack Yards",
        "description": "Yards lost by the offense on this defender's sacks.",
    },
    "def_interception_yards": {
        "label": "INT Return Yards",
        "description": "Yards gained returning this defender's interceptions.",
    },
    "def_punt_blocks": {
        "label": "Punts Blocked",
        "description": "Opponent punts blocked by this defender.",
    },
    "def_pat_blocks": {
        "label": "PATs Blocked",
        "description": "Opponent extra points blocked by this defender.",
    },
    "def_fg_blocks": {
        "label": "FGs Blocked",
        "description": "Opponent field goals blocked by this defender.",
    },
    "def_2pt_atts": {
        "label": "Def 2PT Attempts Against",
        "description": "Opponent two-point conversion attempts this defender faced.",
    },
    "def_2pt_made": {
        "label": "Def 2PT Allowed",
        "description": "Opponent two-point conversions allowed on plays involving this defender.",
    },
    # Kicking
    "fg_made": {
        "label": "FG Made",
        "description": "Field goals made.",
    },
    "fg_att": {
        "label": "FG Attempts",
        "description": "Field goals attempted.",
    },
    "fg_missed": {
        "label": "FG Missed",
        "description": "Field goals missed (not blocked).",
    },
    "fg_blocked": {
        "label": "FG Blocked",
        "description": "Field goal attempts blocked by the defense.",
    },
    "fg_long": {
        "label": "Long FG",
        "description": "Longest field goal made, in yards.",
    },
    "fg_pct": {
        "label": "FG %",
        "description": "Field goal accuracy.",
        "formula": "fg_made / fg_att.",
    },
    "fg_made_0_19": {
        "label": "FG Made 0-19",
        "description": "Field goals made from 0-19 yards.",
    },
    "fg_made_20_29": {
        "label": "FG Made 20-29",
        "description": "Field goals made from 20-29 yards.",
    },
    "fg_made_30_39": {
        "label": "FG Made 30-39",
        "description": "Field goals made from 30-39 yards.",
    },
    "fg_made_40_49": {
        "label": "FG Made 40-49",
        "description": "Field goals made from 40-49 yards.",
    },
    "fg_made_50_59": {
        "label": "FG Made 50-59",
        "description": "Field goals made from 50-59 yards.",
    },
    "fg_made_60_": {
        "label": "FG Made 60+",
        "description": "Field goals made from 60 or more yards.",
    },
    "fg_missed_0_19": {
        "label": "FG Missed 0-19",
        "description": "Field goals missed from 0-19 yards.",
    },
    "fg_missed_20_29": {
        "label": "FG Missed 20-29",
        "description": "Field goals missed from 20-29 yards.",
    },
    "fg_missed_30_39": {
        "label": "FG Missed 30-39",
        "description": "Field goals missed from 30-39 yards.",
    },
    "fg_missed_40_49": {
        "label": "FG Missed 40-49",
        "description": "Field goals missed from 40-49 yards.",
    },
    "fg_missed_50_59": {
        "label": "FG Missed 50-59",
        "description": "Field goals missed from 50-59 yards.",
    },
    "fg_missed_60_": {
        "label": "FG Missed 60+",
        "description": "Field goals missed from 60 or more yards.",
    },
    "fg_made_distance": {
        "label": "FG Made Distance",
        "description": "Combined distance, in yards, of all made field goals.",
    },
    "fg_missed_distance": {
        "label": "FG Missed Distance",
        "description": "Combined distance, in yards, of all missed field goals.",
    },
    "fg_blocked_distance": {
        "label": "FG Blocked Distance",
        "description": "Combined distance, in yards, of all blocked field goal attempts.",
    },
    "pat_made": {
        "label": "PAT Made",
        "description": "Extra points made.",
    },
    "pat_att": {
        "label": "PAT Attempts",
        "description": "Extra points attempted.",
    },
    "pat_missed": {
        "label": "PAT Missed",
        "description": "Extra points missed (not blocked).",
    },
    "pat_blocked": {
        "label": "PAT Blocked",
        "description": "Extra point attempts blocked by the defense.",
    },
    "pat_pct": {
        "label": "PAT %",
        "description": "Extra point accuracy.",
        "formula": "pat_made / pat_att.",
    },
    "gwfg_made": {
        "label": "Game-Winning FG Made",
        "description": "Field goals made that either won the game or gave the lead in the final minute of regulation or in overtime.",
    },
    "gwfg_att": {
        "label": "Game-Winning FG Attempts",
        "description": "Field goal attempts in a game-winning situation.",
    },
    "gwfg_missed": {
        "label": "Game-Winning FG Missed",
        "description": "Game-winning field goal attempts missed.",
    },
    "gwfg_blocked": {
        "label": "Game-Winning FG Blocked",
        "description": "Game-winning field goal attempts blocked.",
    },
    "gwfg_distance": {
        "label": "Game-Winning FG Distance",
        "description": "Distance, in yards, of game-winning field goal attempts.",
    },
    # Punting
    "pt_att": {
        "label": "Punts",
        "description": "Punts attempted.",
    },
    "pt_blocked": {
        "label": "Punts Blocked",
        "description": "Punts blocked by the defense.",
    },
    "pt_long": {
        "label": "Long Punt",
        "description": "Longest punt, in yards.",
    },
    "pt_yards": {
        "label": "Punt Yards",
        "description": "Total gross punting yards.",
    },
    "pt_net_yards": {
        "label": "Net Punt Yards",
        "description": "Total punting yards after subtracting return yardage.",
        "formula": "Gross punt yards minus yards returned by the opponent.",
    },
    "pt_inside_20": {
        "label": "Punts Inside 20",
        "description": "Punts downed or fair-caught inside the opponent's 20-yard line.",
    },
    "pt_out_of_bounds": {
        "label": "Punts OOB",
        "description": "Punts that went out of bounds.",
    },
    "pt_downed": {
        "label": "Punts Downed",
        "description": "Punts downed by the coverage team before a return.",
    },
    "pt_touchback": {
        "label": "Punt Touchbacks",
        "description": "Punts resulting in a touchback.",
    },
    "pt_fair_caught": {
        "label": "Punts Fair Caught",
        "description": "Punts fair-caught by the returner.",
    },
    "pt_returned": {
        "label": "Punts Returned",
        "description": "Punts returned by the opponent.",
    },
    "pt_return_yards": {
        "label": "Punt Return Yards Allowed",
        "description": "Yards gained by the opponent returning this player's punts.",
    },
    "pt_return_tds": {
        "label": "Punt Return TDs Allowed",
        "description": "Touchdowns scored by the opponent returning this player's punts.",
    },
    # Returns
    "punt_returns": {
        "label": "Punt Returns",
        "description": "Punts returned by this player.",
    },
    "punt_return_yards": {
        "label": "Punt Return Yards",
        "description": "Yards gained returning punts.",
    },
    "kickoff_returns": {
        "label": "Kickoff Returns",
        "description": "Kickoffs returned by this player.",
    },
    "kickoff_return_yards": {
        "label": "Kickoff Return Yards",
        "description": "Yards gained returning kickoffs.",
    },
    "special_teams_tds": {
        "label": "Special Teams TDs",
        "description": "Touchdowns scored on returns or other special teams plays.",
    },
    # Penalties
    "penalties": {
        "label": "Penalties",
        "description": "Penalties committed by this player.",
    },
    "penalty_yards": {
        "label": "Penalty Yards",
        "description": "Yards assessed on this player's penalties.",
    },
    # Ball security (fumbles not already tied to a passing/rushing/receiving stat line)
    "fumble_recovery_own": {
        "label": "Own Fumbles Recovered",
        "description": "This player's own fumbles that they recovered themselves.",
    },
    "fumble_recovery_yards_own": {
        "label": "Own Fumble Recovery Yards",
        "description": "Yards gained recovering their own fumble.",
    },
    "fumble_recovery_opp": {
        "label": "Opponent Fumbles Recovered",
        "description": "Opponent fumbles recovered by this player.",
    },
    "fumble_recovery_yards_opp": {
        "label": "Opponent Fumble Recovery Yards",
        "description": "Yards gained recovering an opponent's fumble.",
    },
    "fumble_recovery_tds": {
        "label": "Fumble Recovery TDs",
        "description": "Touchdowns scored on a fumble recovery.",
    },
    "fumbles_forced_by_opp": {
        "label": "Fumbles Forced by Opponent",
        "description": "Times this player fumbled after being forced to by the defense.",
    },
    "fumbles_not_forced": {
        "label": "Unforced Fumbles",
        "description": "Fumbles this player lost control of without being forced.",
    },
    "fumbles_out_of_bounds": {
        "label": "Fumbles Out of Bounds",
        "description": "Fumbles by this player that went out of bounds.",
    },
    "fumbles_total": {
        "label": "Total Fumbles",
        "description": "All fumbles by this player, across passing, rushing, and receiving plays.",
    },
    "fumbles_lost_total": {
        "label": "Total Fumbles Lost",
        "description": "All fumbles by this player recovered by the opposing team.",
    },
    "misc_yards": {
        "label": "Misc Yards",
        "description": "Yardage from plays that don't fit standard passing, rushing, or receiving categories (e.g. lateral or recovery yardage).",
    },
    # Fantasy bonus-yardage thresholds — used by some fantasy scoring formats
    # that award bonus points for crossing a yardage milestone in a game.
    "passing_10": {
        "label": "Pass Yardage Bonus (10)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big passing games.",
    },
    "passing_16": {
        "label": "Pass Yardage Bonus (16)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big passing games.",
    },
    "passing_20": {
        "label": "Pass Yardage Bonus (20)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big passing games.",
    },
    "passing_40": {
        "label": "Pass Yardage Bonus (40)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big passing games.",
    },
    "rushing_10": {
        "label": "Rush Yardage Bonus (10)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big rushing games.",
    },
    "rushing_12": {
        "label": "Rush Yardage Bonus (12)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big rushing games.",
    },
    "rushing_20": {
        "label": "Rush Yardage Bonus (20)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big rushing games.",
    },
    "rushing_40": {
        "label": "Rush Yardage Bonus (40)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big rushing games.",
    },
    "receiving_10": {
        "label": "Rec Yardage Bonus (10)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big receiving games.",
    },
    "receiving_16": {
        "label": "Rec Yardage Bonus (16)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big receiving games.",
    },
    "receiving_20": {
        "label": "Rec Yardage Bonus (20)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big receiving games.",
    },
    "receiving_40": {
        "label": "Rec Yardage Bonus (40)",
        "description": "Bonus-yardage threshold tracked for fantasy scoring formats that award points for big receiving games.",
    },
    # EPA aggregates
    "epa": {
        "label": "EPA",
        "description": "How much did this one play help or hurt the offense's chances of scoring? A big positive number is a great play; a big negative number is a bad one — it accounts for down, distance, and field position, not just yards gained.",
        "formula": "Expected points after the play minus expected points before it (nflfastR EP model).",
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
    "game_id": {
        "label": "Game ID",
        "description": "Unique nflverse identifier for the game this row belongs to.",
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
        "description": "How likely the team with the ball was to win the game at the moment of this play, based on score, time, and field position.",
        "formula": "nflfastR win probability model at snap.",
    },
    "wpa": {
        "label": "WPA",
        "description": "How much this specific play swung the team's odds of winning the game — a walk-off touchdown might swing it 40+ points; a routine first-down run barely moves it.",
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
