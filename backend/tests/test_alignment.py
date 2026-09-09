"""Tests for `app.etl.alignment` — league structure, season by season.

No fixture database needed: the alignment table is a pure hand-authored data
structure and the whole point is that it must be right on its own, without a
loader in the loop.
"""

from __future__ import annotations

import pytest

from app.etl import alignment


# -- team and division counts by era -----------------------------------------


@pytest.mark.parametrize("season", [1999, 2000, 2001])
def test_pre_realignment_seasons_have_31_teams_and_6_divisions(season):
    assert len(alignment.teams_in_season(season)) == 31
    assert len(alignment.divisions_in_season(season)) == 6


@pytest.mark.parametrize("season", [2002, 2010, 2019, 2024])
def test_post_realignment_seasons_have_32_teams_and_8_divisions(season):
    assert len(alignment.teams_in_season(season)) == 32
    assert len(alignment.divisions_in_season(season)) == 8


# -- the 2002 realignment itself ---------------------------------------------


def test_seattle_moves_from_afc_west_to_nfc_west_in_2002():
    assert alignment.division_of("SEA", 2001) == ("AFC", "West")
    assert alignment.division_of("SEA", 2002) == ("NFC", "West")


def test_arizona_moves_from_nfc_east_to_nfc_west_in_2002():
    assert alignment.division_of("ARI", 2001) == ("NFC", "East")
    assert alignment.division_of("ARI", 2002) == ("NFC", "West")


def test_houston_did_not_exist_before_2002():
    assert "HOU" not in alignment.teams_in_season(2001)
    assert "HOU" in alignment.teams_in_season(2002)


# -- playoff field and schedule length ---------------------------------------


def test_playoff_seeds_are_6_through_2019_and_7_from_2020():
    assert alignment.playoff_seeds(1999) == 6
    assert alignment.playoff_seeds(2019) == 6
    assert alignment.playoff_seeds(2020) == 7
    assert alignment.playoff_seeds(2025) == 7


def test_regular_season_is_17_weeks_through_2020_and_18_from_2021():
    assert alignment.regular_season_weeks(1999) == 17
    assert alignment.regular_season_weeks(2020) == 17
    assert alignment.regular_season_weeks(2021) == 18
    assert alignment.regular_season_weeks(2025) == 18


# -- code mapping in both directions ------------------------------------------


def test_current_code_maps_relocated_franchises_forward():
    assert alignment.current_code("STL") == "LA"
    assert alignment.current_code("SD") == "LAC"
    assert alignment.current_code("OAK") == "LV"
    assert alignment.current_code("LAR") == "LA"  # a spelling variant, not a relocation
    assert alignment.current_code("KC") == "KC"  # a franchise that never moved is unchanged


def test_code_in_season_maps_the_current_code_back_to_the_period_code():
    assert alignment.code_in_season("LA", 2013) == "STL"
    assert alignment.code_in_season("LA", 2024) == "LA"
    assert alignment.code_in_season("LAC", 2010) == "SD"
    assert alignment.code_in_season("LAC", 2024) == "LAC"
    assert alignment.code_in_season("LV", 2015) == "OAK"
    assert alignment.code_in_season("LV", 2024) == "LV"


def test_label_in_season_names_the_franchise_as_it_was_called_then():
    assert alignment.label_in_season("LA", 2013, "Los Angeles Rams") == "St. Louis Rams"
    assert alignment.label_in_season("LA", 2024, "Los Angeles Rams") == "Los Angeles Rams"


# -- refusing to guess ---------------------------------------------------


def test_division_of_raises_for_a_team_that_did_not_exist_that_season():
    with pytest.raises(KeyError):
        alignment.division_of("HOU", 2001)


def test_alignment_defined_seasons_reject_out_of_window_years():
    # Below FIRST_SEASON and past any authored era: an invented alignment here
    # would silently misgroup standings nobody asked for.
    with pytest.raises(ValueError):
        alignment.playoff_seeds(1990)


# -- the divisions partition the league, with no overlaps --------------------


@pytest.mark.parametrize("season", [1999, 2001, 2002, 2010, 2024])
def test_every_team_has_exactly_one_division_and_nothing_is_double_counted(season):
    seen: set[str] = set()
    era = alignment.alignment(season)
    for conference, divisions in era.items():
        assert conference in ("AFC", "NFC")
        for teams in divisions.values():
            for team in teams:
                assert team not in seen, f"{team} appears in two divisions in {season}"
                seen.add(team)
    assert seen == set(alignment.teams_in_season(season))
