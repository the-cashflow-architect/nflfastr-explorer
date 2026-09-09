"""Tests for the loader — the part of the app that is hardest to get wrong quietly.

Every test here runs against `built_loader`: a real Loader over a real DuckDB
file, built from the locally generated fixtures in `factories.py`. Only the
network call is faked; canonicalisation, the null-team filter, schema widening,
freshness tracking and the play-by-play attach/evict cycle all run for real,
because those are exactly where a passing-looking loader can still be wrong.
"""

from __future__ import annotations

import os

import pytest

from app.config import PBP_CACHE_SEASONS, data_dir
from app.sources import BY_ID


# -- team-code canonicalisation ---------------------------------------------


def test_games_holds_la_for_2001_never_stl(built_loader):
    built_loader.ensure("games")
    cur = built_loader.cursor()
    codes = {
        r[0]
        for r in cur.execute(
            "SELECT home_team FROM games WHERE season = 2001 "
            "UNION SELECT away_team FROM games WHERE season = 2001"
        ).fetchall()
    }
    assert "STL" not in codes
    assert "LA" in codes


def test_games_joins_team_week_with_nothing_unmatched(built_loader):
    """If either side of this join were left in its raw code, half the rows drop.

    `games` and `team_week` are canonicalised independently at load time; this
    is the check that they actually land on the same vocabulary.
    """
    built_loader.ensure("games")
    built_loader.ensure("team_week")
    cur = built_loader.cursor()
    unmatched = cur.execute(
        """
        SELECT count(*) FROM team_week tw
        WHERE tw.team IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM games g
            WHERE g.season = tw.season
              AND (g.home_team = tw.team OR g.away_team = tw.team)
          )
        """
    ).fetchone()[0]
    assert unmatched == 0

    total = cur.execute("SELECT count(*) FROM team_week WHERE team IS NOT NULL").fetchone()[0]
    assert total > 0  # a join that matches everything because there was nothing to match is not a pass


# -- the unattributed null-team row ------------------------------------------


def test_unattributed_row_dropped_from_player_week(built_loader):
    built_loader.ensure("player_week")
    cur = built_loader.cursor()
    assert cur.execute("SELECT count(*) FROM player_week WHERE team IS NULL").fetchone()[0] == 0
    # factories.write_player_week emits 24 real rows plus the one unattributed
    # row per season; if the filter silently stopped working this would be 25.
    per_season = cur.execute(
        "SELECT count(*) FROM player_week WHERE season = 2024"
    ).fetchone()[0]
    assert per_season == 24


def test_unattributed_row_dropped_from_team_week(built_loader):
    built_loader.ensure("team_week")
    cur = built_loader.cursor()
    assert cur.execute("SELECT count(*) FROM team_week WHERE team IS NULL").fetchone()[0] == 0
    per_season = cur.execute("SELECT count(*) FROM team_week WHERE season = 2024").fetchone()[0]
    assert per_season == 16


# -- freshness: a completed season is fetched exactly once ------------------


def test_completed_season_not_redownloaded_on_second_ensure(built_loader):
    calls: list[str] = []
    original_download = built_loader.download  # bound to the fake that serves fixtures

    def counting(url: str) -> str:
        calls.append(url)
        return original_download(url)

    built_loader.download = counting

    built_loader.ensure("team_week")
    first_pass = [u for u in calls if "_2001.parquet" in u]
    assert len(first_pass) == 1, f"expected exactly one fetch of the 2001 file, got {first_pass}"

    calls.clear()
    built_loader.ensure("team_week")
    second_pass = [u for u in calls if "_2001.parquet" in u]
    assert second_pass == [], "a completed season must never be re-downloaded"


# -- schema widening -----------------------------------------------------


def test_schema_widening_backfills_null_for_the_earlier_season(built_loader):
    """`receiving_epa` only exists in nflverse files from 2010 on.

    2001 loads first and has no such column; 2024 introduces it. The table
    must widen rather than fail, and every 2001 row must read NULL for it —
    never 0, which would silently claim a value nobody produced.
    """
    built_loader.ensure("player_week")
    cur = built_loader.cursor()
    columns = {row[0] for row in cur.execute("DESCRIBE player_week").fetchall()}
    assert "receiving_epa" in columns

    total_2001 = cur.execute("SELECT count(*) FROM player_week WHERE season = 2001").fetchone()[0]
    null_2001 = cur.execute(
        "SELECT count(*) FROM player_week WHERE season = 2001 AND receiving_epa IS NULL"
    ).fetchone()[0]
    assert total_2001 > 0
    assert null_2001 == total_2001

    non_null_2024 = cur.execute(
        "SELECT count(*) FROM player_week WHERE season = 2024 AND receiving_epa IS NOT NULL"
    ).fetchone()[0]
    assert non_null_2024 > 0


# -- play-by-play residency and lazy materialisation -------------------------


def test_pbp_relation_resident_season_is_queryable(built_loader):
    """2024 is inside the resident window (LATEST_SEASON=2024, 6 seasons resident).

    `pbp_relation` for it must answer straight from the main table, not attach
    anything.
    """
    relation = built_loader.pbp_relation(2024)
    assert relation.strip().startswith("(SELECT")  # the resident-table form, not an attached alias
    cur = built_loader.cursor()
    count = cur.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    assert count == 48  # factories.write_pbp emits range(48) plays
    seasons = {r[0] for r in cur.execute(f"SELECT DISTINCT season FROM {relation}").fetchall()}
    assert seasons == {2024}


def test_pbp_relation_materialises_an_old_season_on_demand(built_loader):
    """2001 predates the resident window and must be attached from its own file."""
    relation = built_loader.pbp_relation(2001)
    assert relation == "pbp_2001.plays"
    cur = built_loader.cursor()
    count = cur.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    assert count == 48
    assert os.path.exists(os.path.join(data_dir(), "pbp_2001.duckdb"))


def test_pbp_lru_evicts_past_the_cap_and_deletes_the_file(built_loader):
    """One season past the cap must push out the least-recently-used one.

    Eviction is `DETACH` + `os.remove`, not `DROP TABLE` — DuckDB never shrinks
    a database file, so only actually deleting the attached file reclaims disk
    (SPEC 0.9). This test would pass on a broken eviction that forgot the
    `os.remove` if it only checked the attach set, so it checks the filesystem too.
    """
    seasons = list(range(1990, 1990 + PBP_CACHE_SEASONS + 1))  # one more than the cap
    for season in seasons:
        built_loader.pbp_relation(season)

    oldest = seasons[0]
    newest = seasons[-1]
    assert oldest not in built_loader._attached
    assert newest in built_loader._attached
    assert len(built_loader._attached) == PBP_CACHE_SEASONS

    oldest_path = os.path.join(data_dir(), f"pbp_{oldest}.duckdb")
    assert not os.path.exists(oldest_path)
    newest_path = os.path.join(data_dir(), f"pbp_{newest}.duckdb")
    assert os.path.exists(newest_path)


# -- a season with no published file yet -------------------------------------


def test_404_for_an_unpublished_season_is_skipped_not_raised(built_loader):
    """`snap_counts` has no fixture builder, so its one in-window season 404s.

    A season that has not been published yet is the ordinary shape of "the
    current season before it starts" (SPEC, loader.py `_load_season`), and must
    not take the whole `ensure()` call down with it.
    """
    assert BY_ID["snap_counts"].first_season == 2012  # only 2024 of our two fixture seasons qualifies
    built_loader.ensure("snap_counts")  # must not raise
    assert not built_loader.table_exists("snap_counts")
    assert built_loader.row_count("snap_counts") is None


# -- the connection the whole app queries through ---------------------------


def test_duckdb_memory_limit_is_pinned(built_loader):
    """DuckDB defaults to a share of host RAM, which a container does not have.

    Every reader in the app — the Finder's store included — takes its cursor
    from this one connection, so this is where the setting has to hold.
    """
    cur = built_loader.cursor()
    limit = cur.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert limit not in (None, "")
    # Must be well under a small instance; the default would be GB-scale.
    assert "GB" not in limit.upper() or float(limit.upper().split("GB")[0]) <= 1
    order = cur.execute("SELECT current_setting('preserve_insertion_order')").fetchone()[0]
    assert order is False or str(order).lower() == "false"
