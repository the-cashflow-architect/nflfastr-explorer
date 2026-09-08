"""Standings, ratings and seeding.

The `built_loader` fixture's league is eight clubs wide — enough to prove the
arithmetic, the null-score filter and the era-correct division names, and not enough
to prove that 2001 has six divisions and 2024 has eight. So these tests work at two
scales. The small fixture is used as it is, and a full 31- and 32-club league is
generated into the same real `games` table for the structural claims. Both are
offline; neither invents a column name the real file does not have.

Three of the seeding tests are real history, spelled out game by game, and they are
the three outcomes the derivation has to tell apart: the 2015 AFC bracket, which its
own results pin down completely; the 2004 AFC, which fixes the byes and cannot
separate the third seed from the fourth; and the 2001 NFC, where nothing but the
regular season separates anybody. Saying which of those happened, on the row, is the
point of the exercise.
"""

from __future__ import annotations

import pytest

from app.etl import alignment
from app.etl import standings as etl
from app.repo import standings as repo


# --- helpers -----------------------------------------------------------------


def _game(game_id, season, game_type, week, home, away, home_score, away_score,
          neutral=False):
    return etl.Game(
        game_id=game_id, season=season, game_type=game_type, week=week,
        home=home, away=away, home_score=home_score, away_score=away_score,
        neutral=neutral,
    )


def _db_row(game):
    """One `Game` in the column order the real games table uses."""
    return (
        game.game_id, game.season, game.game_type, game.week,
        game.home, game.home_score, game.away, game.away_score,
        "Neutral" if game.neutral else "Home",
    )


def _replace_games(loader, rows):
    """Put a synthetic schedule in the games table the loader already built.

    Team codes go in already canonicalised, because that is the state the loader
    leaves the real file in — a 2001 row says LA, never STL.
    """
    loader.ensure("games")
    cur = loader.cursor()
    columns = [
        "game_id", "season", "game_type", "week",
        "home_team", "home_score", "away_team", "away_score", "location",
    ]
    present = {row[0] for row in cur.execute("DESCRIBE games").fetchall()}
    assert set(columns) <= present, sorted(set(columns) - present)
    cur.execute("DELETE FROM games")
    cur.executemany(
        f"INSERT INTO games ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        rows,
    )


def _power_order(season):
    """Clubs strongest first: division by division, alphabetical inside each.

    Ordering this way means the strongest club in every division is unambiguous, so
    a generated season has exactly one possible set of division winners.
    """
    order = []
    for conference, division in alignment.divisions_in_season(season):
        order.extend(sorted(alignment.alignment(season)[conference][division]))
    return order


def _intended_seeds(season):
    """{conference: [team in seed order]} for a generated season."""
    order = _power_order(season)
    seeds = alignment.playoff_seeds(season)
    out = {}
    for conference in ("AFC", "NFC"):
        divisions = alignment.alignment(season)[conference]
        winners = [sorted(members)[0] for members in divisions.values()]
        winners.sort(key=order.index)
        rest = [t for t in order if t in _conference_teams(season, conference)
                and t not in winners]
        out[conference] = (winners + rest)[:seeds]
    return out


def _conference_teams(season, conference):
    return {
        team
        for members in alignment.alignment(season)[conference].values()
        for team in members
    }


def _full_league(season, *, postseason=True):
    """A whole league-season: a single round robin, then a bracket.

    A round robin makes the record order identical to the power order — a club beats
    exactly the clubs below it — so the division winners and the seeds a correct
    implementation must produce are known before the ETL runs.
    """
    order = _power_order(season)
    strength = {team: len(order) - i for i, team in enumerate(order)}
    weeks = alignment.regular_season_weeks(season)
    rows = []
    index = 0
    for i, home_side in enumerate(order):
        for away_side in order[i + 1:]:
            home, away = (home_side, away_side) if index % 2 == 0 else (away_side, home_side)
            margin = 3 + (abs(strength[home] - strength[away]) % 14)
            if strength[home] > strength[away]:
                home_score, away_score = 17 + margin, 17
            else:
                home_score, away_score = 17, 17 + margin
            week = 1 + index % weeks
            rows.append((
                f"{season}_{week:02d}_{away}_{home}_{index}", season, "REG", week,
                home, home_score, away, away_score, "Home",
            ))
            index += 1
    if postseason:
        rows.extend(_full_bracket(season))
    return rows


def _full_bracket(season):
    """The bracket the intended seeding would have produced, higher seed always winning."""
    seeds = alignment.playoff_seeds(season)
    byes = seeds - 2 * ((seeds - 1) // 2)
    rows = []
    finalists = {}
    for conference, field_teams in _intended_seeds(season).items():
        seat = {index + 1: team for index, team in enumerate(field_teams)}
        alive = list(range(1, byes + 1))
        for j in range(1, (seeds - 1) // 2 + 1):
            host, visitor = byes + j, seeds + 1 - j
            rows.append(_post_row(season, "WC", 19, conference, seat[host], seat[visitor]))
            alive.append(host)
        for round_code, week in (("DIV", 20), ("CON", 21)):
            alive.sort()
            pairs = [(alive[i], alive[len(alive) - 1 - i]) for i in range(len(alive) // 2)]
            for host, visitor in pairs:
                rows.append(_post_row(season, round_code, week, conference,
                                      seat[host], seat[visitor]))
            alive = [host for host, _ in pairs]
        finalists[conference] = seat[alive[0]]
    rows.append((
        f"{season}_22_{finalists['NFC']}_{finalists['AFC']}", season, "SB", 22,
        finalists["AFC"], 27, finalists["NFC"], 20, "Neutral",
    ))
    return rows


def _post_row(season, round_code, week, conference, host, visitor):
    return (
        f"{season}_{week}_{visitor}_{host}", season, round_code, week,
        host, 27, visitor, 20, "Home",
    )


def _built(loader, rows):
    _replace_games(loader, rows)
    return etl.build(loader)


def _table(loader, season):
    cur = loader.cursor()
    return {
        row[0]: row
        for row in cur.execute(
            "SELECT team, conference, division, wins, losses, ties, playoff_seed, "
            "projected, seed_basis, won_division, srs, osrs, dsrs, sos, "
            "points_for, points_against, games "
            "FROM team_standings WHERE season = ?", [season],
        ).fetchall()
    }


# --- the small fixture -------------------------------------------------------


def test_build_covers_both_fixture_seasons(built_loader):
    report = etl.build(built_loader)
    assert report.seasons == (2001, 2024)
    assert built_loader.row_count(etl.TABLE) == report.rows > 0


def test_division_names_come_from_the_season_not_from_today(built_loader):
    etl.build(built_loader)
    # Baltimore and Cincinnati shared the AFC Central until the 2002 realignment
    # moved them into the AFC North. teams_colors_logos.csv only knows the latter.
    assert _table(built_loader, 2001)["BAL"][2] == "Central"
    assert _table(built_loader, 2024)["BAL"][2] == "North"


@pytest.mark.parametrize("season", [2001, 2024])
def test_wins_plus_losses_plus_ties_is_twice_the_played_games(built_loader, season):
    etl.build(built_loader)
    cur = built_loader.cursor()
    played = cur.execute(
        "SELECT count(*) FROM games WHERE season = ? AND game_type = 'REG' "
        "AND home_score IS NOT NULL", [season],
    ).fetchone()[0]
    totals = cur.execute(
        "SELECT sum(wins), sum(losses), sum(ties), sum(games) FROM team_standings "
        "WHERE season = ?", [season],
    ).fetchone()
    assert sum(totals[:3]) == 2 * played
    assert totals[3] == 2 * played


@pytest.mark.parametrize("season", [2001, 2024])
def test_points_for_and_points_against_balance(built_loader, season):
    etl.build(built_loader)
    scored, allowed = built_loader.cursor().execute(
        "SELECT sum(points_for), sum(points_against) FROM team_standings "
        "WHERE season = ?", [season],
    ).fetchone()
    assert scored == allowed


def test_unplayed_games_never_contribute(built_loader):
    """The fixture's 2024 week four has no scores, and 2026 has no scores at all."""
    etl.build(built_loader)
    cur = built_loader.cursor()
    scheduled = cur.execute(
        "SELECT count(*) FROM games WHERE season = 2024 AND home_score IS NULL"
    ).fetchone()[0]
    assert scheduled > 0
    assert cur.execute(
        "SELECT max(games) FROM team_standings WHERE season = 2024"
    ).fetchone()[0] == 3

    cur.execute(
        "INSERT INTO games (game_id, season, game_type, week, home_team, away_team) "
        "VALUES ('2026_01_BUF_KC', 2026, 'REG', 1, 'KC', 'BUF')"
    )
    etl.build(built_loader)
    assert cur.execute(
        "SELECT count(*) FROM team_standings WHERE season = 2026"
    ).fetchone()[0] == 0


def test_playoff_result_reads_the_postseason_and_nothing_else(built_loader):
    etl.build(built_loader)
    rows = {
        row[0]: row for row in built_loader.cursor().execute(
            "SELECT team, made_playoffs, playoff_round, playoff_result, "
            "playoff_wins, playoff_losses FROM team_standings WHERE season = 2024"
        ).fetchall()
    }
    assert rows["KC"][1:] == (True, "SB", "Won Super Bowl", 1, 0)
    assert rows["BUF"][1:] == (True, "SB", "Lost Super Bowl", 0, 1)
    # A club with no postseason game did not make the playoffs, and says nothing
    # rather than "0-0" or "Missed playoffs".
    assert rows["DAL"][1:] == (False, None, None, 0, 0)


def test_an_unreadable_bracket_produces_no_seeds_rather_than_a_guess(built_loader):
    """The fixture has a Super Bowl and no rounds before it."""
    report = etl.build(built_loader)
    seeds = built_loader.cursor().execute(
        "SELECT count(playoff_seed) FROM team_standings"
    ).fetchone()[0]
    assert seeds == 0
    assert set(report.unseeded) == {2001, 2024}


def test_a_division_our_rules_cannot_split_says_so(built_loader):
    """Every 2001 fixture club goes 2-2, and the two AFC Central clubs split 2-2."""
    etl.build(built_loader)
    rows = {
        row[0]: row for row in built_loader.cursor().execute(
            "SELECT team, division_rank, tiebreak_note FROM team_standings "
            "WHERE season = 2001 AND division = 'Central'"
        ).fetchall()
    }
    assert rows["BAL"][1] == 1 and rows["CIN"][1] == 2
    assert rows["BAL"][2] == etl.UNBROKEN_NOTE
    assert rows["CIN"][2] == etl.UNBROKEN_NOTE


def test_head_to_head_breaks_a_tie_before_conference_record(built_loader):
    """2024's fixture clubs each play one opponent, so head-to-head decides."""
    etl.build(built_loader)
    rows = {
        row[0]: row for row in built_loader.cursor().execute(
            "SELECT team, division_rank, tiebreak_note FROM team_standings "
            "WHERE season = 2024 AND division = 'North'"
        ).fetchall()
    }
    # BAL beat CIN twice in three meetings, so it is not a tie at all.
    assert rows["BAL"][1] == 1
    assert rows["BAL"][2] is None


def test_the_build_is_deterministic(built_loader):
    etl.build(built_loader)
    first = built_loader.cursor().execute(
        f"SELECT * FROM {etl.TABLE} ORDER BY season, team"
    ).fetchall()
    etl.build(built_loader)
    second = built_loader.cursor().execute(
        f"SELECT * FROM {etl.TABLE} ORDER BY season, team"
    ).fetchall()
    assert first == second


def _neutral_site_season():
    """A six-club 2024 with one tie, one neutral site and two conferences.

    Kansas City goes W, W, L, W, T: a one-game tie streak on top of a two-game win
    streak, three division games, one non-conference game, and a neutral-site win
    that belongs to neither the home nor the away split.
    """
    return [
        _game("g1", 2024, "REG", 1, "KC", "DEN", 24, 10),
        _game("g2", 2024, "REG", 2, "LV", "KC", 20, 30),
        _game("g3", 2024, "REG", 3, "KC", "DAL", 14, 21),
        _game("g4", 2024, "REG", 4, "PHI", "KC", 17, 20, neutral=True),
        _game("g5", 2024, "REG", 5, "KC", "LAC", 3, 3),
        _game("g6", 2024, "REG", 6, "LV", "DEN", 24, 21),
    ]


def test_splits_streaks_and_neutral_sites_from_a_hand_built_season():
    games = _neutral_site_season()
    rows = {row["team"]: row for row in etl.season_rows(2024, games)}
    kc = rows["KC"]
    assert (kc["wins"], kc["losses"], kc["ties"]) == (3, 1, 1)
    assert (kc["points_for"], kc["points_against"]) == (91, 71)
    assert kc["streak_kind"] == "T" and kc["streak_length"] == 1
    assert kc["longest_win_streak"] == 2
    # The neutral-site win is in neither split, so the two do not add up to five —
    # and the missing game is counted rather than lost, so the row says why.
    assert (kc["home_wins"], kc["home_losses"], kc["home_ties"]) == (1, 1, 1)
    assert (kc["away_wins"], kc["away_losses"], kc["away_ties"]) == (1, 0, 0)
    assert (kc["neutral_wins"], kc["neutral_losses"], kc["neutral_ties"]) == (1, 0, 0)
    assert sum(
        kc[f"{split}_{outcome}"]
        for split in ("home", "away", "neutral")
        for outcome in ("wins", "losses", "ties")
    ) == kc["games"]
    # Philadelphia hosted on paper and lost at a neutral site; neither is a home loss.
    phi = rows["PHI"]
    assert (phi["home_wins"], phi["home_losses"], phi["home_ties"]) == (0, 0, 0)
    assert (phi["neutral_wins"], phi["neutral_losses"], phi["neutral_ties"]) == (0, 1, 0)
    assert (kc["division_wins"], kc["division_losses"], kc["division_ties"]) == (2, 0, 1)
    # Dallas and Philadelphia are NFC, so neither counts towards a conference record.
    assert (kc["conference_wins"], kc["conference_losses"], kc["conference_ties"]) == \
        (2, 0, 1)
    assert kc["made_playoffs"] is False and kc["playoff_result"] is None
    assert kc["season_completed"] is False


def test_a_season_with_no_played_games_produces_no_rows():
    assert etl.season_rows(2024, []) == []


# --- ratings -----------------------------------------------------------------


@pytest.mark.parametrize("season", [2001, 2024])
def test_srs_sums_to_about_zero_and_splits_into_offence_and_defence(built_loader, season):
    etl.build(built_loader)
    rows = built_loader.cursor().execute(
        "SELECT srs, osrs, dsrs, sos, point_differential, games FROM team_standings "
        "WHERE season = ?", [season],
    ).fetchall()
    assert rows
    assert sum(row[0] for row in rows) == pytest.approx(0.0, abs=1e-9)
    for srs, osrs, dsrs, sos, differential, games in rows:
        assert osrs + dsrs == pytest.approx(srs, abs=1e-9)
        assert sos + differential / games == pytest.approx(srs, abs=1e-9)


def test_the_rating_solve_converges_quickly_and_repeatably():
    # A three-club round robin with a clear ordering: A beats B, B beats C, A beats C.
    schedules = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    points_for = {"A": 50, "B": 40, "C": 20}
    points_against = {"A": 20, "B": 40, "C": 50}
    first = etl.solve_ratings(schedules, points_for, points_against)
    second = etl.solve_ratings(schedules, points_for, points_against)
    assert first.converged and first.iterations < 50
    assert first.srs == second.srs
    assert first.srs["A"] > first.srs["B"] > first.srs["C"]
    assert sum(first.srs.values()) == pytest.approx(0.0, abs=1e-12)


def test_strength_of_schedule_is_the_difference_between_srs_and_margin():
    schedules = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    points_for = {"A": 50, "B": 40, "C": 20}
    points_against = {"A": 20, "B": 40, "C": 50}
    solved = etl.solve_ratings(schedules, points_for, points_against)
    for team in schedules:
        assert solved.sos[team] == pytest.approx(solved.srs[team] - solved.mov[team])


def test_every_number_we_compute_carries_its_formula():
    computed = ("srs", "osrs", "dsrs", "sos", "mov", "pythagorean_wins",
                "win_pct", "division_rank", "playoff_seed")
    assert set(computed) <= set(etl.FORMULAS)
    assert all(etl.FORMULAS[key].strip() for key in computed)
    assert set(computed) <= set(repo.formulas())


def test_pythagorean_wins_is_absent_rather_than_zero_without_scoring():
    assert etl.pythagorean_wins(0, 0, 16) is None
    assert etl.pythagorean_wins(400, 300, 16) == pytest.approx(
        16 * 400 ** 2.37 / (400 ** 2.37 + 300 ** 2.37)
    )


# --- seeding, against real brackets ------------------------------------------


def test_2015_afc_seeds_are_fixed_by_the_bracket_alone():
    """Seeds 1 DEN, 2 NE, 3 CIN, 4 HOU, 5 KC, 6 PIT, recovered with no record at all.

    Both wild-card hosts lost, which is what makes this bracket readable: the two
    clubs on a bye faced qualifiers of different seeds and then met each other, and
    no other seeding of these six clubs explains all five games.
    """
    games = [
        _game("2015_18_KC_HOU", 2015, "WC", 18, "HOU", "KC", 0, 30),
        _game("2015_18_PIT_CIN", 2015, "WC", 18, "CIN", "PIT", 16, 18),
        _game("2015_19_PIT_DEN", 2015, "DIV", 19, "DEN", "PIT", 23, 16),
        _game("2015_19_KC_NE", 2015, "DIV", 19, "NE", "KC", 27, 20),
        _game("2015_20_NE_DEN", 2015, "CON", 20, "DEN", "NE", 20, 18),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    seeds, basis, unsettled = etl.derive_seeds(field_teams, games, 6)
    assert seeds == {"DEN": 1, "NE": 2, "CIN": 3, "HOU": 4, "KC": 5, "PIT": 6}
    assert basis == etl.SEED_BASIS_RESULTS
    assert unsettled == set()


def test_2004_afc_bracket_fixes_the_byes_and_leaves_the_hosts_to_record():
    """Seeds 1 PIT, 2 NE, 3 IND, 4 SD, 5 NYJ, 6 DEN.

    Nothing in this bracket separates the third seed from the fourth: Indianapolis
    and San Diego never met, and swapping them — which swaps their wild-card
    opponents with them — explains every game just as well. Pittsburgh and New
    England are pinned regardless, because each played a qualifier the other did not.
    """
    games = [
        _game("2004_18_NYJ_SD", 2004, "WC", 18, "LAC", "NYJ", 17, 20),
        _game("2004_18_DEN_IND", 2004, "WC", 18, "IND", "DEN", 49, 24),
        _game("2004_19_NYJ_PIT", 2004, "DIV", 19, "PIT", "NYJ", 20, 17),
        _game("2004_19_IND_NE", 2004, "DIV", 19, "NE", "IND", 20, 3),
        _game("2004_20_NE_PIT", 2004, "CON", 20, "PIT", "NE", 27, 41),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    # 15-1 PIT, 14-2 NE, then the two 12-4 division winners, IND ahead of SD.
    league_order = ["PIT", "NE", "IND", "LAC", "NYJ", "DEN"]
    seeds, basis, unsettled = etl.derive_seeds(
        field_teams, games, 6, order_key=league_order.index
    )
    assert seeds == {"PIT": 1, "NE": 2, "IND": 3, "LAC": 4, "NYJ": 5, "DEN": 6}
    assert basis == etl.SEED_BASIS_RESULTS_AND_RECORD
    assert unsettled == {"IND", "LAC", "NYJ", "DEN"}


def test_2001_nfc_seeds_need_record_and_admit_it():
    """The bracket allows two seedings; only the regular season separates them.

    St. Louis and Chicago never met in the postseason, so nothing in the bracket
    says which of them was the top seed — swapping 1 with 2 and 3 with 4 explains
    every game equally well. The right answer is to use record and to mark the rows.
    """
    games = [
        _game("2001_18_TB_PHI", 2001, "WC", 18, "PHI", "TB", 31, 9),
        _game("2001_18_SF_GB", 2001, "WC", 18, "GB", "SF", 25, 15),
        _game("2001_19_GB_STL", 2001, "DIV", 19, "LA", "GB", 45, 17),
        _game("2001_19_PHI_CHI", 2001, "DIV", 19, "CHI", "PHI", 19, 33),
        _game("2001_20_PHI_STL", 2001, "CON", 20, "LA", "PHI", 29, 24),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    # Division winners first, then win percentage: 14-2 LA, 13-3 CHI, 11-5 PHI,
    # then the wild cards 12-4 GB, 12-4 SF, 9-7 TB.
    league_order = ["LA", "CHI", "PHI", "GB", "SF", "TB"]
    seeds, basis, unsettled = etl.derive_seeds(
        field_teams, games, 6, order_key=league_order.index
    )
    assert seeds == {"LA": 1, "CHI": 2, "PHI": 3, "GB": 4, "SF": 5, "TB": 6}
    assert basis == etl.SEED_BASIS_RESULTS_AND_RECORD
    assert unsettled == set(field_teams)


def test_a_partial_bracket_is_not_a_seeding():
    games = [_game("2024_18_A_B", 2024, "WC", 18, "KC", "BUF", 27, 20)]
    assert etl.derive_seeds(["KC", "BUF"], games, 7) is None
    assert etl.candidate_seedings(["KC", "BUF"], games, 7) == []


# --- division titles the bracket already settled -----------------------------


def test_the_2015_afc_bracket_names_its_four_division_winners():
    """Denver, New England, Cincinnati and Houston, from the bracket alone.

    Those are the four clubs that actually won the 2015 AFC divisions — West, East,
    North and South — and the four top seeds are exactly them. Kansas City and
    Pittsburgh, the wild cards, are not among them however well they played.
    """
    games = [
        _game("2015_18_KC_HOU", 2015, "WC", 18, "HOU", "KC", 0, 30),
        _game("2015_18_PIT_CIN", 2015, "WC", 18, "CIN", "PIT", 16, 18),
        _game("2015_19_PIT_DEN", 2015, "DIV", 19, "DEN", "PIT", 23, 16),
        _game("2015_19_KC_NE", 2015, "DIV", 19, "NE", "KC", 27, 20),
        _game("2015_20_NE_DEN", 2015, "CON", 20, "DEN", "NE", 20, 18),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    assert etl.division_titles_in_bracket(field_teams, games, 6, 4) == {
        "DEN", "NE", "CIN", "HOU"
    }


def test_the_2004_afc_bracket_names_the_winners_it_cannot_order():
    """It cannot say whether Indianapolis or San Diego was the third seed.

    It can still say both won divisions — the two of them are seeds 3 and 4 either
    way, and in a four-division, six-seed conference the top four seeds are the
    division winners. A club being unseparable from another is not a reason to
    withhold a fact both orderings agree on.
    """
    games = [
        _game("2004_18_NYJ_SD", 2004, "WC", 18, "LAC", "NYJ", 17, 20),
        _game("2004_18_DEN_IND", 2004, "WC", 18, "IND", "DEN", 49, 24),
        _game("2004_19_NYJ_PIT", 2004, "DIV", 19, "PIT", "NYJ", 20, 17),
        _game("2004_19_IND_NE", 2004, "DIV", 19, "NE", "IND", 20, 3),
        _game("2004_20_NE_PIT", 2004, "CON", 20, "PIT", "NE", 27, 41),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    assert etl.division_titles_in_bracket(field_teams, games, 6, 4) == {
        "PIT", "NE", "IND", "LAC"
    }


def test_the_2001_nfc_bracket_cannot_name_its_division_winners():
    """Three divisions and six seeds put a division winner on the same line as a
    wild card: Philadelphia was seed 3 and Green Bay seed 4, and the bracket allows
    the reverse. So this returns nothing and the ladder is left to decide.
    """
    games = [
        _game("2001_18_TB_PHI", 2001, "WC", 18, "PHI", "TB", 31, 9),
        _game("2001_18_SF_GB", 2001, "WC", 18, "GB", "SF", 25, 15),
        _game("2001_19_GB_STL", 2001, "DIV", 19, "LA", "GB", 45, 17),
        _game("2001_19_PHI_CHI", 2001, "DIV", 19, "CHI", "PHI", 19, 33),
        _game("2001_20_PHI_STL", 2001, "CON", 20, "LA", "PHI", 29, 24),
    ]
    field_teams = sorted({g_.home for g_ in games} | {g_.away for g_ in games})
    assert etl.division_titles_in_bracket(field_teams, games, 6, 3) is None


def _split_division_season(*, postseason: bool):
    """A 2024 AFC where Baltimore and Cincinnati are identical on every rule we have.

    They split their two meetings, so head-to-head is level; they are the only two
    clubs of their division here, so their division records are level; every game in
    the season is a conference game, so their conference records are level; and they
    beat and lost to the same four other clubs, so their common-games records are
    level too. Our ladder runs out and falls back to alphabetical order, which puts
    Baltimore first.

    The bracket says otherwise: Cincinnati is the second seed and Baltimore the
    fifth, so Cincinnati won the division and Baltimore was a wild card. The bracket
    is what happened.
    """
    games = [
        _game("2024_01_CIN_BAL", 2024, "REG", 1, "BAL", "CIN", 24, 20),
        _game("2024_02_BAL_CIN", 2024, "REG", 2, "CIN", "BAL", 27, 17),
        _game("2024_03_MIA_BAL", 2024, "REG", 3, "BAL", "MIA", 30, 13),
        _game("2024_04_MIA_CIN", 2024, "REG", 4, "CIN", "MIA", 26, 10),
        _game("2024_05_BAL_BUF", 2024, "REG", 5, "BUF", "BAL", 28, 21),
        _game("2024_06_CIN_BUF", 2024, "REG", 6, "BUF", "CIN", 24, 14),
        _game("2024_07_IND_BAL", 2024, "REG", 7, "BAL", "IND", 20, 16),
        _game("2024_08_IND_CIN", 2024, "REG", 8, "CIN", "IND", 23, 17),
        _game("2024_09_BAL_KC", 2024, "REG", 9, "KC", "BAL", 31, 24),
        _game("2024_10_CIN_KC", 2024, "REG", 10, "KC", "CIN", 27, 20),
        _game("2024_11_MIA_BUF", 2024, "REG", 11, "BUF", "MIA", 31, 10),
        _game("2024_12_BUF_MIA", 2024, "REG", 12, "MIA", "BUF", 13, 31),
        _game("2024_13_IND_HOU", 2024, "REG", 13, "HOU", "IND", 24, 10),
        _game("2024_14_HOU_IND", 2024, "REG", 14, "IND", "HOU", 17, 27),
        _game("2024_15_LV_KC", 2024, "REG", 15, "KC", "LV", 30, 13),
        _game("2024_16_KC_LV", 2024, "REG", 16, "LV", "KC", 14, 24),
        _game("2024_17_LV_MIA", 2024, "REG", 17, "MIA", "LV", 27, 20),
        _game("2024_18_LV_IND", 2024, "REG", 18, "IND", "LV", 23, 20),
    ]
    if postseason:
        games += [
            # Seeds 1 KC, 2 CIN, 3 BUF, 4 HOU, 5 BAL, 6 MIA, 7 IND.
            _game("2024_19_IND_CIN", 2024, "WC", 19, "CIN", "IND", 27, 10),
            _game("2024_19_MIA_BUF", 2024, "WC", 19, "BUF", "MIA", 30, 20),
            _game("2024_19_BAL_HOU", 2024, "WC", 19, "HOU", "BAL", 23, 20),
            _game("2024_20_HOU_KC", 2024, "DIV", 20, "KC", "HOU", 26, 13),
            _game("2024_20_BUF_CIN", 2024, "DIV", 20, "CIN", "BUF", 24, 21),
            _game("2024_21_CIN_KC", 2024, "CON", 21, "KC", "CIN", 20, 17),
            _game("2024_22_PHI_KC", 2024, "SB", 22, "KC", "PHI", 31, 24, neutral=True),
        ]
    return games


def test_a_completed_bracket_overrules_the_ladder_on_the_division_title():
    rows = {row["team"]: row for row in
            etl.season_rows(2024, _split_division_season(postseason=True))}
    assert rows["BAL"]["wins"] == rows["CIN"]["wins"] == 3
    assert rows["CIN"]["won_division"] is True
    assert rows["CIN"]["division_rank"] == 1
    assert rows["CIN"]["division_title_basis"] == etl.TITLE_BASIS_BRACKET
    assert rows["BAL"]["won_division"] is False
    assert rows["BAL"]["division_rank"] == 2
    # No tiebreaker ran, so no tiebreaker is claimed. The old code stamped the
    # "our rules ran out" marker on both clubs and made Baltimore the champion.
    assert rows["BAL"]["tiebreak_note"] is None
    assert rows["BAL"]["tiebreak_ladder"] is None
    assert rows["CIN"]["playoff_seed"] == 2 and rows["BAL"]["playoff_seed"] == 5
    assert rows["CIN"]["seed_basis"] == etl.SEED_BASIS_RESULTS
    # One title per division, still.
    assert sum(1 for row in rows.values() if row["won_division"]) == 4


def test_without_a_bracket_the_ladder_decides_and_says_it_could_not():
    """The same season with the postseason not yet played."""
    rows = {row["team"]: row for row in
            etl.season_rows(2024, _split_division_season(postseason=False))}
    assert rows["BAL"]["won_division"] is True
    assert rows["BAL"]["division_title_basis"] == etl.TITLE_BASIS_LADDER
    assert rows["BAL"]["tiebreak_note"] == etl.UNBROKEN_NOTE
    assert rows["BAL"]["tiebreak_ladder"] == etl.LADDER_DIVISION
    assert rows["CIN"]["won_division"] is False
    assert all(row["projected"] for row in rows.values() if row["playoff_seed"])


def test_two_unbeaten_division_winners_are_separated_by_strength_of_victory():
    """Buffalo and Kansas City are both 4-0 in the same season as above.

    They never met, every game either played was a conference game so their
    conference records are level too, and they share no common opponents. The
    division ladder has nothing left to say at that point; the conference ladder
    still does, and what it says is strength of victory — which Buffalo wins,
    because the clubs it beat won more than the clubs Kansas City beat.
    """
    rows = {row["team"]: row for row in
            etl.season_rows(2024, _split_division_season(postseason=False))}
    assert (rows["BUF"]["playoff_seed"], rows["KC"]["playoff_seed"]) == (1, 2)
    for code in ("BUF", "KC"):
        assert rows[code]["tiebreak_note"] == "Strength of victory"
        assert rows[code]["tiebreak_ladder"] == etl.LADDER_WILD_CARD
    # Which is a rule the division ladder does not have, and must not acquire.
    assert "Strength of victory" not in etl.DIVISION_TIEBREAK_RULES


def _standing(code, *, season=2024, record, conference_record=None, versus=None,
              division_record=None):
    """One club's season as the tiebreakers see it, without a schedule behind it."""
    conference, division = alignment.division_of(code, season)
    row = etl.TeamSeason(season=season, team=code, conference=conference,
                         division=division)
    row.overall = etl.Record(*record)
    row.conference_record = etl.Record(*(conference_record or record))
    row.division_record = etl.Record(*(division_record or (0, 0, 0)))
    row.versus = {opponent: etl.Record(*rec) for opponent, rec in (versus or {}).items()}
    return row


def test_the_wild_card_ladder_admits_one_club_per_division_before_anything_else():
    """Cincinnati has the best conference record of the three and still finishes last.

    All three are 4-4. A straight conference tiebreak would put Cincinnati first,
    but Baltimore swept it, so the division ladder places Baltimore above it and the
    wild-card procedure begins by admitting only the highest-placed club in each
    division. Houston takes the first slot from the two clubs actually eligible.
    """
    teams = {
        "BAL": _standing("BAL", record=(4, 4, 0), conference_record=(2, 4, 0),
                         versus={"CIN": (2, 0, 0)}, division_record=(2, 0, 0)),
        "CIN": _standing("CIN", record=(4, 4, 0), conference_record=(4, 2, 0),
                         versus={"BAL": (0, 2, 0)}, division_record=(0, 2, 0)),
        "HOU": _standing("HOU", record=(4, 4, 0), conference_record=(3, 3, 0)),
    }
    order = etl.rank_group(sorted(teams), teams, ladder=etl.LADDER_WILD_CARD)
    assert [placement.team for placement in order] == ["HOU", "BAL", "CIN"]
    # Both facts, in order: who was eligible, and what then separated them.
    assert order[0].note == (
        "Only the highest-placed club in each division is eligible, then "
        "conference record"
    )
    assert order[1].note == "Only the highest-placed club in each division is eligible"
    assert all(placement.ladder == etl.LADDER_WILD_CARD for placement in order[:2])
    # The division ladder, which has no such step, would have ordered them by that
    # conference record and let Cincinnati past its own division rival.
    straight = etl.rank_group(sorted(teams), teams)
    assert [placement.team for placement in straight][0] == "CIN"


# --- a whole league ----------------------------------------------------------


@pytest.mark.parametrize(
    "season,divisions,teams", [(2001, 6, 31), (2024, 8, 32)]
)
def test_a_full_season_has_the_divisions_and_clubs_of_its_era(
    built_loader, season, divisions, teams
):
    _built(built_loader, _full_league(season))
    rows = _table(built_loader, season)
    assert len(rows) == teams
    assert len({(row[1], row[2]) for row in rows.values()}) == divisions
    grouped = repo.season_standings(season, loader=built_loader)
    assert len(grouped["groups"]) == divisions
    assert sum(len(group["teams"]) for group in grouped["groups"]) == teams


@pytest.mark.parametrize("season", [2001, 2024])
def test_a_full_season_balances_and_its_ratings_sum_to_zero(built_loader, season):
    report = _built(built_loader, _full_league(season))
    cur = built_loader.cursor()
    played = cur.execute(
        "SELECT count(*) FROM games WHERE season = ? AND game_type = 'REG'", [season]
    ).fetchone()[0]
    assert report.iterations[season] < 50
    assert report.unconverged == ()
    assert report.unseeded == {}
    wins, losses, ties, scored, allowed, srs = cur.execute(
        "SELECT sum(wins), sum(losses), sum(ties), sum(points_for), "
        "sum(points_against), sum(srs) FROM team_standings WHERE season = ?", [season]
    ).fetchone()
    assert wins + losses + ties == 2 * played
    assert scored == allowed
    assert srs == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("season", [2001, 2024])
def test_a_completed_season_is_seeded_from_its_bracket(built_loader, season):
    _built(built_loader, _full_league(season))
    rows = _table(built_loader, season)
    expected = _intended_seeds(season)
    for conference, field_teams in expected.items():
        for index, team in enumerate(field_teams, start=1):
            assert rows[team][6] == index, (conference, team)
            assert rows[team][8] == etl.SEED_BASIS_RESULTS
            assert rows[team][7] is False
        seeded = [t for t, row in rows.items()
                  if row[1] == conference and row[6] is not None]
        assert len(seeded) == alignment.playoff_seeds(season)
    # A division winner is a division winner in every era, and there is one per
    # division — six in 2001, eight in 2024.
    assert sum(1 for row in rows.values() if row[9]) == len(
        alignment.divisions_in_season(season)
    )


@pytest.mark.parametrize("season", [2001, 2024])
def test_a_season_still_being_played_is_seeded_only_as_a_projection(built_loader, season):
    _built(built_loader, _full_league(season, postseason=False))
    rows = _table(built_loader, season)
    seeded = [row for row in rows.values() if row[6] is not None]
    assert len(seeded) == 2 * alignment.playoff_seeds(season)
    assert all(row[7] is True for row in seeded)
    assert all(row[8] == etl.SEED_BASIS_PROJECTED for row in seeded)
    payload = repo.season_standings(season, grouping="conference", loader=built_loader)
    assert payload["projected"] is True
    assert payload["season_completed"] is False
    assert "still being played" in payload["note"]
    # The projection puts every division winner above every wild card, which is the
    # one part of seeding that is not a matter of record.
    for group in payload["groups"]:
        winners = [team["seed"] for team in group["teams"] if team["won_division"]]
        wildcards = [
            team["seed"] for team in group["teams"]
            if team["seed"] is not None and not team["won_division"]
        ]
        assert max(winners) < min(wildcards)


# --- the read side -----------------------------------------------------------


def test_season_standings_groups_three_ways(built_loader):
    etl.build(built_loader)
    by_division = repo.season_standings(2024, loader=built_loader)
    by_conference = repo.season_standings(2024, grouping="conference", loader=built_loader)
    league = repo.season_standings(2024, grouping="league", loader=built_loader)
    assert [group["label"] for group in by_conference["groups"]] == ["AFC", "NFC"]
    assert len(league["groups"]) == 1
    assert {group["conference"] for group in by_division["groups"]} == {"AFC", "NFC"}
    ladders = by_division["tiebreak_rules_implemented"]
    assert ladders["division"][0] == ladders["wild_card"][0] == "Win percentage"
    # The two ladders diverge immediately after that, which is the point of having
    # two of them: a division tie asks about the division, a wild-card tie does not.
    assert ladders["division"] != ladders["wild_card"]
    assert "Strength of victory" in ladders["wild_card"]
    assert "Strength of victory" not in ladders["division"]
    with pytest.raises(ValueError):
        repo.season_standings(2024, grouping="alphabetical", loader=built_loader)


def test_read_side_computes_rates_rather_than_reading_them(built_loader):
    etl.build(built_loader)
    stored = {row[0] for row in built_loader.cursor().execute(
        f"DESCRIBE {etl.TABLE}").fetchall()}
    # Nothing that is a rate is stored; the read side divides.
    assert not {"win_pct", "pct", "mov", "srs_rank"} & stored
    row = repo.team_season_record("KC", 2024, loader=built_loader)
    assert row["pct"] == pytest.approx((row["w"] + 0.5 * row["t"]) / row["games"])
    assert row["mov"] == pytest.approx(row["diff"] / row["games"])
    assert row["home"].count("-") == 2
    assert row["ranks"]["srs"] >= 1
    assert "srs" in row["formulas"]


def test_the_read_side_says_why_home_and_away_do_not_add_up(built_loader):
    _built(built_loader, [_db_row(game) for game in _neutral_site_season()])
    row = repo.team_season_record("KC", 2024, loader=built_loader)
    assert row["neutral"] == "1-0-0"
    assert row["neutral_games"] == 1
    assert row["home"] == "1-1-1" and row["away"] == "1-0-0"
    assert "neutral site" in row["neutral_note"]
    # A club that played no neutral-site game says nothing, rather than "0-0-0 at a
    # neutral site", which would be a note about nothing on 31 rows out of 32.
    assert repo.team_season_record("LAC", 2024, loader=built_loader)["neutral_note"] is None
    payload = repo.season_standings(2024, loader=built_loader)
    # One game, not two, however many rows it appears on.
    assert "1 game was played at a neutral site" in payload["note"]


def test_the_read_side_names_the_ladder_that_produced_each_note(built_loader):
    rows = [_db_row(game) for game in _split_division_season(postseason=False)]
    _built(built_loader, rows)
    baltimore = repo.team_season_record("BAL", 2024, loader=built_loader)
    buffalo = repo.team_season_record("BUF", 2024, loader=built_loader)
    assert baltimore["tiebreak_ladder"] == "division"
    assert baltimore["tiebreak_rules_applied"] == list(etl.DIVISION_TIEBREAK_RULES)
    assert buffalo["tiebreak_ladder"] == "wild card"
    assert buffalo["tiebreak_rules_applied"] == list(etl.WILD_CARD_TIEBREAK_RULES)
    # Nothing separated Houston from anybody, so it claims no rule and no ladder.
    houston = repo.team_season_record("HOU", 2024, loader=built_loader)
    assert houston["tiebreak_note"] is None
    assert houston["tiebreak_ladder"] is None
    assert houston["tiebreak_rules_applied"] is None


def test_a_historical_code_and_the_current_one_are_the_same_franchise(built_loader):
    etl.build(built_loader)
    # The 2001 Rams played as STL; every table in this application keys them on LA.
    assert repo.team_season_record("STL", 2001, loader=built_loader) == \
        repo.team_season_record("LA", 2001, loader=built_loader)
    history = repo.franchise_history("STL", loader=built_loader)
    assert history["team"] == "LA"
    assert [row["season"] for row in history["seasons"]] == [2024, 2001]
    assert history["seasons"][-1]["code_in_season"] == "STL"
    assert history["seasons"][0]["code_in_season"] == "LA"
    assert history["summary"]["seasons"] == 2


def test_franchise_history_totals_match_the_seasons_it_lists(built_loader):
    etl.build(built_loader)
    history = repo.franchise_history("KC", loader=built_loader)
    summary = history["summary"]
    assert summary["w"] == sum(row["w"] for row in history["seasons"])
    assert summary["games"] == sum(row["games"] for row in history["seasons"])
    assert summary["super_bowls"] == 2  # the fixture hands KC both Super Bowls
    assert summary["playoff_appearances"] == 2


def test_league_ratings_are_ordered_and_labelled(built_loader):
    etl.build(built_loader)
    payload = repo.league_ratings(2024, loader=built_loader)
    ratings = [team["srs"] for team in payload["teams"]]
    assert ratings == sorted(ratings, reverse=True)
    assert set(payload["computed_by_us"]) <= set(payload["formulas"])
    best = payload["teams"][0]
    assert best["ranks"]["srs"] == 1
    assert best["pythagorean_delta"] == pytest.approx(
        best["w"] + 0.5 * best["t"] - best["pythagorean_wins"]
    )


def test_reads_build_the_table_on_demand(built_loader):
    assert built_loader.row_count(etl.TABLE) is None
    payload = repo.season_standings(2001, loader=built_loader)
    assert payload["groups"]
    assert built_loader.row_count(etl.TABLE) > 0


def test_a_season_with_no_games_answers_honestly(built_loader):
    etl.build(built_loader)
    payload = repo.season_standings(2026, loader=built_loader)
    assert payload["groups"] == []
    assert payload["note"] == "No games have been played in this season yet."
    assert repo.team_season_record("KC", 2026, loader=built_loader) is None
