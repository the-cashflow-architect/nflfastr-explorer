"""Tests for `app.etl.franchises` — resolving PFR's draft-code dialect.

`draft_picks` is the one source keyed on Pro-Football-Reference's own codes,
three of which are reused for a different franchise in a different era. The
whole point of this module is refusing to guess in the gap years, so the gap
years are exactly what these tests check.
"""

from __future__ import annotations

import pytest

from app.etl import franchises


# -- codes PFR reuses for a different franchise in a different era -----------


def test_stl_is_the_cardinals_then_the_rams_then_nothing():
    assert franchises.franchise_from_draft_code("STL", 1985) == "ARI"
    assert franchises.franchise_from_draft_code("STL", 2000) == "LA"
    # 1988-1994: the Cardinals had already left, the Rams hadn't arrived yet.
    assert franchises.franchise_from_draft_code("STL", 1990) is None


def test_hou_is_the_oilers_then_nothing_then_the_texans():
    assert franchises.franchise_from_draft_code("HOU", 1990) == "TEN"
    assert franchises.franchise_from_draft_code("HOU", 2010) == "HOU"
    # 1997-2001: Houston had no NFL team at all.
    assert franchises.franchise_from_draft_code("HOU", 1999) is None


def test_bal_is_the_colts_then_a_gap_then_the_ravens():
    assert franchises.franchise_from_draft_code("BAL", 1982) == "IND"
    assert franchises.franchise_from_draft_code("BAL", 2000) == "BAL"


# -- PFR's own spelling of everyone else --------------------------------------


@pytest.mark.parametrize(
    "pfr_code, current_code",
    [
        ("GNB", "GB"),
        ("KAN", "KC"),
        ("NWE", "NE"),
        ("SFO", "SF"),
        ("TAM", "TB"),
        ("NOR", "NO"),
        ("RAM", "LA"),
        ("RAI", "LV"),
        ("SDG", "LAC"),
        ("LVR", "LV"),
        ("PHO", "ARI"),
    ],
)
def test_pfr_spellings_map_to_the_current_code(pfr_code, current_code):
    assert franchises.franchise_from_draft_code(pfr_code, 2020) == current_code


# -- refusing to guess ---------------------------------------------------


def test_none_code_resolves_to_none():
    assert franchises.franchise_from_draft_code(None, 2020) is None
    assert franchises.franchise_from_draft_code("", 2020) is None


def test_era_code_with_no_season_given_is_ambiguous_and_resolves_to_none():
    # Without a season, STL/HOU/BAL cannot be resolved at all — picking either
    # franchise would be a guess, not a lookup.
    assert franchises.franchise_from_draft_code("STL", None) is None
    assert franchises.franchise_from_draft_code("HOU", None) is None
    assert franchises.franchise_from_draft_code("BAL", None) is None
