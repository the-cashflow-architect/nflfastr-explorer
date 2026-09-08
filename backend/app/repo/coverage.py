"""The honesty payload: what data we actually have, not what we hoped for.

Everything here comes from two places only: `sources.SOURCES` (the declared
catalogue — one row per dataset, one place a season window or a projection is
written down) and the loader's load log (what has actually landed on disk, via
the public `Loader.load_records()` / `table_exists()` / `row_count()` /
`disk_usage_bytes()` surface — nothing here reaches into the loader's private
locks or attachment state). A dataset's *declared* window says what nflverse
publishes; its *actual* window, read from the load log, says what this
deployment has actually fetched. The two are allowed to differ — a fresh
deploy before the build job has run holds nothing yet — and this endpoint is
the one place that says so instead of papering over it.

No year belongs in this file as a literal. Every coverage boundary — the
stats floor, the air-yards charting boundary, Next Gen Stats, PFR advanced
stats, snap counts, injuries, the draft — is a named constant in `sources.py`
and is read from there, because the day this file and `sources.py` disagree is
the day the site starts lying about what it knows. `test_coverage.py` greps
this file for four-digit year literals to hold that line.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .. import sources
from ..deps import get_loader
from ..loader import LoadRecord, Loader

# What we do not have, and why. Mirrors SPEC.md section 7 ("What we are
# deliberately not building") so the reasoning behind a missing block lives in
# exactly one place a visitor can read, on /about/data, rather than being
# re-explained ad hoc on whichever page someone notices the gap first.
NOT_BUILDING: tuple[dict[str, str], ...] = (
    {
        "what": "Season-by-season Approximate Value, and any AV-based similarity or Hall-of-Fame monitor",
        "why": (
            "PFR's AV is a proprietary formula with no season-level figure in any "
            "nflverse file. We show draft_picks' career AV where it exists, labeled "
            "as PFR's career total for drafted players only, and ship our own, "
            "differently named similarity method instead of reimplementing it."
        ),
    },
    {
        "what": (
            "Season-by-season awards: MVP, OPOY, DPOY, Rookie of the Year, "
            "Coach of the Year, All-Pro teams and Pro Bowl rosters"
        ),
        "why": (
            "No verified source records which season an honor was earned — "
            "draft_picks carries only career counts — and hand-maintained award "
            "data would have to be kept current forever."
        ),
    },
    {
        "what": "Transaction logs, draft-day trade trackers, and pick-ownership boards",
        "why": (
            "No transaction dataset exists in the verified sources, and inferring "
            "a trade from a player changing teams between seasons is not a "
            "transaction log and would read as one."
        ),
    },
    {
        "what": "Official starters and inactives per game",
        "why": (
            "Nothing in the verified data marks who started. We ship a "
            "snap-share-based started proxy, labeled a proxy, on the game log "
            "only, and never present it as the official designation."
        ),
    },
    {
        "what": "Attendance, game duration, coin toss, and TV network",
        "why": (
            "Not present in the schedule file or any verified source, so these "
            "fields do not appear rather than showing blank cells."
        ),
    },
    {
        "what": "Seasons before our stat floor, and the phrase 'all-time' anywhere on the site",
        "why": (
            "Our play-level data starts at the floor recorded in the registry "
            "(the draft is the sole exception, reaching back further). Every "
            "leaderboard is labeled modern era rather than implying a century of "
            "coverage we do not have."
        ),
    },
    {
        "what": "A coaches hub with career records and coaching trees",
        "why": (
            "The schedule file carries only free-text head-coach names per game — "
            "no coach ids, no assistants, no tenure table, and name-variant "
            "fragility — so we surface head coach as a field and a small "
            "franchise-page table, and stop there."
        ),
    },
    {
        "what": "Officials analytics (crew penalty tendencies)",
        "why": (
            "The officials file gives assignments only; tendencies would need a "
            "heavy play-by-play aggregation for a block that would not change "
            "what a visitor does next."
        ),
    },
    {
        "what": "Contract and salary cap data",
        "why": (
            "The available contracts file is unverified for currency and "
            "completeness. Shipping unverified money figures on a reference site "
            "is a brand risk out of proportion to the feature."
        ),
    },
    {
        "what": "Depth charts",
        "why": (
            "The depth-chart file is larger than every other dataset we load "
            "combined, for a page whose job is already done by sorting the "
            "roster by snap share."
        ),
    },
    {
        "what": "Radar / 'pizza' charts",
        "why": (
            "Harder to read than a sorted percentile bar list and they degrade "
            "past two entities; the comparison tool ships bars and a table only."
        ),
    },
    {
        "what": "A conversational 'ask the data' natural-language query box",
        "why": (
            "It would add per-query cost and a hallucination surface to a site "
            "whose entire promise is accuracy. The Finder's auditable, "
            "permalinkable filter builder serves the same need honestly."
        ),
    },
    {
        "what": "Predictive game-outcome models, power ratings, and proprietary player grades",
        "why": (
            "We publish an EPA-and-schedule-adjusted rating with its formula "
            "stated, and nothing that claims to know the future or to grade a "
            "player's technique from data that does not contain it."
        ),
    },
    {
        "what": "Live in-progress game state",
        "why": (
            "nflverse releases are post-game; there is no real-time feed in the "
            "verified sources, so no live badge or ticking score appears "
            "anywhere."
        ),
    },
    {
        "what": "User accounts, server-side saved queries, and any ad or paywall surface",
        "why": (
            "Saved views live in the visitor's own browser and say so. No "
            "credentials are handled anywhere."
        ),
    },
    {
        "what": "The full multi-season play-by-play table held resident at once",
        "why": (
            "Unprojected and un-windowed it would force every query on a small "
            "instance to spill to disk. Recent seasons stay resident and older "
            "ones materialise on demand instead."
        ),
    },
)

#: Named coverage windows other surfaces cite by name rather than repeating a
#: year. Each entry's `first_season` is a live attribute read off `sources`,
#: never a literal — see the module docstring.
_COVERAGE_WINDOWS: tuple[tuple[str, str, str], ...] = (
    (
        "stats",
        "FIRST_SEASON",
        "Expected points, win probability, success rate and drive data run from here.",
    ),
    (
        "charting",
        "CHARTING_FIRST_SEASON",
        "Air yards, yards after catch and CPOE were not charted before this season "
        "and are NULL, not zero, in earlier ones.",
    ),
    (
        "next_gen_stats",
        "NGS_FIRST_SEASON",
        "Player-tracking-derived metrics begin here.",
    ),
    (
        "pfr_advanced",
        "ADVSTATS_FIRST_SEASON",
        "Pro-Football-Reference charting (pressures, drops, on-target throws), "
        "republished by nflverse, begins here.",
    ),
    (
        "snap_counts",
        "SNAP_COUNTS_FIRST_SEASON",
        "Offensive, defensive and special-teams snap shares begin here.",
    ),
    (
        "injuries",
        "INJURIES_FIRST_SEASON",
        "Weekly practice and game-status reports begin here.",
    ),
    (
        "draft",
        "DRAFT_FIRST_SEASON",
        "The only block on the site that reaches before the stats floor.",
    ),
)


def _coverage_windows() -> dict[str, dict[str, Any]]:
    return {
        key: {"first_season": getattr(sources, attr), "note": note}
        for key, attr, note in _COVERAGE_WINDOWS
    }


def _actual_window(
    loader: Loader, source: sources.Source, records: list[LoadRecord]
) -> tuple[int | None, int | None]:
    """The season range this deployment has actually fetched for one source.

    Season-grained sources answer straight from the load log, which is keyed
    by season already. `single`-grain sources (players, draft_picks, the NGS
    and PFR-advanced files, ...) are loaded in one shot with no per-season
    entry in the log, so their internal `season` column — where they have
    one — is read back directly; a source with no such column (team
    identity, officials assignments) has no season window to report, and
    reports none rather than guessing the declared one.
    """
    if source.grain == "season":
        seasons = [r.season for r in records if r.season is not None]
        return (min(seasons), max(seasons)) if seasons else (None, None)
    if not records or not loader.table_exists(source.table):
        return (None, None)
    cur = loader.cursor()
    columns = {row[0] for row in cur.execute(f"DESCRIBE {source.table}").fetchall()}
    if "season" not in columns:
        return (None, None)
    row = cur.execute(f"SELECT min(season), max(season) FROM {source.table}").fetchone()
    return (row[0], row[1]) if row else (None, None)


def _dataset_entry(
    loader: Loader, source: sources.Source, records: list[LoadRecord]
) -> dict[str, Any]:
    season_min, season_max = _actual_window(loader, source, records)
    if records:
        row_count = sum(r.row_count for r in records)
        loaded_at = max(r.loaded_at for r in records)
        status = "loaded"
    else:
        # The public Loader surface (load_records / table_exists / row_count)
        # has no notion of "a download is in flight right now" — that lives in
        # locks private to the loader — so a dataset with no load record is
        # reported as not yet available rather than guessing at a 'loading'
        # state we cannot actually verify. A false "it's loading" is worse
        # than an honest "we don't have it yet".
        row_count = None
        loaded_at = None
        status = "unavailable"
    return {
        "id": source.id,
        "name": source.name,
        "label": source.name,
        "description": source.description,
        "source_url": source.url,
        "season_min": season_min,
        "season_max": season_max,
        "declared_first_season": source.first_season,
        "declared_last_season": source.last_season,
        "row_count": row_count,
        "loaded_at": loaded_at.isoformat() if loaded_at else None,
        "coverage_note": source.coverage_note or None,
        "status": status,
    }


def _latest_completed_season(loader: Loader) -> int | None:
    """The newest season with at least one played game, straight from `games`.

    Returns None rather than a guess when the schedule has not loaded yet —
    the same honesty rule as everything else on this page.
    """
    if not loader.table_exists("games"):
        return None
    cur = loader.cursor()
    row = cur.execute(
        "SELECT max(season) FROM games WHERE home_score IS NOT NULL"
    ).fetchone()
    return row[0] if row else None


def build_coverage(loader: Any = None) -> dict[str, Any]:
    """The full `/api/coverage` payload.

    Built fresh on every call rather than cached: it is read rarely (a footer
    line, an era badge, one reference page) and it exists specifically to
    never go stale relative to what the loader actually holds.
    """
    loader = loader or get_loader()
    records_by_source: dict[str, list[LoadRecord]] = {}
    for record in loader.load_records():
        records_by_source.setdefault(record.source_id, []).append(record)

    datasets = [
        _dataset_entry(loader, source, records_by_source.get(source.id, []))
        for source in sources.SOURCES
    ]

    return {
        "datasets": datasets,
        "coverage_windows": _coverage_windows(),
        "not_building": [dict(item) for item in NOT_BUILDING],
        "disk_usage_bytes": loader.disk_usage_bytes(),
        "latest_completed_season": _latest_completed_season(loader),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
