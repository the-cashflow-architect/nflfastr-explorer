"""Build a real DuckDB database from the test fixtures, with no network.

The route review (`frontend/npm run review`) is the gate that catches what the
static checks cannot, and it needs an API with data behind it. The real database
takes four minutes and ~200 MB of downloads, which is too much to ask of anyone
checking a frontend change.

This builds the same database the test suite builds — the production loader and
the production derived tables, over locally generated files shaped like the
nflverse originals — covering 2001 and 2024, one season either side of both the
2002 realignment and the 2006 air-yards charting boundary.

It is for local verification only. Nothing here should ever run in a deploy: the
numbers are generated, not real.

    python -m scripts.build_fixture_db /tmp/fixture.duckdb
    DUCKDB_PATH=/tmp/fixture.duckdb uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    target = Path(argv[1]).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    work = target.parent / f"{target.stem}-sources"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    os.environ["DATA_DIR"] = str(target.parent)
    os.environ["DUCKDB_PATH"] = str(target)

    import requests

    import conftest  # the test fixtures' own file generators
    from app import deps as deps_module
    from app import loader as loader_module
    from app import sources as sources_module
    from app.etl import derived
    # The same three imports app.build makes, for the same reason: they are what
    # registers the derived tables. Miss them and the build quietly produces
    # sources only, which is the failure that job exists to prevent.
    from app.etl import pbp_derive as _pbp_derive  # noqa: F401
    from app.etl import standings as _standings  # noqa: F401
    from app.repo import search as _search  # noqa: F401

    os.environ["LATEST_SEASON"] = str(max(conftest.FIXTURE_SEASONS))

    # Only the fixture seasons exist, so the loader must not ask for the others.
    sources_module.Source.seasons = lambda self, through: [  # type: ignore[method-assign]
        s for s in conftest.FIXTURE_SEASONS
        if s >= (self.first_season or 0) and s <= through
    ]

    counter = {"n": 0}

    def fake_download(self, url: str) -> str:
        try:
            path = conftest.fixture_file(str(work), url)
        except conftest.NotPublished:
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError(f"404 for {url}", response=response) from None
        counter["n"] += 1
        copy = work / f"copy{counter['n']}_{Path(path).name}"
        shutil.copyfile(path, copy)
        return str(copy)

    loader_module.Loader.download = fake_download  # type: ignore[method-assign]

    loader = loader_module.Loader(path=str(target), building=True)
    deps_module.use_loader(loader)

    through = max(conftest.FIXTURE_SEASONS)
    for source in sources_module.SOURCES:
        try:
            loader.ensure(source.id, through=through)
            print(f"  {source.id}")
        except Exception as exc:  # noqa: BLE001 — a missing fixture is not fatal here
            print(f"  {source.id}: skipped ({type(exc).__name__})")

    for name, outcome in derived.build_all(loader).items():
        print(f"  derived {name}: {outcome}")

    loader.close()
    deps_module.use_loader(None)
    print(f"\nFixture database at {target} ({target.stat().st_size / 1e6:.1f} MB)")
    print("Seasons:", ", ".join(str(s) for s in conftest.FIXTURE_SEASONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
