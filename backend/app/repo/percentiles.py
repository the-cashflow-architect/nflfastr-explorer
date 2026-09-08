"""Positional cohorts, and the percentile bars drawn against them.

A percentile is not a property of a player. It is a property of a player *and* a
cohort, and a bar drawn without saying who the peers were is decoration. So every
payload this module produces carries three things the caller cannot omit: the
cohort's position group, its size, and the qualification rule written out as a
sentence a reader can check.

Four rules shape the arithmetic.

**Rates are pooled, never averaged.** A metric is `SUM(numerator) / SUM(denominator)`
over the seasons in scope (SPEC 0.7). A stat that upstream already stores as a rate —
CPOE is the only one on this surface — is re-weighted by the volume it was computed
over before it is summed, because averaging two seasons' CPOE is averaging averages.

**A column that is not there is not a zero.** Every metric names candidate columns and
is dropped from the payload if none of them is present in the loaded table. A position
group whose metrics all drop out gets a note saying so, not a row of zeroes.

**Thresholds are measured where they can be.** "14 pass attempts per team game" is the
NFL's own qualifier for its passing leaders, and the team-games it multiplies by is
counted out of the schedule file rather than assumed to be sixteen or seventeen.

**Not qualifying is an answer.** A player below the cohort's volume bar still gets his
value back, with `in_cohort` false and no percentile, rather than being silently
ranked against peers he does not belong with.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from statistics import median as _median
from typing import Any, Iterable, Sequence

from .. import sources
from ..deps import get_loader

logger = logging.getLogger(__name__)

#: The season table every cohort is built from. Postseason volume never enters a
#: percentile: a cohort mixing eighteen-game seasons with four-game ones would rank
#: players on how far their team went.
SEASON_TABLE = "player_season_reg"

CAREER = "career"


# --- reading whatever actually loaded ----------------------------------------
#
# These three are the lower layer `repo/players.py` also reads through, which is
# why they live here rather than there: percentiles is the module with no
# dependency on the other.


def resolve_loader(loader: Any = None) -> Any:
    return loader if loader is not None else get_loader()


def ensure_source(loader: Any, source_id: str) -> bool:
    """Load one source if we can, and answer whether its table is actually there.

    A source can be missing for two entirely ordinary reasons: a season-grained
    file that upstream has not published yet (the loader swallows that 404), and a
    deployment whose build job has not reached this dataset. Neither is a server
    error, and neither may be reported as an empty result — the caller's job is to
    leave the block out of the payload and say why. Anything else raised while
    loading is logged and treated the same way, because a player page that fails
    whole because the combine file moved is worse than one missing its combine row.
    """
    table = sources.get(source_id).table
    try:
        loader.ensure(source_id)
    except Exception:  # noqa: BLE001 - see docstring: availability, not failure
        logger.warning("Source %s is unavailable; its blocks will be omitted", source_id, exc_info=True)
    return loader.table_exists(table)


def table_columns(loader: Any, table: str) -> frozenset[str]:
    if not loader.table_exists(table):
        return frozenset()
    cur = loader.cursor()
    return frozenset(row[0] for row in cur.execute(f"DESCRIBE {table}").fetchall())


def first_present(columns: Iterable[str], candidates: Sequence[str]) -> str | None:
    """The first candidate column that exists, or None.

    nflverse renames columns between releases (`interceptions` became
    `passing_interceptions`), and a stat line that hardcodes one spelling turns
    into a wall of nulls the day it changes. Naming the alternatives is cheaper
    than discovering it in production.
    """
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


# --- metrics ------------------------------------------------------------------


@dataclass(frozen=True)
class Metric:
    """One percentile bar: a pooled rate, its unit, and which way is better."""

    id: str
    label: str
    unit: str
    numerator: tuple[str, ...]
    denominator: tuple[str, ...]
    #: Set when `numerator` is a stored per-season rate. The rate is multiplied by
    #: this volume before summing, so a career figure is the volume-weighted one
    #: rather than the mean of the seasons.
    weight: tuple[str, ...] | None = None
    higher_is_better: bool = True
    #: Read off `sources`, never written as a year. Populates `coverage_note`.
    first_season: int | None = None
    note: str = ""


#: `games` is the denominator of every per-game metric. Named once so the
#: fallback below and the metrics agree about what a "game" is.
_GAMES = ("games",)

_PASS_ATTEMPTS = ("attempts", "passing_attempts", "pass_attempts")
_CARRIES = ("carries", "rushing_attempts", "rush_atts")

_QB_METRICS: tuple[Metric, ...] = (
    Metric("epa_per_attempt", "EPA per pass attempt", "epa", ("passing_epa",), _PASS_ATTEMPTS),
    Metric("yards_per_attempt", "Yards per pass attempt", "yards", ("passing_yards",), _PASS_ATTEMPTS),
    Metric("completion_pct", "Completion percentage", "percent", ("completions",), _PASS_ATTEMPTS),
    Metric("td_per_attempt", "Touchdown rate", "percent", ("passing_tds",), _PASS_ATTEMPTS),
    Metric(
        "interception_pct", "Interception rate", "percent",
        ("passing_interceptions", "interceptions"), _PASS_ATTEMPTS, higher_is_better=False,
    ),
    Metric(
        "cpoe", "Completion percentage over expected", "percent",
        ("passing_cpoe",), _PASS_ATTEMPTS, weight=_PASS_ATTEMPTS,
        first_season=sources.CHARTING_FIRST_SEASON,
        note="Volume-weighted across seasons, because a stored season rate cannot be averaged.",
    ),
    Metric("passing_yards_per_game", "Passing yards per game", "yards", ("passing_yards",), _GAMES),
)

_RB_METRICS: tuple[Metric, ...] = (
    Metric("yards_per_carry", "Yards per carry", "yards", ("rushing_yards",), _CARRIES),
    Metric("epa_per_carry", "EPA per carry", "epa", ("rushing_epa",), _CARRIES),
    Metric("rushing_yards_per_game", "Rushing yards per game", "yards", ("rushing_yards",), _GAMES),
    Metric("receiving_yards_per_game", "Receiving yards per game", "yards", ("receiving_yards",), _GAMES),
    Metric("catch_rate", "Catch rate", "percent", ("receptions",), ("targets",)),
)

_RECEIVER_METRICS: tuple[Metric, ...] = (
    Metric("yards_per_reception", "Yards per reception", "yards", ("receiving_yards",), ("receptions",)),
    Metric("yards_per_target", "Yards per target", "yards", ("receiving_yards",), ("targets",)),
    Metric("catch_rate", "Catch rate", "percent", ("receptions",), ("targets",)),
    Metric("epa_per_target", "EPA per target", "epa", ("receiving_epa",), ("targets",)),
    Metric(
        "air_yards_per_target", "Air yards per target", "yards",
        ("receiving_air_yards",), ("targets",),
        first_season=sources.CHARTING_FIRST_SEASON,
    ),
    Metric("receiving_yards_per_game", "Receiving yards per game", "yards", ("receiving_yards",), _GAMES),
)

_DEFENCE_METRICS: tuple[Metric, ...] = (
    Metric("tackles_per_game", "Tackles per game", "count", ("def_tackles_solo", "def_tackles"), _GAMES),
    Metric("sacks_per_game", "Sacks per game", "count", ("def_sacks",), _GAMES),
    Metric("interceptions_per_game", "Interceptions per game", "count", ("def_interceptions",), _GAMES),
    Metric(
        "passes_defended_per_game", "Passes defended per game", "count",
        ("def_pass_defended", "def_passes_defended"), _GAMES,
    ),
    Metric("tackles_for_loss_per_game", "Tackles for loss per game", "count", ("def_tackles_for_loss",), _GAMES),
)

#: Position groups as `players.position_group` spells them. A group with no entry
#: has no percentile strip rather than a borrowed one — a long snapper ranked on
#: receiving yards would be a fabricated comparison.
METRICS: dict[str, tuple[Metric, ...]] = {
    "QB": _QB_METRICS,
    "RB": _RB_METRICS,
    "WR": _RECEIVER_METRICS,
    "TE": _RECEIVER_METRICS,
    "DL": _DEFENCE_METRICS,
    "LB": _DEFENCE_METRICS,
    "DB": _DEFENCE_METRICS,
}


# --- qualification -------------------------------------------------------------


@dataclass(frozen=True)
class Qualification:
    """The volume bar a player clears to enter a cohort, and its provenance."""

    columns: tuple[str, ...]
    per_team_game: float
    #: What the volume is called in the sentence: "pass attempts", "receptions".
    noun: str
    #: Where the rate comes from. `ours` is flagged to the reader as our own rule.
    source: str


#: The three per-team-game rates are the NFL's own qualifiers for its season
#: leaders — the same ones SPEC section 3 quotes for the leaderboards ("14 pass
#: attempts per team game"). Keeping them here means the percentile cohort and the
#: leaderboard cannot drift apart into two different definitions of "qualified".
_NFL_QUALIFIERS: dict[str, Qualification] = {
    "QB": Qualification(_PASS_ATTEMPTS, 14.0, "pass attempts", "NFL"),
    "RB": Qualification(_CARRIES, 6.25, "rushing attempts", "NFL"),
    "WR": Qualification(("receptions",), 1.875, "receptions", "NFL"),
    "TE": Qualification(("receptions",), 1.875, "receptions", "NFL"),
}

#: The fallback, and the only qualifier for defensive and line play: the league
#: publishes no volume qualifier for them, and snap counts — the honest
#: denominator — only start in 2012, which would silently shrink every cohort
#: before then. Half the team's games is ours, and is labelled as ours.
_GAMES_QUALIFIER = Qualification(_GAMES, 0.5, "games played", "ours")


def qualification_for(position_group: str | None) -> Qualification:
    return _NFL_QUALIFIERS.get((position_group or "").upper(), _GAMES_QUALIFIER)


def team_games(loader: Any, season: int) -> int | None:
    """How many regular-season games a team in this season has actually played.

    Measured out of the schedule file rather than derived from the number of
    weeks: 2021 added a game without adding a bye-adjusted week count, a season in
    progress has played fewer than it will, and one cancelled game (2022's
    Bills-Bengals) means not every club reaches the same total. Returns None when
    the schedule is not loaded, which makes every qualification fall back to a
    rule that does not need it.
    """
    if not loader.table_exists("games"):
        return None
    cur = loader.cursor()
    row = cur.execute(
        """
        SELECT max(played) FROM (
            SELECT team, count(*) AS played FROM (
                SELECT home_team AS team FROM games
                WHERE season = ? AND game_type = 'REG' AND home_score IS NOT NULL
                UNION ALL
                SELECT away_team AS team FROM games
                WHERE season = ? AND game_type = 'REG' AND away_score IS NOT NULL
            ) GROUP BY team
        )
        """,
        [season, season],
    ).fetchone()
    return int(row[0]) if row and row[0] else None


@dataclass(frozen=True)
class ResolvedQualification:
    column: str | None
    threshold: float | None
    words: str
    computed_by_us: bool


def resolve_qualification(
    loader: Any,
    position_group: str | None,
    columns: Iterable[str],
    *,
    season: int | None,
    seasons_in_scope: Sequence[int],
) -> ResolvedQualification:
    """Turn a per-team-game rate into a number for this scope, and a sentence.

    Career scope uses one qualifying season's worth of volume, not a career's:
    a bar that scaled with career length would rank a fifteen-year starter against
    nobody. The sentence says which of the two it is.
    """
    rule = qualification_for(position_group)
    column = first_present(columns, rule.columns)
    if column is None:
        rule = _GAMES_QUALIFIER
        column = first_present(columns, rule.columns)
    reference_season = season if season is not None else (max(seasons_in_scope) if seasons_in_scope else None)
    games = team_games(loader, reference_season) if reference_season is not None else None
    if column is None or games is None:
        return ResolvedQualification(
            column=None,
            threshold=None,
            words=(
                "Everyone with a season row is in the cohort: the volume column this "
                "position group qualifies on is not in the loaded data, so no bar was applied."
            ),
            computed_by_us=True,
        )
    threshold = rule.per_team_game * games
    provenance = (
        "the NFL's own qualifier for its season leaders"
        if rule.source == "NFL"
        else "our own rule, because the league publishes no volume qualifier for this position group"
    )
    scope_words = (
        f"in {season}" if season is not None
        else "over the seasons in scope, measured as one qualifying season's worth"
    )
    return ResolvedQualification(
        column=column,
        threshold=threshold,
        words=(
            f"At least {rule.per_team_game:g} {rule.noun} per team game "
            f"({threshold:g} across a {games}-game team season) {scope_words} — {provenance}."
        ),
        computed_by_us=rule.source != "NFL",
    )


# --- the cohort ----------------------------------------------------------------


def _sum(column: str) -> str:
    return f'sum(CAST("{column}" AS DOUBLE))'


def _metric_columns(metric: Metric, columns: Iterable[str]) -> tuple[str, str] | None:
    """The numerator and denominator column this metric can actually use."""
    numerator = first_present(columns, metric.numerator)
    denominator = first_present(columns, metric.denominator)
    if numerator is None or denominator is None:
        return None
    if metric.weight is not None and first_present(columns, metric.weight) is None:
        return None
    return numerator, denominator


def _selects(metrics: Sequence[Metric], columns: Iterable[str]) -> tuple[list[Metric], list[str]]:
    """One SELECT list covering every usable metric, and the metrics it covers."""
    usable: list[Metric] = []
    selects: list[str] = []
    for metric in metrics:
        resolved = _metric_columns(metric, columns)
        if resolved is None:
            continue
        numerator, denominator = resolved
        if metric.weight is not None:
            weight = first_present(columns, metric.weight)
            # The stored rate is only meaningful where it exists: a season with a
            # NULL CPOE must not contribute its attempts to the denominator, or
            # every pre-2006 season would drag the career figure toward zero.
            selects.append(
                f'sum(CAST("{numerator}" AS DOUBLE) * CAST("{weight}" AS DOUBLE)) AS "n_{metric.id}"'
            )
            selects.append(
                f'sum(CASE WHEN "{numerator}" IS NOT NULL THEN CAST("{weight}" AS DOUBLE) END)'
                f' AS "d_{metric.id}"'
            )
        else:
            selects.append(f'{_sum(numerator)} AS "n_{metric.id}"')
            selects.append(f'{_sum(denominator)} AS "d_{metric.id}"')
        usable.append(metric)
    return usable, selects


def _ratio(numerator: float | None, denominator: float | None, scale: float) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * scale


def _scale(metric: Metric) -> float:
    """100 for a ratio of counts shown as a percentage, 1 for anything else.

    A stored rate is the trap here: CPOE already arrives in percentage points, so
    re-weighting it by attempts and then multiplying by a hundred would report a
    two-point CPOE as two hundred.
    """
    return 100.0 if metric.unit == "percent" and metric.weight is None else 1.0


def _percentile(value: float, peers: Sequence[float], higher_is_better: bool) -> float | None:
    """PERCENT_RANK: the share of the cohort this player is strictly better than.

    Returns None for a cohort of one, where the concept has no content — a bar
    reading "100th percentile of 1" is the kind of number this site exists not to
    print.
    """
    if len(peers) < 2:
        return None
    if higher_is_better:
        better_than = sum(1 for peer in peers if peer < value)
    else:
        better_than = sum(1 for peer in peers if peer > value)
    return round(100.0 * better_than / (len(peers) - 1), 1)


def _player_season_rows(loader: Any, gsis_id: str) -> list[tuple[int, str | None]]:
    cur = loader.cursor()
    return cur.execute(
        f"SELECT DISTINCT season, position_group FROM {SEASON_TABLE} WHERE player_id = ? ORDER BY season",
        [gsis_id],
    ).fetchall()


def position_group_for(loader: Any, gsis_id: str, season: int | None = None) -> str | None:
    """This player's position group, preferring the season table's own answer.

    A player's group can change (a college quarterback playing receiver), and the
    season file records what he was that year while `players.parquet` records only
    what he is now. Cohorts are built from the season file, so the group has to be
    read from the same place or a player would be ranked against peers his own row
    says he is not one of.
    """
    columns = table_columns(loader, SEASON_TABLE)
    if "position_group" in columns:
        cur = loader.cursor()
        params: list[Any] = [gsis_id]
        where = "player_id = ? AND position_group IS NOT NULL"
        if season is not None:
            where += " AND season = ?"
            params.append(season)
        row = cur.execute(
            f"SELECT position_group FROM {SEASON_TABLE} WHERE {where} "
            "GROUP BY position_group ORDER BY count(*) DESC LIMIT 1",
            params,
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    if loader.table_exists("players"):
        cur = loader.cursor()
        row = cur.execute(
            "SELECT position_group FROM players WHERE gsis_id = ?", [gsis_id]
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    return None


def player_percentiles(
    gsis_id: str,
    *,
    season: int | str | None = None,
    position_group: str | None = None,
    loader: Any = None,
) -> dict[str, Any]:
    """Percentile bars for one player against his positional peers.

    `season` is a season number or `"career"` (the default), which pools every
    season in the table. The cohort, its size and its qualification sentence are
    always present; `metrics` is absent when this position group has none we can
    compute, because an empty list of bars would render as a block that failed
    rather than a block that does not apply.
    """
    loader = resolve_loader(loader)
    scope_season: int | None = None
    if season is not None and season != CAREER:
        scope_season = int(season)

    if not ensure_source(loader, "player_season_reg"):
        return {
            "gsis_id": gsis_id,
            "scope": CAREER if scope_season is None else "season",
            "season": scope_season,
            "cohort": {
                "position_group": position_group,
                "season": scope_season,
                "n": 0,
                "qualification": "The season stats file is not loaded, so no cohort could be built.",
                "computed_by_us": True,
            },
            "note": "Season stats are not available in this deployment yet.",
        }

    group = (position_group or position_group_for(loader, gsis_id, scope_season) or "").upper() or None
    columns = table_columns(loader, SEASON_TABLE)
    metrics = METRICS.get(group or "", ())
    usable, selects = _selects(metrics, columns)

    seasons = [row[0] for row in _player_season_rows(loader, gsis_id)]
    qualification = resolve_qualification(
        loader, group, columns, season=scope_season, seasons_in_scope=seasons
    )

    cohort_where = ["player_id IS NOT NULL"]
    params: list[Any] = []
    if group and "position_group" in columns:
        cohort_where.append("position_group = ?")
        params.append(group)
    if scope_season is not None:
        cohort_where.append("season = ?")
        params.append(scope_season)

    having = ""
    if qualification.column is not None and qualification.threshold is not None:
        having = f'HAVING {_sum(qualification.column)} >= ?'

    cur = loader.cursor()
    select_sql = ", ".join(["player_id", *selects]) if selects else "player_id"
    rows = cur.execute(
        f"SELECT {select_sql} FROM {SEASON_TABLE} WHERE {' AND '.join(cohort_where)} "
        f"GROUP BY player_id {having}",
        params + ([qualification.threshold] if having else []),
    ).fetchall()

    cohort_ids = {row[0] for row in rows}
    payload: dict[str, Any] = {
        "gsis_id": gsis_id,
        "scope": CAREER if scope_season is None else "season",
        "season": scope_season,
        "position_group": group,
        "cohort": {
            "position_group": group,
            "season": scope_season,
            "n": len(cohort_ids),
            "qualification": qualification.words,
            "computed_by_us": True,
        },
        "in_cohort": gsis_id in cohort_ids,
        "source_window": {
            "first_season": sources.get("player_season_reg").first_season,
            "note": "Regular-season rows only; postseason volume never enters a cohort.",
        },
    }

    if not usable:
        payload["note"] = (
            f"No percentile metrics are defined for position group {group!r}"
            if group and group not in METRICS
            else "None of this position group's metrics have a column in the loaded season stats file."
        )
        return payload

    # The player's own value is computed from his own rows whether or not he
    # qualified, so a below-the-bar season still reports a real number with no
    # percentile beside it rather than disappearing. It carries the cohort's own
    # filters minus the volume bar: a value computed over a wider set of rows than
    # the cohort was could rank a player above every peer including himself.
    own = cur.execute(
        f"SELECT {', '.join(selects)} FROM {SEASON_TABLE} "
        f"WHERE player_id = ? AND {' AND '.join(cohort_where)}",
        [gsis_id] + params,
    ).fetchone()

    metric_payloads: list[dict[str, Any]] = []
    for index, metric in enumerate(usable):
        numerator = own[index * 2] if own else None
        denominator = own[index * 2 + 1] if own else None
        scale = _scale(metric)
        value = _ratio(numerator, denominator, scale)
        peers = [
            peer for peer in (
                _ratio(row[index * 2 + 1], row[index * 2 + 2], scale) for row in rows
            )
            if peer is not None
        ]
        entry: dict[str, Any] = {
            "id": metric.id,
            "label": metric.label,
            "unit": metric.unit,
            "value": None if value is None else round(value, 4),
            "higher_is_better": metric.higher_is_better,
            "n": len(peers),
            "median": round(_median(peers), 3) if peers else None,
            "percentile": (
                _percentile(value, peers, metric.higher_is_better)
                if value is not None and gsis_id in cohort_ids
                else None
            ),
            "computed_by_us": True,
            "coverage_note": None,
            "note": metric.note or None,
        }
        if metric.first_season is not None:
            entry["coverage_note"] = (
                f"Not charted before {metric.first_season}; earlier seasons are empty, not zero."
            )
            entry["first_season"] = metric.first_season
        metric_payloads.append(entry)

    payload["metrics"] = metric_payloads
    if not payload["in_cohort"]:
        payload["note"] = (
            "This player did not clear the cohort's volume bar in this scope, so his "
            "values are shown without a percentile beside them."
        )
    return payload


def headline_rate(gsis_id: str, *, loader: Any = None) -> dict[str, Any] | None:
    """The one career rate the hub puts on a tile, with its percentile and cohort.

    The hub reads this rather than computing its own so the tile and the
    percentile strip below it can never disagree about the same number.
    """
    payload = player_percentiles(gsis_id, season=CAREER, loader=loader)
    metrics = payload.get("metrics") or []
    for metric in metrics:
        if metric["value"] is not None:
            return {**metric, "cohort": payload["cohort"], "in_cohort": payload["in_cohort"]}
    return None
