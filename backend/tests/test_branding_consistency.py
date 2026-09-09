"""Every surface that names a franchise must name it the same way.

`teams_colors_logos.csv` carries the pre-relocation clubs alongside the current
ones — STL beside LA, SD beside LAC, OAK beside LV — and they canonicalise onto
the same franchise. Four separate modules read that file and build their own
lookup, and three of them originally took whichever row the file happened to
list last, which is alphabetically the historical one. The Rams' franchise page
introduced itself in the present tense as "St. Louis Rams".

This test exists because the bug is per-reader: fixing one does not fix the
others, and a fifth reader would arrive with the same mistake. It holds every
module that builds a branding map to the same answer.
"""

from __future__ import annotations

import pytest

from app.repo import games as games_repo
from app.repo import search as search_repo
from app.repo import seasons as seasons_repo
from app.repo import teams as teams_repo

#: (historical code, current code, the name the current code must resolve to).
RELOCATIONS = [
    ("STL", "LA", "Los Angeles Rams"),
    ("SD", "LAC", "Los Angeles Chargers"),
    ("OAK", "LV", "Las Vegas Raiders"),
]


@pytest.fixture
def branded_loader(built_loader):
    """The fixture's teams table plus both rows for each relocated franchise."""
    built_loader.ensure("teams_meta")
    cur = built_loader.cursor()
    for old, new, current_name in RELOCATIONS:
        # Current first, historical second — the order the real file uses, and
        # the order under which a last-write-wins merge picks the wrong one.
        for abbr, name in ((new, current_name), (old, f"Historical {old}")):
            cur.execute(
                """
                INSERT INTO teams_meta (team_abbr, team_name, team_nick, team_conf,
                                        team_division, team_color, team_color2,
                                        team_logo_espn, team_logo_squared, team_wordmark)
                VALUES (?, ?, 'Nick', 'NFC', 'NFC West', '#111111', '#222222',
                        'logo', 'sq', 'wm')
                """,
                [abbr, name],
            )
    return built_loader


@pytest.mark.parametrize("old,new,current_name", RELOCATIONS)
def test_teams_repo_prefers_the_current_name(branded_loader, old, new, current_name):
    branding = teams_repo._branding(branded_loader)
    assert branding[new]["name"] == current_name
    assert old not in branding


@pytest.mark.parametrize("old,new,current_name", RELOCATIONS)
def test_seasons_repo_prefers_the_current_name(branded_loader, old, new, current_name):
    branding = seasons_repo._branding(branded_loader)
    assert branding[new]["name"] == current_name
    assert old not in branding


@pytest.mark.parametrize("old,new,current_name", RELOCATIONS)
def test_games_repo_prefers_the_current_name(branded_loader, old, new, current_name):
    branding = games_repo._branding(branded_loader)
    assert branding[new]["name"] == current_name
    assert old not in branding


@pytest.mark.parametrize("old,new,current_name", RELOCATIONS)
def test_search_prefers_the_current_name(branded_loader, old, new, current_name):
    search_repo._TEAM_TABLE_CACHE.clear()
    table = search_repo._team_table(branded_loader)
    by_code = {record.abbr: record for record, _tokens in table}
    assert by_code[new].name == current_name
    assert old not in by_code
