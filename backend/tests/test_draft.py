"""Tests for `app.repo.draft` and the two draft endpoints.

`draft_picks` and `combine` both 404 through `conftest.fixture_file` — neither is
modelled there, and `factories.py` is shared, so per this package's return notes
the fixture data is built directly here rather than by editing that file. `_seed`
below writes the two tables straight into the loader's DuckDB with the real
column names (verified against the actual nflverse `draft_picks.parquet` and
`combine.parquet`, not guessed) and backdates a `_source_log` row for each so
`loader.ensure(...)` finds them already "loaded" and never tries to download.

The fixture models, deliberately, every sharp edge this package's job description
calls out:

* a pick whose PFR-era team code the alignment table cannot resolve (`STL` at a
  season that belongs to neither the Cardinals nor the Rams era) — `team` comes
  back `None`, `pfr_team_code` still shows the raw code;
* a pick with no `gsis_id` — renders as text, never a fabricated link;
* one combine `pfr_id` that is unique (an "exact" match) and one that appears
  twice (an ambiguous match, which must come back exactly like no match at all);
* a still-active class (2021) whose picks carry no `games` or `w_av` yet, to
  prove those come back `None` rather than `0`;
* a cohort of five older classes (2015-2019) whose known round medians make the
  best-value-by-round delta on the 2020 class arithmetic, not just plausible.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app import main
from app.repo import draft as draft_repo
from app.routers import draft as draft_router

FIRST = draft_repo.sources.DRAFT_FIRST_SEASON  # 1980, measured — see sources.py

# Cohort classes: round 1 w_av = 10,20,30,40,50; round 2 w_av = 4,8,12,16,20.
# `built_loader` pins LATEST_SEASON to 2024, so the five-seasons-old cutoff the
# repo computes is 2019 — every one of these years lands inside the cohort, none
# of 2020 or 2021 does. (1999's lone round-1 pick is in the cohort too and
# shifts its median — see the best-value test for the arithmetic.)
_COHORT_YEARS = (2015, 2016, 2017, 2018, 2019)
_COHORT_R1_AV = (10, 20, 30, 40, 50)
_COHORT_R2_AV = (4, 8, 12, 16, 20)

_DRAFT_COLUMNS = (
    "season", "round", "pick", "team", "gsis_id", "pfr_player_id",
    "pfr_player_name", "hof", "position", "college", "age", "to", "games",
    "seasons_started", "allpro", "probowls", "w_av", "dr_av",
)


def _draft_row(**kw: Any) -> tuple:
    return tuple(kw[c] for c in _DRAFT_COLUMNS)


def _seed(loader: Any) -> None:
    cur = loader.cursor()
    cur.execute(
        """
        CREATE TABLE draft_picks (
            season INTEGER, round INTEGER, pick INTEGER, team VARCHAR,
            gsis_id VARCHAR, pfr_player_id VARCHAR, pfr_player_name VARCHAR,
            hof BOOLEAN, position VARCHAR, college VARCHAR, age INTEGER,
            "to" INTEGER, games INTEGER, seasons_started INTEGER,
            allpro INTEGER, probowls INTEGER, w_av INTEGER, dr_av INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE combine (
            pfr_id VARCHAR, forty DOUBLE, bench DOUBLE, vertical DOUBLE,
            broad_jump DOUBLE, cone DOUBLE, shuttle DOUBLE
        )
        """
    )

    rows: list[tuple] = []
    for year, r1_av, r2_av in zip(_COHORT_YEARS, _COHORT_R1_AV, _COHORT_R2_AV):
        rows.append(_draft_row(
            season=year, round=1, pick=1, team="KAN", gsis_id=f"00-00{year}1",
            pfr_player_id=f"PFR{year}A", pfr_player_name=f"Cohort R1 {year}",
            hof=False, position="QB", college="State", age=22, to=year + 5,
            games=50, seasons_started=5, allpro=0, probowls=0, w_av=r1_av, dr_av=r1_av,
        ))
        rows.append(_draft_row(
            season=year, round=2, pick=40, team="KAN", gsis_id=f"00-00{year}2",
            pfr_player_id=f"PFR{year}B", pfr_player_name=f"Cohort R2 {year}",
            hof=False, position="RB", college="State", age=22, to=year + 3,
            games=30, seasons_started=2, allpro=0, probowls=0, w_av=r2_av, dr_av=r2_av,
        ))

    # 1999: the sole pick's team code (`HOU`) falls in the gap between the
    # Oilers-as-Titans era (through 1996) and the Texans era (from 2002) —
    # genuinely unresolvable, and `franchise_from_draft_code` must say so.
    rows.append(_draft_row(
        season=1999, round=1, pick=1, team="HOU", gsis_id="00-0019991",
        pfr_player_id="PFR1999A", pfr_player_name="Old Timer", hof=False,
        position="DE", college="Old State", age=22, to=2005, games=80,
        seasons_started=6, allpro=0, probowls=1, w_av=25, dr_av=25,
    ))

    # 2020: the class under test.
    rows.append(_draft_row(  # exact combine match, best value in round 1
        season=2020, round=1, pick=1, team="KAN", gsis_id="00-0020001",
        pfr_player_id="PFR2020A", pfr_player_name="Star Rookie", hof=False,
        position="QB", college="Ohio State", age=22, to=2023, games=40,
        seasons_started=3, allpro=1, probowls=2, w_av=45, dr_av=40,
    ))
    rows.append(_draft_row(  # no gsis_id at all -> renders as text, never a guess
        season=2020, round=1, pick=2, team="GNB", gsis_id=None,
        pfr_player_id=None, pfr_player_name="Never Signed", hof=False,
        position="RB", college="Directional State", age=23, to=None, games=None,
        seasons_started=0, allpro=0, probowls=0, w_av=5, dr_av=5,
    ))
    rows.append(_draft_row(  # unresolvable team code; also the class's lone HOF pick
        season=2020, round=2, pick=50, team="STL", gsis_id="00-0020050",
        pfr_player_id="PFR2020C", pfr_player_name="Ambiguous Team Pick", hof=True,
        position="CB", college="Z State", age=21, to=2021, games=10,
        seasons_started=1, allpro=0, probowls=0, w_av=8, dr_av=8,
    ))
    rows.append(_draft_row(  # pfr_id that resolves to two combine rows -> ambiguous, not a guess
        season=2020, round=2, pick=51, team="KAN", gsis_id="00-0020051",
        pfr_player_id="PFRDUP", pfr_player_name="Combine Ambiguous", hof=False,
        position="WR", college="Q State", age=22, to=2022, games=20,
        seasons_started=2, allpro=0, probowls=0, w_av=12, dr_av=12,
    ))

    # 2021: a class one season old — no career has had time to happen yet.
    rows.append(_draft_row(
        season=2021, round=1, pick=1, team="KAN", gsis_id="00-0021001",
        pfr_player_id="PFR2021A", pfr_player_name="Next Year Guy", hof=False,
        position="OT", college="W State", age=21, to=None, games=None,
        seasons_started=0, allpro=0, probowls=0, w_av=None, dr_av=None,
    ))

    cur.executemany(
        f"INSERT INTO draft_picks VALUES ({', '.join('?' * len(_DRAFT_COLUMNS))})",
        rows,
    )

    combine_rows = [
        ("PFR2020A", 4.4, 20.0, 38.0, 125.0, 6.9, 4.1),  # unique -> exact match
        ("PFRDUP", 4.5, 18.0, 35.0, 118.0, 7.1, 4.3),     # duplicate pfr_id...
        ("PFRDUP", 4.6, 17.0, 34.0, 116.0, 7.2, 4.4),     # ...ambiguous, not a guess
    ]
    cur.executemany("INSERT INTO combine VALUES (?, ?, ?, ?, ?, ?, ?)", combine_rows)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total_rows = len(rows)
    cur.execute(
        "INSERT INTO _source_log VALUES ('draft_picks', NULL, ?, ?)", [now, total_rows]
    )
    cur.execute(
        "INSERT INTO _source_log VALUES ('combine', NULL, ?, ?)", [now, len(combine_rows)]
    )


def _loader(built_loader):
    _seed(built_loader)
    return built_loader


# --- app.repo.draft ----------------------------------------------------------


def test_index_lists_every_class_with_pick_counts_and_first_overall(built_loader):
    loader = _loader(built_loader)
    index = draft_repo.draft_index(loader=loader)
    assert index["first_season"] == FIRST
    by_year = {row["year"]: row for row in index["years"]}
    assert by_year[2020]["picks"] == 4
    assert by_year[2020]["first_overall"]["player"] == "Star Rookie"
    assert by_year[2020]["first_overall"]["team"] == "KC"
    assert by_year[2020]["first_overall"]["team_href"] == "/teams/KC"
    # Newest first.
    years = [row["year"] for row in index["years"]]
    assert years == sorted(years, reverse=True)


def test_index_first_overall_omits_an_unresolvable_team_rather_than_guessing(built_loader):
    loader = _loader(built_loader)
    index = draft_repo.draft_index(loader=loader)
    by_year = {row["year"]: row for row in index["years"]}
    first = by_year[1999]["first_overall"]
    assert first["player"] == "Old Timer"
    assert first["team"] is None
    assert first["team_href"] is None


def test_class_board_resolves_team_through_the_season(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    by_player = {p["player"]: p for p in cls["picks"]}
    assert by_player["Star Rookie"]["team"] == "KC"
    assert by_player["Star Rookie"]["team_href"] == "/teams/KC"


def test_class_board_unresolvable_team_keeps_the_raw_code_but_no_link(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    pick = next(p for p in cls["picks"] if p["player"] == "Ambiguous Team Pick")
    assert pick["team"] is None
    assert pick["team_href"] is None
    assert pick["pfr_team_code"] == "STL"


def test_class_board_pick_with_no_gsis_id_has_no_player_link(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    pick = next(p for p in cls["picks"] if p["player"] == "Never Signed")
    assert pick["gsis_id"] is None
    assert pick["player_href"] is None


def test_class_board_combine_exact_match(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    pick = next(p for p in cls["picks"] if p["player"] == "Star Rookie")
    assert pick["combine_match_confidence"] == "exact"
    assert pick["combine"]["forty"] == 4.4
    assert pick["combine"]["broad"] == 125.0


def test_class_board_ambiguous_combine_id_renders_blank_not_a_guess(built_loader):
    """A deliberately ambiguous pfr_id (two combine rows) must never pick one."""
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    pick = next(p for p in cls["picks"] if p["player"] == "Combine Ambiguous")
    assert pick["combine"] is None
    assert pick["combine_match_confidence"] is None


def test_class_board_no_combine_row_is_a_plain_miss(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    pick = next(p for p in cls["picks"] if p["player"] == "Ambiguous Team Pick")
    assert pick["combine"] is None
    assert pick["combine_match_confidence"] is None


def test_class_board_unplayed_class_has_null_not_zero(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2021, loader=loader)
    pick = cls["picks"][0]
    assert pick["games"] is None
    assert pick["w_av"] is None
    assert cls["summary"]["median_games"] is None


def test_class_board_car_av_never_appears(built_loader):
    """car_av is 100% NULL in the real source; the field must not exist at all."""
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    for pick in cls["picks"]:
        assert "car_av" not in pick
    assert "w_av" in cls["av_note"] or "w_av" in cls["picks"][0]


def test_class_board_summary_tiles(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    summary = cls["summary"]
    assert summary["picks"] == 4
    assert summary["pro_bowlers"] == 1  # Star Rookie, probowls=2
    assert summary["all_pros"] == 1     # Star Rookie, allpro=1
    assert summary["hof"] == 1          # Ambiguous Team Pick
    # games present: Star Rookie 40, Ambiguous Team Pick 10, Combine Ambiguous 20
    # (Never Signed excluded, games is None) -> sorted [10, 20, 40] -> median 20.
    assert summary["median_games"] == 20


def test_class_board_best_value_by_round_uses_the_five_season_cohort(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    by_round = {entry["round"]: entry for entry in cls["best_value"]}
    # Round 1 cohort is every round-1 w_av from a class at least five seasons
    # old: the five cohort years (10,20,30,40,50) plus 1999's "Old Timer" (25) —
    # sorted [10,20,25,30,40,50], median 27.5. Star Rookie (45, delta 17.5)
    # beats Never Signed (5, delta -22.5).
    assert by_round[1]["player"] == "Star Rookie"
    assert by_round[1]["slot_median_av"] == 27.5
    assert by_round[1]["delta"] == 17.5
    # Round 2 cohort median is 12 (4,8,12,16,20). Combine Ambiguous (12, delta 0)
    # beats Ambiguous Team Pick (8, delta -4).
    assert by_round[2]["player"] == "Combine Ambiguous"
    assert by_round[2]["slot_median_av"] == 12
    assert by_round[2]["delta"] == 0
    cohort = cls["best_value_cohort"]
    assert cohort["first_season"] == FIRST
    assert cohort["last_season"] == 2019  # latest_season() (2024, pinned) - 5
    assert cohort["note"]


def test_class_board_best_value_excludes_picks_with_no_w_av(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2021, loader=loader)
    # The lone 2021 pick has w_av=None; it cannot be ranked and best_value must
    # not fabricate a delta for it.
    assert cls["best_value"] == []


def test_class_board_team_filter_narrows_only_the_picks_list(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, team="KC", loader=loader)
    names = {p["player"] for p in cls["picks"]}
    assert names == {"Star Rookie", "Combine Ambiguous"}
    # Summary and best_value still describe the whole class, not the filtered one.
    assert cls["summary"]["picks"] == 4
    assert {e["round"] for e in cls["best_value"]} == {1, 2}


def test_class_board_round_filter_narrows_only_the_picks_list(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, round=1, loader=loader)
    names = {p["player"] for p in cls["picks"]}
    assert names == {"Star Rookie", "Never Signed"}
    assert cls["summary"]["picks"] == 4


def test_class_board_team_filters_omit_unresolved_teams(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    codes = {tf["team"] for tf in cls["team_filters"]}
    assert codes == {"KC", "GB"}  # STL (Ambiguous Team Pick) cannot resolve


def test_class_board_sibling_navigation(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    assert cls["prev_year"] == 2019
    assert cls["next_year"] == 2021


def test_class_board_rounds_reflect_what_the_class_actually_has(built_loader):
    loader = _loader(built_loader)
    cls = draft_repo.draft_class(2020, loader=loader)
    assert cls["rounds"] == [1, 2]


def test_class_board_returns_none_for_a_year_with_no_picks(built_loader):
    loader = _loader(built_loader)
    assert draft_repo.draft_class(1955, loader=loader) is None


# --- HTTP surface --------------------------------------------------------------

_MOUNTED = False


def _client() -> TestClient:
    global _MOUNTED
    if not _MOUNTED:
        main.app.include_router(draft_router.router)
        _MOUNTED = True
    return TestClient(main.app)


def test_get_draft_index_http(built_loader):
    _loader(built_loader)
    response = _client().get("/api/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["first_season"] == FIRST
    years = {row["year"] for row in body["years"]}
    assert {1999, 2015, 2020, 2021}.issubset(years)


def test_get_draft_class_http(built_loader):
    _loader(built_loader)
    response = _client().get("/api/draft/2020")
    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2020
    assert len(body["picks"]) == 4
    assert body["best_value_cohort"]["last_season"] == 2019


def test_get_draft_class_http_filters(built_loader):
    _loader(built_loader)
    response = _client().get("/api/draft/2020", params={"team": "KC"})
    assert response.status_code == 200
    body = response.json()
    assert {p["player"] for p in body["picks"]} == {"Star Rookie", "Combine Ambiguous"}


def test_get_draft_class_http_404_for_unknown_year(built_loader):
    _loader(built_loader)
    response = _client().get("/api/draft/1955")
    assert response.status_code == 404
