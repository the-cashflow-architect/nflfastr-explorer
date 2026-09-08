"""Tests for the play-by-play ETL.

Two kinds of test live here. The fixture seasons — 2001 and 2024, one either side
of both the realignment and the air-yards charting boundary — prove the transforms
run over real-shaped files. Hand-built play tables prove the things the fixture
cannot contain: a drive owned by the team on the *other* side of the field, two
seasons with different play counts, a four-hundred-play game.

The hand-built tables are created from the loaded `pbp` table's own shape and
filled `BY NAME`, so every column the ETL touches exists with its real type and
everything not named is NULL — which is also how the source behaves.
"""

from __future__ import annotations

import pytest

from app.etl import pbp_derive
from app.etl.buckets import BUCKETS, BUCKET_KEYS, ROLE_KEYS, any_bucket_sql
from app.etl.pbp_derive import (
    WP_POINTS_PER_GAME,
    derive_all,
    derive_season,
    derived_tables,
    ensure_tables,
    insert_season,
)

FIXTURE_SEASONS = (2001, 2024)


def _plays_table(cur, name: str, select_sql: str) -> str:
    """A plays relation shaped exactly like `pbp`, filled from `select_sql`."""
    cur.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM pbp LIMIT 0")
    cur.execute(f"INSERT INTO {name} BY NAME {select_sql}")
    return name


@pytest.fixture
def derived(built_loader):
    """A loader with both fixture seasons derived."""
    built_loader.ensure("pbp")
    derive_all(built_loader, FIXTURE_SEASONS)
    return built_loader


# --- the buckets -------------------------------------------------------------


def test_there_are_exactly_sixteen_buckets_and_they_are_not_a_cross_product():
    assert len(BUCKETS) == 16
    assert len(set(BUCKET_KEYS)) == 16
    # Quarters were removed in SPEC section 3; halves plus two-minute replace them.
    assert not [k for k in BUCKET_KEYS if k.startswith("qtr") or "quarter" in k]
    # A cross-product of down x distance x score state would be dozens of keys and
    # would show up as compound names. Sixteen flat situations is the contract.
    assert ROLE_KEYS == ("passer", "rusher", "receiver")


@pytest.mark.parametrize("season", FIXTURE_SEASONS)
def test_every_play_falls_into_at_least_one_bucket(built_loader, season):
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    relation = built_loader.pbp_relation(season)
    orphans = cur.execute(
        f"SELECT count(*) FROM {relation} AS p "
        f"WHERE season = {season} AND NOT ({any_bucket_sql()})"
    ).fetchone()[0]
    assert orphans == 0


# --- shape and idempotency ---------------------------------------------------


def test_derived_tables_are_the_six_the_coverage_endpoint_reports(derived):
    names = derived_tables()
    assert len(names) == 6
    for name in names:
        assert derived.table_exists(name), name
        assert derived.row_count(name) > 0, name


def test_deriving_a_season_twice_produces_identical_row_counts(derived):
    cur = derived.cursor()

    def counts() -> dict[str, int]:
        return {
            name: cur.execute(
                f"SELECT count(*) FROM {name} WHERE season = 2024"
            ).fetchone()[0]
            for name in derived_tables()
        }

    first = counts()
    derive_season(derived, 2024)
    assert counts() == first
    assert all(n > 0 for n in first.values())


def test_game_team_stats_has_one_row_per_team_per_game(derived):
    cur = derived.cursor()
    rows = cur.execute(
        "SELECT game_id, count(*) FROM derived_game_team_stats "
        "GROUP BY game_id ORDER BY 1"
    ).fetchall()
    assert rows and all(n == 2 for _, n in rows)


def test_drives_carry_both_the_text_yard_line_and_the_parsed_one(derived):
    cur = derived.cursor()
    assert cur.execute(
        "SELECT count(*) FROM derived_drives WHERE start_yard_line IS NULL"
    ).fetchone()[0] == 0
    lo, hi = cur.execute(
        "SELECT min(start_yardline_100), max(start_yardline_100) FROM derived_drives"
    ).fetchone()
    assert 1 <= lo and hi <= 99


# --- yard lines --------------------------------------------------------------


def test_the_same_text_yard_line_means_two_things_depending_on_who_has_the_ball(
    built_loader,
):
    """"KC 25" is 75 yards out for Kansas City and 25 for whoever it is playing."""
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "yardline_plays",
        """
        SELECT * FROM (VALUES
          (1998, 1, 'G1', 1, 'KC',  'BUF', 1, 'KC 25', 'BUF 40'),
          (1998, 1, 'G1', 2, 'BUF', 'KC',  2, 'KC 25', 'BUF 40'),
          (1998, 1, 'G1', 3, 'KC',  'BUF', 3, '50',    'KC 12')
        ) AS t(season, week, game_id, play_id, posteam, defteam, fixed_drive,
               drive_start_yard_line, drive_end_yard_line)
        """,
    )
    insert_season(cur, "yardline_plays", 1998, tables=[pbp_derive.table("derived_drives")])

    rows = dict(
        cur.execute(
            "SELECT posteam, start_yardline_100 FROM derived_drives "
            "WHERE season = 1998 AND drive IN (1, 2) ORDER BY drive"
        ).fetchall()
    )
    assert rows["KC"] == 75, "own 25 is 75 yards from the opponent goal line"
    assert rows["BUF"] == 25, "the opponent's 25 is 25 yards from the goal line"

    midfield, end_own_12 = cur.execute(
        "SELECT start_yardline_100, end_yardline_100 FROM derived_drives "
        "WHERE season = 1998 AND drive = 3"
    ).fetchone()
    assert midfield == 50, "midfield carries no team code"
    assert end_own_12 == 88, "ending at your own 12 is 88 yards from scoring"


# --- charting era ------------------------------------------------------------


def test_air_yards_are_null_before_2006_and_present_after(derived):
    cur = derived.cursor()
    charted_2001 = cur.execute(
        "SELECT count(air_yards_total) FROM derived_player_game_epa WHERE season = 2001"
    ).fetchone()[0]
    rows_2001 = cur.execute(
        "SELECT count(*) FROM derived_player_game_epa WHERE season = 2001"
    ).fetchone()[0]
    assert rows_2001 > 0
    assert charted_2001 == 0, "air yards were not charted before 2006; NULL, never 0"
    assert cur.execute(
        "SELECT count(*) FROM derived_player_game_epa "
        "WHERE season = 2001 AND air_yards_total = 0"
    ).fetchone()[0] == 0

    assert cur.execute(
        "SELECT count(air_yards_total) FROM derived_player_game_epa "
        "WHERE season = 2024 AND role = 'receiver'"
    ).fetchone()[0] > 0


# --- the trap: pooled rates, not averaged ones -------------------------------


def test_a_career_rate_pools_the_counts_and_is_not_the_mean_of_season_rates(
    built_loader,
):
    """Two seasons, unequal volume: the pooled rate is the only true one.

    3 of 10 in one season and 3 of 4 in the next is 6 of 14 — 42.9%. The mean of
    30% and 75% is 52.5%, and it is what you get by storing season rates instead of
    season counts. This is the whole reason the derived tables hold counts.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    rows = []
    for season, plays, successes in ((1998, 10, 3), (1999, 4, 3)):
        for i in range(plays):
            rows.append(
                f"({season}, 1, 'G{season}', {i + 1}, 'KC', 'BUF', 1, 10, 50, 1, "
                f"'00-0000001', {1 if i < successes else 0}, 0.5, 5, 0, 900, 0)"
            )
    _plays_table(
        cur,
        "pooled_plays",
        "SELECT * FROM (VALUES " + ",\n".join(rows) + ") AS t("
        "season, week, game_id, play_id, posteam, defteam, down, ydstogo,"
        " yardline_100, qtr, passer_player_id, success, epa, yards_gained,"
        " first_down, half_seconds_remaining, score_differential)",
    )
    situational = pbp_derive.table("derived_player_season_situational")
    for season in (1998, 1999):
        insert_season(cur, "pooled_plays", season, tables=[situational])

    seasons = cur.execute(
        "SELECT season, plays, successes FROM derived_player_season_situational "
        "WHERE bucket = 'down_1' AND role = 'passer' AND season IN (1998, 1999) "
        "ORDER BY season"
    ).fetchall()
    assert [(s, p, k) for s, p, k in seasons] == [(1998, 10, 3), (1999, 4, 3)]

    pooled = cur.execute(
        "SELECT sum(successes)::DOUBLE / sum(plays) "
        "FROM derived_player_season_situational "
        "WHERE bucket = 'down_1' AND role = 'passer' AND season IN (1998, 1999)"
    ).fetchone()[0]
    from_plays = cur.execute(
        "SELECT sum(success)::DOUBLE / count(*) FROM pooled_plays "
        "WHERE passer_player_id IS NOT NULL AND down = 1"
    ).fetchone()[0]
    mean_of_season_rates = sum(k / p for _, p, k in seasons) / len(seasons)

    assert pooled == pytest.approx(from_plays)
    assert pooled == pytest.approx(6 / 14)
    assert mean_of_season_rates == pytest.approx(0.525)
    assert pooled != pytest.approx(mean_of_season_rates), (
        "averaging season rates weights a 4-play season like a 10-play one"
    )


# --- win-probability series --------------------------------------------------


def test_the_wp_series_is_downsampled_towards_the_target(built_loader):
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "long_game_plays",
        """
        SELECT 1998 AS season, 1 AS week, 'LONG' AS game_id, i + 1 AS play_id,
               3600 - i * 9 AS game_seconds_remaining,
               0.4 + (i % 20) / 100.0 AS home_wp,
               0 AS total_home_score, 0 AS total_away_score, 0 AS sp
        FROM range(400) t(i)
        """,
    )
    insert_season(
        cur, "long_game_plays", 1998, tables=[pbp_derive.table("derived_wp_series")]
    )
    kept = cur.execute(
        "SELECT count(*) FROM derived_wp_series WHERE game_id = 'LONG'"
    ).fetchone()[0]
    assert WP_POINTS_PER_GAME <= kept <= WP_POINTS_PER_GAME + 5, kept
    # A short game keeps every play it has rather than being padded.
    assert cur.execute(
        "SELECT count(*) FROM derived_wp_series WHERE game_id = 'LONG' "
        "AND home_wp IS NULL"
    ).fetchone()[0] == 0


def test_the_wp_series_covers_every_game_in_the_season(derived):
    cur = derived.cursor()
    for season in FIXTURE_SEASONS:
        relation = derived.pbp_relation(season)
        games = cur.execute(
            f"SELECT count(DISTINCT game_id) FROM {relation} AS p WHERE season = {season}"
        ).fetchone()[0]
        charted = cur.execute(
            "SELECT count(DISTINCT game_id) FROM derived_wp_series WHERE season = ?",
            [season],
        ).fetchone()[0]
        assert charted == games, season


# --- scoring plays -----------------------------------------------------------


def test_a_scoring_play_carries_the_score_it_produced(built_loader):
    """nflfastR's running totals are the score at the *start* of the play.

    So a touchdown row still says 0-0 and the six points appear on the next row.
    Reading them as post-play scores would put every scoring summary one play out
    of step, which is why this is pinned rather than assumed.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "scoring_plays_src",
        """
        SELECT * FROM (VALUES
          (1998, 1, 'S1', 1, 'KC', 'BUF', 'KC', 'BUF', 0, 0, 0, 0, 0, NULL),
          (1998, 1, 'S1', 2, 'KC', 'BUF', 'KC', 'BUF', 0, 0, 1, 1, 0, NULL),
          (1998, 1, 'S1', 3, 'KC', 'BUF', 'KC', 'BUF', 6, 0, 1, 0, 1, NULL),
          (1998, 1, 'S1', 4, 'BUF', 'KC', 'KC', 'BUF', 7, 0, 0, 0, 0, NULL),
          (1998, 1, 'S1', 5, 'BUF', 'KC', 'KC', 'BUF', 7, 0, 1, 0, 0, 'made'),
          (1998, 1, 'S1', 6, 'KC', 'BUF', 'KC', 'BUF', 7, 3, 0, 0, 0, NULL)
        ) AS t(season, week, game_id, play_id, posteam, defteam, home_team, away_team,
               total_home_score, total_away_score, sp, touchdown,
               extra_point_attempt, field_goal_result)
        """,
    )
    insert_season(
        cur,
        "scoring_plays_src",
        1998,
        tables=[pbp_derive.table("derived_scoring_plays")],
    )
    rows = cur.execute(
        "SELECT play_id, scoring_type, scoring_team, home_score, away_score "
        "FROM derived_scoring_plays WHERE game_id = 'S1' ORDER BY play_id"
    ).fetchall()
    assert rows == [
        (2, "touchdown", "KC", 6, 0),
        (3, "extra_point", "KC", 7, 0),
        (5, "field_goal", "BUF", 7, 3),
    ]


def test_the_running_score_never_goes_backwards(derived):
    cur = derived.cursor()
    backwards = cur.execute(
        """
        SELECT count(*) FROM (
          SELECT home_score - lag(home_score) OVER w AS dh,
                 away_score - lag(away_score) OVER w AS da
          FROM derived_scoring_plays
          WINDOW w AS (PARTITION BY game_id ORDER BY play_id)
        ) WHERE dh < 0 OR da < 0
        """
    ).fetchone()[0]
    assert backwards == 0


# --- one season at a time ----------------------------------------------------


def test_deriving_one_season_never_writes_another_seasons_rows(built_loader):
    built_loader.ensure("pbp")
    derive_season(built_loader, 2001)
    cur = built_loader.cursor()
    for name in derived_tables():
        seasons = [
            row[0]
            for row in cur.execute(f"SELECT DISTINCT season FROM {name}").fetchall()
        ]
        assert seasons == [2001], name


def test_zzz_debug(derived):
    cur = derived.cursor()
    for name in derived_tables():
        print("\n==", name, cur.execute(f"select count(*) from {name}").fetchone())
        print(cur.execute(f"select * from {name} limit 4").df().to_string())
    print(cur.execute("select season, bucket, role, count(*), sum(plays) from derived_player_season_situational group by 1,2,3 order by 1,2,3").df().to_string())
    print(cur.execute("select * from derived_game_team_stats limit 4").df().to_string())
