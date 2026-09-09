from app.sources import BY_ID


def test_fixture_builds_a_real_database(built_loader):
    for sid in ("games", "teams_meta", "players", "player_week", "team_week", "pbp"):
        built_loader.ensure(sid)
    cur = built_loader.cursor()
    teams = sorted(r[0] for r in cur.execute(
        "SELECT DISTINCT home_team FROM games WHERE season=2001").fetchall())
    assert "LA" in teams and "STL" not in teams, teams
    assert cur.execute("SELECT count(*) FROM player_week WHERE team IS NULL").fetchone()[0] == 0
    assert cur.execute("SELECT count(air_yards) FROM pbp WHERE season=2001").fetchone()[0] == 0
    assert cur.execute("SELECT count(air_yards) FROM pbp WHERE season=2024").fetchone()[0] > 0
    assert built_loader.row_count(BY_ID["players"].table) == 6
