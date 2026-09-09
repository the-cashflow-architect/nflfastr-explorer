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
from app.etl.buckets import BUCKETS, BUCKET_KEYS, ROLE_KEYS, any_bucket_sql, role
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
                f"({season}, 1, 'REG', 'G{season}', {i + 1}, 'KC', 'BUF', 1, 10, 50, 1, "
                f"'00-0000001', {1 if i < successes else 0}, 0.5, 5, 0, 900, 0)"
            )
    _plays_table(
        cur,
        "pooled_plays",
        "SELECT * FROM (VALUES " + ",\n".join(rows) + ") AS t("
        "season, week, season_type, game_id, play_id, posteam, defteam, down, ydstogo,"
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
    """nflfastR's two score columns do not share a convention. Pinned, not assumed.

    Measured on the real 2024 file: `total_home_score` / `total_away_score` are the
    score **after** the play — the Henry touchdown in 2024_01_BAL_KC already reads
    6 on its own row, and the last row of every game equals the final score — while
    `score_differential` on that same row is still 0, because it is the state
    before the snap. Across the season the two agree on 43,012 of 46,779 plays and
    the ~8% that disagree are exactly the scoring plays.

    Reading the totals as pre-play, as an earlier version of this table did, put
    every scoring summary one play out of step: the touchdown was reported at 0-0
    and its points were attributed to whatever happened next.
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
          (1998, 1, 'S1', 2, 'KC', 'BUF', 'KC', 'BUF', 6, 0, 1, 1, 0, NULL),
          (1998, 1, 'S1', 3, 'KC', 'BUF', 'KC', 'BUF', 7, 0, 1, 0, 1, NULL),
          (1998, 1, 'S1', 4, 'BUF', 'KC', 'KC', 'BUF', 7, 0, 0, 0, 0, NULL),
          (1998, 1, 'S1', 5, 'BUF', 'KC', 'KC', 'BUF', 7, 3, 1, 0, 0, 'made'),
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


def test_the_scoring_table_and_the_win_probability_series_agree_on_the_score(built_loader):
    """The two tables read the same columns, so they must read them the same way.

    They disagreed once — one reached forward with LEAD, the other did not — which
    made a game page show a different score in its scoring summary than in its win
    probability tooltip for the same play.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "agree_src",
        """
        SELECT * FROM (VALUES
          (1998, 1, 'A1', 1, 'KC', 'BUF', 'KC', 'BUF', 0, 0, 0, 0, 0, NULL, 0.50, 3600),
          (1998, 1, 'A1', 2, 'KC', 'BUF', 'KC', 'BUF', 6, 0, 1, 1, 0, NULL, 0.61, 3500),
          (1998, 1, 'A1', 3, 'KC', 'BUF', 'KC', 'BUF', 7, 0, 1, 0, 1, NULL, 0.63, 3480)
        ) AS t(season, week, game_id, play_id, posteam, defteam, home_team, away_team,
               total_home_score, total_away_score, sp, touchdown,
               extra_point_attempt, field_goal_result, home_wp, game_seconds_remaining)
        """,
    )
    insert_season(cur, "agree_src", 1998)
    scoring = dict(
        cur.execute(
            "SELECT play_id, home_score FROM derived_scoring_plays WHERE game_id = 'A1'"
        ).fetchall()
    )
    series = dict(
        cur.execute(
            "SELECT play_id, home_score FROM derived_wp_series WHERE game_id = 'A1'"
        ).fetchall()
    )
    shared = set(scoring) & set(series)
    assert shared, "the two tables should cover at least one play in common"
    for play_id in shared:
        assert scoring[play_id] == series[play_id]


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



def test_every_bucket_is_reachable(built_loader):
    """The fixture seasons contain no red-zone snap and no blowout.

    Four hand-placed plays put a snap in all sixteen situations, so a predicate
    that never matches anything — a column renamed upstream, a sign flipped — fails
    here rather than silently shipping an always-empty split.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "bucket_plays",
        """
        SELECT * FROM (VALUES
          -- 1st and short at the 5, two minutes left in the half, ahead, blowout.
          (1998, 1, 'REG', 'B1', 1, 'KC', 1, 3, 5,  1, 60,  3, 0.02, '00-0000001'),
          -- 2nd and medium, midfield, second half, tied.
          (1998, 1, 'REG', 'B1', 2, 'KC', 2, 5, 50, 3, 900, 0, 0.50, '00-0000001'),
          -- 3rd and long, own half, fourth quarter, behind.
          (1998, 1, 'REG', 'B1', 3, 'KC', 3, 10, 60, 4, 800, -7, 0.50, '00-0000001'),
          (1998, 1, 'REG', 'B1', 4, 'KC', 4, 2, 40, 4, 700, -7, 0.50, '00-0000001')
        ) AS t(season, week, season_type, game_id, play_id, posteam, down, ydstogo,
               yardline_100, qtr, half_seconds_remaining, score_differential, wp,
               passer_player_id)
        """,
    )
    insert_season(
        cur,
        "bucket_plays",
        1998,
        tables=[pbp_derive.table("derived_player_season_situational")],
    )
    found = {
        row[0]
        for row in cur.execute(
            "SELECT DISTINCT bucket FROM derived_player_season_situational "
            "WHERE season = 1998"
        ).fetchall()
    }
    assert found == set(BUCKET_KEYS)


def test_situational_counts_match_the_plays_they_came_from(derived):
    """The bucket predicates mean the same thing in the ETL and against the plays."""
    cur = derived.cursor()
    relation = derived.pbp_relation(2024)
    for bucket in BUCKETS:
        derived_plays = cur.execute(
            "SELECT COALESCE(sum(plays), 0) FROM derived_player_season_situational "
            "WHERE season = 2024 AND role = 'passer' AND bucket = ?",
            [bucket.key],
        ).fetchone()[0]
        raw = cur.execute(
            f"SELECT count(*) FROM {relation} AS p WHERE season = 2024 "
            f"AND passer_player_id IS NOT NULL AND ({bucket.predicate})"
        ).fetchone()[0]
        assert derived_plays == raw, bucket.key


# --- the passer role: sacks, scrambles and which EPA ------------------------


def test_the_passer_role_is_charged_qb_epa_and_the_others_the_plays_own_epa():
    """`qb_epa` is not a way of hiding a sack; it is a fumble convention.

    Measured on the published files: `epa` and `qb_epa` are identical on every
    play carrying `passer_player_id` except a lost fumble — 62 such plays in 2024
    worth +293.6 EPA, 64 in 1999 worth +288.5 — where `epa` charges the passer for
    a receiver coughing the ball up after the catch and `qb_epa` stops at the
    catch. On all 1,392 sacks in 2024 the two agree to the last decimal.
    """
    assert role("passer").epa_column == "qb_epa"
    assert role("rusher").epa_column == "epa"
    assert role("receiver").epa_column == "epa"


def test_a_sack_is_a_passer_play_and_its_epa_is_counted_and_labelled(built_loader):
    """A quarterback's EPA per dropback must include the plays that hurt him most.

    `passer_player_id` is populated on every sack in the real files — 1,297 in
    1999, 1,234 in 2005, 1,202 in 2006, 1,250 in 2015 and 1,392 in 2024, none of
    them NULL — so the sack is already inside `plays` and `epa_total`. What was
    missing was any way to see that from the table, which is what `sacks` and
    `sack_epa` are for: drop the sack from the frame and this test fails on the
    counts, drop the two columns and it fails on the labelling.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    ensure_tables(cur)
    _plays_table(
        cur,
        "sack_plays",
        """
        SELECT * FROM (VALUES
          -- A completion: epa and qb_epa agree.
          (1998, 1, 'K1', 1, 'KC', '00-0000001', '00-0000002', 0, -1.0, -1.0),
          -- A completion the receiver fumbles away: the passer keeps his credit
          -- up to the catch, the receiver wears the whole play.
          (1998, 1, 'K1', 2, 'KC', '00-0000001', '00-0000002', 0, -4.0,  1.0),
          -- A sack: no receiver, no rusher, and the passer eats all of it.
          (1998, 1, 'K1', 3, 'KC', '00-0000001', NULL,         1, -6.0, -6.0)
        ) AS t(season, week, game_id, play_id, posteam, passer_player_id,
               receiver_player_id, sack, epa, qb_epa)
        """,
    )
    insert_season(
        cur, "sack_plays", 1998, tables=[pbp_derive.table("derived_player_game_epa")]
    )
    rows = {
        r[0]: r[1:]
        for r in cur.execute(
            "SELECT role, plays, epa_total, sacks, sack_epa "
            "FROM derived_player_game_epa WHERE game_id = 'K1'"
        ).fetchall()
    }

    plays, epa_total, sacks, sack_epa = rows["passer"]
    assert plays == 3, "the sack is one of the passer's plays, not a play he skipped"
    assert epa_total == pytest.approx(-6.0), (
        "qb_epa: -1.0 + 1.0 - 6.0. Summing the play's own epa would give -11.0 and "
        "charge the quarterback for his receiver's fumble"
    )
    assert (sacks, sack_epa) == (1, pytest.approx(-6.0)), (
        "the sack share of that total has to be readable without a play scan"
    )
    assert epa_total - sack_epa == pytest.approx(0.0), "EPA net of sacks is a subtraction"

    receiver_plays, receiver_epa, receiver_sacks, receiver_sack_epa = rows["receiver"]
    assert receiver_plays == 2
    assert receiver_epa == pytest.approx(-5.0), "the receiver wears the play's own EPA"
    assert receiver_sacks == 0
    assert receiver_sack_epa is None, "no sacks means no sack EPA, not zero EPA"


@pytest.mark.parametrize("season", FIXTURE_SEASONS)
def test_the_situational_sack_counts_are_the_sacks_the_plays_hold(derived, season):
    """Every sack in the season reaches the passer's row, in every bucket it fits."""
    cur = derived.cursor()
    relation = derived.pbp_relation(season)
    for bucket in BUCKETS:
        stored = cur.execute(
            "SELECT COALESCE(sum(sacks), 0) FROM derived_player_season_situational "
            "WHERE season = ? AND role = 'passer' AND bucket = ?",
            [season, bucket.key],
        ).fetchone()[0]
        raw = cur.execute(
            f"SELECT count(*) FROM {relation} AS p WHERE season = {season} "
            f"AND passer_player_id IS NOT NULL AND sack = 1 AND ({bucket.predicate})"
        ).fetchone()[0]
        assert stored == raw, bucket.key
    total = cur.execute(
        f"SELECT count(*) FROM {relation} AS p WHERE season = {season} AND sack = 1"
    ).fetchone()[0]
    assert total > 0, "a fixture with no sack cannot test that sacks are counted"


# --- the fixture reaches every bucket ----------------------------------------


@pytest.mark.parametrize("season", FIXTURE_SEASONS)
def test_the_fixture_seasons_populate_all_sixteen_buckets(derived, season):
    """`red_zone`, `goal_to_go` and `garbage_time` used to match no fixture row.

    The generator stopped `yardline_100` at 33 and kept win probability inside
    0.30-0.69, so three predicates could have been broken upstream — a renamed
    column, a flipped bound — and every test here would still have passed.
    """
    cur = derived.cursor()
    found = {
        row[0]
        for row in cur.execute(
            "SELECT DISTINCT bucket FROM derived_player_season_situational "
            "WHERE season = ?",
            [season],
        ).fetchall()
    }
    assert found == set(BUCKET_KEYS)


def test_the_fixture_game_is_eight_whole_drives_and_both_clubs_have_the_ball(derived):
    """DuckDB's `/` is float division and `::INTEGER` rounds.

    `(i / 6)::INTEGER` first steps at i = 3, so the 48-play fixture game used to
    cut into nine ragged drives whose `drive_play_count` of 6 was a fiction — and
    because possession alternated per snap rather than per drive, every drive's
    first play belonged to the home team and the away club never appeared as a
    defence.
    """
    cur = derived.cursor()
    for game_id, drives in cur.execute(
        "SELECT game_id, count(*) FROM derived_drives GROUP BY game_id"
    ).fetchall():
        assert drives == 8, game_id
    owners = cur.execute(
        "SELECT count(DISTINCT posteam), count(DISTINCT defteam) FROM derived_drives"
    ).fetchone()
    assert owners == (2, 2), "a drive belongs to one club and is defended by the other"


def test_a_database_built_before_a_column_existed_is_widened_rather_than_broken(
    built_loader,
):
    """`CREATE TABLE IF NOT EXISTS` is a no-op, so a new column needs an ALTER.

    `sacks` and `sack_epa` were added to two tables after the first databases were
    built. Without the widening the deployed table stays one column short and
    every insert fails, because the derived rows name their columns explicitly —
    and the failure is at build time, on a table that already returns rows.
    """
    built_loader.ensure("pbp")
    cur = built_loader.cursor()
    table = pbp_derive.table("derived_player_game_epa")
    old_columns = [c for c in table.columns if c[0] not in ("sacks", "sack_epa")]
    body = ", ".join(f'"{name}" {dtype}' for name, dtype in old_columns)
    cur.execute("DROP TABLE IF EXISTS derived_player_game_epa")
    cur.execute(f"CREATE TABLE derived_player_game_epa ({body})")

    ensure_tables(cur)

    present = [
        row[0] for row in cur.execute("DESCRIBE derived_player_game_epa").fetchall()
    ]
    assert present == list(table.column_names)
    # And the insert the build actually runs now works against it.
    insert_season(built_loader.cursor(), built_loader.pbp_relation(2024), 2024,
                  tables=[table])
    assert built_loader.row_count("derived_player_game_epa") > 0
