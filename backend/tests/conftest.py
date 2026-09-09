from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Nothing in the app connects to a database at import time any more, but a test
# that forgets to point at a scratch path should still not write into the repo.
os.environ.setdefault(
    "DUCKDB_PATH", str(Path(tempfile.mkdtemp(prefix="nflfastr-test-")) / "import.duckdb")
)

from app import data_store as ds_module  # noqa: E402


# --- The new registry-driven stack -------------------------------------------
#
# `built_loader` gives a real Loader over a real DuckDB file, with every download
# resolved to a locally generated file shaped like the nflverse original. Only the
# network is faked: projection, team-code canonicalisation, the null-team filter,
# schema widening, per-season load tracking and the play-by-play attach/evict cycle
# all run for real, because those are where the bugs live.

import re  # noqa: E402
import shutil  # noqa: E402

import requests  # noqa: E402

import factories  # noqa: E402
from app import deps as deps_module  # noqa: E402
from app import loader as loader_module  # noqa: E402
from app import sources as sources_module  # noqa: E402

#: Seasons the fixture database covers: one before the 2002 realignment and the
#: 2006 air-yards charting boundary, one after both.
FIXTURE_SEASONS = (2001, 2024)


class NotPublished(Exception):
    """Stands in for a 404 on a file this fixture deliberately does not model."""


def fixture_file(directory: str, url: str) -> str:
    """Generate the local stand-in for whichever nflverse file was requested."""
    season_match = re.search(r"_(\d{4})\.parquet$", url)
    season = int(season_match.group(1)) if season_match else None
    name = url.rsplit("/", 1)[-1]
    target = os.path.join(directory, f"{season or 'all'}_{name}")

    if name == "games.csv":
        return factories.write_games_csv(target, seasons=FIXTURE_SEASONS)
    if name == "teams_colors_logos.csv":
        return factories.write_teams_meta(target)
    if name == "players.parquet":
        return factories.write_players(target)
    if "stats_player_week" in name:
        return factories.write_player_week(target, season)
    if "stats_player_reg" in name or "stats_player_post" in name:
        # The season files name the team column `recent_team` and carry no
        # `team` until the loader aliases one in — see `write_player_week`.
        return factories.write_player_week(target, season, team_column="recent_team")
    if "stats_team_week" in name or "stats_team_reg" in name:
        return factories.write_team_week(target, season)
    if "play_by_play" in name:
        return factories.write_pbp(target, season)
    raise NotPublished(url)


@pytest.fixture
def built_loader(tmp_path, monkeypatch):
    """A Loader over a small, real, locally built database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LATEST_SEASON", str(max(FIXTURE_SEASONS)))
    monkeypatch.setattr(
        sources_module.Source,
        "seasons",
        lambda self, through: [
            s for s in FIXTURE_SEASONS if s >= (self.first_season or 0) and s <= through
        ],
    )

    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    counter = {"n": 0}

    def fake_download(self, url: str) -> str:
        try:
            path = fixture_file(str(sources_dir), url)
        except NotPublished:
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError(f"404 for {url}", response=response) from None
        # Copy, because the loader unlinks whatever it downloaded.
        counter["n"] += 1
        copy = str(sources_dir / f"copy{counter['n']}_{os.path.basename(path)}")
        shutil.copyfile(path, copy)
        return copy

    monkeypatch.setattr(loader_module.Loader, "download", fake_download)

    loader = loader_module.Loader(
        path=str(tmp_path / "data" / "test.duckdb"), building=True
    )
    deps_module.use_loader(loader)
    yield loader
    deps_module.use_loader(None)
    loader.close()


@pytest.fixture
def store(built_loader):
    """The Finder's store, reading the tables `built_loader` just built.

    Nothing is stubbed: `DataStore` owns no loading code of its own, so this is
    the production object over a small real database.
    """
    return ds_module.DataStore()
