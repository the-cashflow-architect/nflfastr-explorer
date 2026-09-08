"""One-shot data build: `python -m app.build`.

Deliberately a job you run, not something a deploy triggers. A deploy that
downloads forty files takes minutes and fails on someone else's flaky CDN; a
build you run once writes a database file that every later start simply opens.

    python -m app.build                 # everything, resuming what is already current
    python -m app.build --only games players
    python -m app.build --through 2024  # stop at a season, for a smaller local copy
    python -m app.build --report        # what is loaded, how big, how fresh
"""

from __future__ import annotations

import argparse
import logging
import resource
import sys
import time

from . import sources
from .config import latest_season
from .etl import derived
from .loader import Loader

# Importing these registers their derived tables. Without the imports the
# registry is empty and the build silently produces sources only — which is
# exactly the failure mode this job exists to prevent.
from .etl import pbp_derive as _pbp_derive  # noqa: F401
from .etl import standings as _standings  # noqa: F401
from .repo import search as _search  # noqa: F401

logger = logging.getLogger("build")


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def report(loader: Loader) -> int:
    records = loader.load_records()
    by_source: dict[str, list] = {}
    for record in records:
        by_source.setdefault(record.source_id, []).append(record)

    print(f"{'source':22s} {'seasons':>18s} {'rows':>12s}  loaded")
    print("-" * 72)
    for source in sources.SOURCES:
        rows = by_source.get(source.id)
        if not rows:
            print(f"{source.id:22s} {'—':>18s} {'not loaded':>12s}")
            continue
        seasons = sorted(r.season for r in rows if r.season is not None)
        window = f"{seasons[0]}-{seasons[-1]}" if seasons else "all"
        total = sum(r.row_count or 0 for r in rows)
        newest = max(r.loaded_at for r in rows)
        print(f"{source.id:22s} {window:>18s} {total:>12,}  {newest:%Y-%m-%d %H:%M}")
    print("-" * 72)
    for entry in derived.all_derived():
        stamp = derived.built_at(loader, entry.name)
        state = "stale" if derived.is_stale(loader, entry) else "current"
        when = f"{stamp:%Y-%m-%d %H:%M}" if stamp else "never built"
        print(f"{entry.name:22s} {state:>18s} {'':>12s}  {when}")
    print("-" * 72)
    print(f"disk: {loader.disk_usage_bytes() / 1e6:.0f} MB")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.build", description=__doc__)
    parser.add_argument("--only", nargs="*", metavar="SOURCE", help="Build just these sources.")
    parser.add_argument("--through", type=int, default=None, metavar="SEASON",
                        help="Latest season to load (default: the current one).")
    parser.add_argument("--report", action="store_true", help="Show what is loaded and exit.")
    parser.add_argument(
        "--sources-only",
        action="store_true",
        help="Fetch the source files but skip the derived tables.",
    )
    parser.add_argument(
        "--derived-only",
        action="store_true",
        help="Rebuild the derived tables from sources already on disk.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    loader = Loader(building=True)
    if args.report:
        return report(loader)

    through = args.through or latest_season()
    wanted = args.only or [s.id for s in sources.SOURCES]
    unknown = [w for w in wanted if w not in sources.BY_ID]
    if unknown:
        parser.error(f"Unknown source(s): {', '.join(unknown)}")

    started = time.monotonic()
    failed: list[str] = []

    if not args.derived_only:
        for source_id in wanted:
            step = time.monotonic()
            try:
                loader.ensure(source_id, through=through)
            except Exception:
                logger.exception("Failed to build %s", source_id)
                failed.append(source_id)
            else:
                logger.info("%s ready in %.0fs", source_id, time.monotonic() - step)

    # Derived tables are not optional extras. Standings, search and every summary
    # that carries a season we do not keep plays for live here, so a deployment
    # that fetched sources and stopped has a working API over an empty product.
    if not args.sources_only:
        step = time.monotonic()
        outcomes = derived.build_all(loader)
        for name, outcome in outcomes.items():
            logger.info("derived %s: %s", name, outcome)
            if outcome == "failed":
                failed.append(name)
        logger.info("derived tables in %.0fs", time.monotonic() - step)

    logger.info(
        "Build finished in %.0fs — disk %.0f MB, peak memory %.0f MB",
        time.monotonic() - started,
        loader.disk_usage_bytes() / 1e6,
        _peak_rss_mb(),
    )
    if failed:
        logger.error("Incomplete: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
