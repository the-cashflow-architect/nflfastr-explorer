"""Synthetic nflverse files, shaped like the real ones.

Backend tests must not hit the network, but they also must not test against a
fantasy schema — most of the bugs worth catching here live in the joins between
sources, and a fixture that invents its own column names cannot catch those. So
these builders emit the real column names and the real quirks:

* Two team-code dialects: `games` uses the period code (STL), the stats files use
  the present-day one (LA).
* Air-yards columns are NULL before 2006.
* One unattributed row per weekly file, which the loader is expected to drop.
* A column that appears only in later seasons, to exercise schema drift.
"""

from __future__ import annotations

import os

import duckdb

# Enough of a league to have divisions, a relocation and a postseason.
TEAMS_2024 = ["KC", "BUF", "BAL", "CIN", "LA", "SF", "PHI", "DAL"]
TEAMS_2001 = ["KC", "BUF", "BAL", "CIN", "STL", "SF", "PHI", "DAL"]


def _write(con: duckdb.DuckDBPyConnection, sql: str, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fmt = "CSV, HEADER" if path.endswith(".csv") else "PARQUET"
    con.execute(f"COPY ({sql}) TO '{path}' ({'FORMAT ' + fmt})")
    return path


def write_games_csv(path: str, seasons=(2001, 2024)) -> str:
    """A schedule with period-correct team codes, a postseason, and an unplayed game."""
    con = duckdb.connect()
    rows = []
    for season in seasons:
        teams = TEAMS_2001 if season < 2002 else TEAMS_2024
        for week in range(1, 5):
            for i in range(0, len(teams), 2):
                home, away = teams[i], teams[i + 1]
                if week % 2 == 0:
                    home, away = away, home
                played = not (season == max(seasons) and week == 4)
                hs = 17 + week + i if played else "NULL"
                as_ = 10 + i if played else "NULL"
                rows.append(
                    f"('{season}_{week:02d}_{away}_{home}', {season}, 'REG', {week}, "
                    f"DATE '{season}-09-{week + 7:02d}', 'Sunday', '13:00', "
                    f"'{away}', {as_}, '{home}', {hs}, 'Home', "
                    f"{'NULL' if not played else f'{hs} - {as_}'}, "
                    f"'outdoors', 'grass', 68, 5, "
                    f"'{'Coach ' + away}', '{'Coach ' + home}', 'Ref One', "
                    f"'STA{i}', 'Stadium {i}', {1 if i == 0 else 0})"
                )
        # One postseason game so bracket and playoff-result code has something real.
        rows.append(
            f"('{season}_19_{teams[1]}_{teams[0]}', {season}, 'SB', 19, "
            f"DATE '{season + 1}-02-05', 'Sunday', '18:30', "
            f"'{teams[1]}', 20, '{teams[0]}', 27, 'Neutral', 7, "
            f"'dome', 'turf', NULL, NULL, 'Coach {teams[1]}', 'Coach {teams[0]}', "
            f"'Ref One', 'STA9', 'Neutral Field', 0)"
        )
    values = ",\n".join(rows)
    sql = f"""
      SELECT * FROM (VALUES {values}) AS t(
        game_id, season, game_type, week, gameday, weekday, gametime,
        away_team, away_score, home_team, home_score, location, result,
        roof, surface, temp, wind, away_coach, home_coach, referee,
        stadium_id, stadium, div_game)
    """
    return _write(con, sql, path)


def write_player_week(path: str, season: int, teams=None) -> str:
    """Weekly player rows in the present-day code dialect, with a null-team row."""
    con = duckdb.connect()
    teams = teams or (TEAMS_2001 if season < 2002 else TEAMS_2024)
    charted = season >= 2006
    team_list = ", ".join(f"'{t}'" for t in teams)
    extra = ", (i % 7)::DOUBLE AS receiving_epa" if season >= 2010 else ""
    return _write(
        con,
        f"""
        SELECT
          {season} AS season,
          (i % 4) + 1 AS week,
          'REG' AS season_type,
          '00-00' || lpad((i % 6)::VARCHAR, 5, '0') AS player_id,
          'Player ' || (i % 6) AS player_display_name,
          ['QB','RB','WR','TE','CB'][(i % 5) + 1] AS position,
          ['QB','RB','WR','TE','DB'][(i % 5) + 1] AS position_group,
          [{team_list}][(i % {len(teams)}) + 1] AS team,
          [{team_list}][((i + 1) % {len(teams)}) + 1] AS opponent_team,
          (200 + i * 3)::DOUBLE AS passing_yards,
          (i % 4)::DOUBLE AS passing_tds,
          (20 + i)::DOUBLE AS attempts,
          (12 + i)::DOUBLE AS completions,
          (40 + i)::DOUBLE AS rushing_yards,
          (55 + i * 2)::DOUBLE AS receiving_yards,
          (i % 9)::DOUBLE AS receptions,
          (i % 11)::DOUBLE AS targets,
          {'(i % 30)::DOUBLE' if charted else 'NULL::DOUBLE'} AS receiving_air_yards,
          {'(i % 5 - 2)::DOUBLE' if charted else 'NULL::DOUBLE'} AS passing_cpoe,
          (i % 7 - 3)::DOUBLE AS passing_epa,
          1 AS games{extra}
        FROM range(24) t(i)
        UNION ALL
        SELECT {season}, 1, 'REG', NULL, NULL, NULL, NULL, NULL, NULL,
               0, 0, 0, 0, 0, 0, 0, 0, NULL, NULL, NULL, 1{', NULL' if season >= 2010 else ''}
        """,
        path,
    )


def write_team_week(path: str, season: int, teams=None) -> str:
    con = duckdb.connect()
    teams = teams or (TEAMS_2001 if season < 2002 else TEAMS_2024)
    team_list = ", ".join(f"'{t}'" for t in teams)
    return _write(
        con,
        f"""
        SELECT
          {season} AS season, (i % 4) + 1 AS week, 'REG' AS season_type,
          [{team_list}][(i % {len(teams)}) + 1] AS team,
          [{team_list}][((i + 1) % {len(teams)}) + 1] AS opponent_team,
          (250 + i * 5)::DOUBLE AS passing_yards,
          (90 + i * 2)::DOUBLE AS rushing_yards,
          (i % 3)::DOUBLE AS def_sacks,
          (i % 2)::DOUBLE AS def_interceptions,
          (i % 8 - 3)::DOUBLE AS passing_epa
        FROM range(16) t(i)
        UNION ALL
        SELECT {season}, 1, 'REG', NULL, NULL, 0, 0, 0, 0, 0
        """,
        path,
    )


def write_players(path: str) -> str:
    con = duckdb.connect()
    return _write(
        con,
        """
        SELECT
          '00-00' || lpad(i::VARCHAR, 5, '0') AS gsis_id,
          'Player ' || i AS display_name,
          'Player' AS first_name, i::VARCHAR AS last_name,
          ['QB','RB','WR','TE','CB'][(i % 5) + 1] AS position,
          ['QB','RB','WR','TE','DB'][(i % 5) + 1] AS position_group,
          (i % 90) + 1 AS jersey_number,
          DATE '1995-01-01' + INTERVAL (i * 40) DAY AS birth_date,
          72 + (i % 8) AS height, 200 + i AS weight,
          'https://example.invalid/' || i || '.png' AS headshot,
          'State University' AS college_name, 'Big Conference' AS college_conference,
          2015 + (i % 6) AS rookie_season, 2024 AS last_season,
          'KC' AS latest_team, 'ACT' AS status, (i % 10) AS years_of_experience,
          CASE WHEN i % 3 = 0 THEN 2015 + (i % 6) END AS draft_year,
          CASE WHEN i % 3 = 0 THEN (i % 7) + 1 END AS draft_round,
          CASE WHEN i % 3 = 0 THEN i + 1 END AS draft_pick,
          CASE WHEN i % 3 = 0 THEN 'KAN' END AS draft_team,
          CASE WHEN i % 4 <> 0 THEN 'Play' || lpad(i::VARCHAR, 2, '0') END AS pfr_id,
          (3000 + i)::VARCHAR AS espn_id
        FROM range(6) t(i)
        """,
        path,
    )


def write_teams_meta(path: str) -> str:
    con = duckdb.connect()
    rows = ",\n".join(
        f"('{t}', '{t} Football Club', '{t}', "
        f"'{'AFC' if i < 4 else 'NFC'}', '{'AFC' if i < 4 else 'NFC'} Division', "
        f"'#123456', '#654321', 'https://example.invalid/{t}.png', "
        f"'https://example.invalid/{t}-sq.png', 'https://example.invalid/{t}-wm.png')"
        for i, t in enumerate(TEAMS_2024)
    )
    return _write(
        con,
        f"""SELECT * FROM (VALUES {rows}) AS t(
              team_abbr, team_name, team_nick, team_conf, team_division,
              team_color, team_color2, team_logo_espn, team_logo_squared, team_wordmark)""",
        path,
    )


def write_pbp(path: str, season: int, teams=None) -> str:
    """Plays with real drive, EPA and win-probability columns, charted only from 2006."""
    con = duckdb.connect()
    teams = teams or (TEAMS_2001 if season < 2002 else TEAMS_2024)
    charted = season >= 2006
    home, away = teams[0], teams[1]
    return _write(
        con,
        f"""
        SELECT
          {season} AS season, 1 AS week,
          '{season}_01_{away}_{home}' AS game_id,
          i + 1 AS play_id, 'REG' AS season_type,
          CASE WHEN i % 2 = 0 THEN '{home}' ELSE '{away}' END AS posteam,
          CASE WHEN i % 2 = 0 THEN '{away}' ELSE '{home}' END AS defteam,
          '{home}' AS home_team, '{away}' AS away_team,
          (i % 4) + 1 AS down, (i % 10) + 1 AS ydstogo, 80 - (i % 60) AS yardline_100,
          (i / 12)::INTEGER + 1 AS qtr,
          900 - (i % 15) * 60 AS quarter_seconds_remaining,
          1800 - (i % 30) * 60 AS half_seconds_remaining,
          3600 - i * 60 AS game_seconds_remaining,
          (i % 14) - 7 AS score_differential,
          (i / 6)::INTEGER * 3 AS total_home_score, (i / 8)::INTEGER * 3 AS total_away_score,
          CASE WHEN i % 3 = 0 THEN 'run' ELSE 'pass' END AS play_type,
          CASE WHEN i % 3 = 0 THEN 0 ELSE 1 END AS "pass",
          CASE WHEN i % 3 = 0 THEN 1 ELSE 0 END AS rush,
          0 AS special, 'Play number ' || i AS "desc",
          CASE WHEN i % 3 <> 0 THEN '00-00' || lpad((i % 6)::VARCHAR, 5, '0') END AS passer_player_id,
          CASE WHEN i % 3 <> 0 THEN 'Player ' || (i % 6) END AS passer_player_name,
          CASE WHEN i % 3 <> 0 THEN '00-00' || lpad(((i + 2) % 6)::VARCHAR, 5, '0') END AS receiver_player_id,
          CASE WHEN i % 3 <> 0 THEN 'Player ' || ((i + 2) % 6) END AS receiver_player_name,
          CASE WHEN i % 3 = 0 THEN '00-00' || lpad(((i + 1) % 6)::VARCHAR, 5, '0') END AS rusher_player_id,
          CASE WHEN i % 3 = 0 THEN 'Player ' || ((i + 1) % 6) END AS rusher_player_name,
          NULL::VARCHAR AS interception_player_id, NULL::VARCHAR AS fumbled_1_player_id,
          NULL::VARCHAR AS td_player_id, NULL::VARCHAR AS td_player_name, NULL::VARCHAR AS td_team,
          NULL::VARCHAR AS penalty_player_id, NULL::VARCHAR AS penalty_team,
          NULL::DOUBLE AS penalty_yards, NULL::VARCHAR AS penalty_type,
          (i % 17) - 3 AS yards_gained,
          {'(i % 25)::DOUBLE' if charted else 'NULL::DOUBLE'} AS air_yards,
          {'(i % 9)::DOUBLE' if charted else 'NULL::DOUBLE'} AS yards_after_catch,
          ((i % 21) - 10) / 10.0 AS epa, ((i % 19) - 9) / 10.0 AS qb_epa,
          0.3 + (i % 40) / 100.0 AS wp, 0.3 + (i % 40) / 100.0 AS home_wp,
          ((i % 11) - 5) / 100.0 AS wpa,
          {'((i % 15) - 7)::DOUBLE' if charted else 'NULL::DOUBLE'} AS cpoe,
          CASE WHEN (i % 21) - 10 > 0 THEN 1 ELSE 0 END AS success,
          (i / 6)::INTEGER + 1 AS series,
          CASE WHEN i % 4 = 0 THEN 1 ELSE 0 END AS series_success,
          CASE WHEN i % 17 = 0 THEN 1 ELSE 0 END AS touchdown,
          CASE WHEN i % 34 = 0 THEN 1 ELSE 0 END AS pass_touchdown,
          CASE WHEN i % 51 = 0 THEN 1 ELSE 0 END AS rush_touchdown,
          0 AS interception, CASE WHEN i % 3 <> 0 AND i % 5 <> 0 THEN 1 ELSE 0 END AS complete_pass,
          CASE WHEN i % 23 = 0 THEN 1 ELSE 0 END AS sack,
          CASE WHEN i % 4 = 0 THEN 1 ELSE 0 END AS first_down,
          0 AS fumble_lost, 0 AS safety, 0 AS two_point_attempt,
          CASE WHEN i % 29 = 0 THEN 1 ELSE 0 END AS field_goal_attempt,
          CASE WHEN i % 29 = 0 THEN 'made' END AS field_goal_result,
          CASE WHEN i % 31 = 0 THEN 1 ELSE 0 END AS punt_attempt,
          0 AS kickoff_attempt, 0 AS extra_point_attempt,
          CASE WHEN i % 17 = 0 THEN 1 ELSE 0 END AS sp,
          (i / 6)::INTEGER + 1 AS fixed_drive,
          ['Touchdown','Punt','Field goal','Turnover on downs'][((i / 6)::INTEGER % 4) + 1] AS fixed_drive_result,
          6 AS drive_play_count, '3:20' AS drive_time_of_possession,
          2 AS drive_first_downs,
          CASE WHEN i % 2 = 0 THEN '{home} 25' ELSE '{away} 30' END AS drive_start_yard_line,
          CASE WHEN i % 2 = 0 THEN '{away} 40' ELSE '50' END AS drive_end_yard_line,
          '15:00' AS drive_game_clock_start,
          CASE WHEN i % 3 = 0 THEN 1 ELSE 0 END AS drive_inside20,
          CASE WHEN i % 4 = 0 THEN 1 ELSE 0 END AS drive_ended_with_score
        FROM range(48) t(i)
        """,
        path,
    )
