"""The leaderboard engine: one catalogue of boards, three scopes, one query shape.

Four rules carry this module, and every one of them is a rule about honesty rather
than about SQL.

**Every board states the window it covers, and none of them claims more.** Our
play-level floor is `sources.FIRST_SEASON`. A passing-yards list that did not say so
would be read as the complete record of the league, and it is not — it starts in the
middle. The floor is read from the registry, the ceiling is measured from the table
the board actually reads, and boards whose metric has a narrower window carry that
narrower one: air-yards-derived stats from `CHARTING_FIRST_SEASON`, Next Gen Stats
from `NGS_FIRST_SEASON`. CPOE exists twice, in two different windows, from two
different sources, and appears here as two separately labelled boards rather than one
board that quietly changes meaning in 2016.

**A rate board without a stated minimum is a list of people who attempted three
passes.** Every rate carries its qualification as a sentence with its number in it,
and the per-team-game rates come from `repo/percentiles.py` so the cohort on a player
page and the bar on a leaderboard cannot drift into two different definitions of
"qualified". Turning qualification off is allowed and is stated in the payload too.

**Rates are pooled, never averaged.** Career scope is a GROUP BY across seasons whose
value is `SUM(numerator) / SUM(denominator)` (SPEC 0.7). The one stored rate on this
surface — CPOE — is re-weighted by the volume it was computed over before it is
summed, and the seasons where it is NULL contribute neither numerator nor denominator,
because a pre-charting season is missing, not zero.

**A column that is not loaded is a missing board, not a board of zeroes.** Every stat
names candidate columns; a stat none of whose columns are present is left out of the
hub and reported in `unavailable` with the reason. A whole category can disappear that
way, which is the correct behaviour on a deployment that has not loaded that file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from .. import sources
from ..etl import derived
from ..etl.pbp_derive import DERIVED_NAME as PBP_DERIVED
from ..glossary import GLOSSARY
from ..loader import SeasonBusy
from .percentiles import (
    Qualification,
    ensure_source,
    first_present,
    qualification_for,
    resolve_loader,
    table_columns,
    team_games,
)
# The fantasy coefficients live beside the game log that first needed them. They are
# imported rather than restated because correction 9 makes one scoring format follow
# a visitor across surfaces: a leaderboard and a game log that disagree about what a
# lost fumble costs would be two products. See this package's notes — the tuple wants
# promoting into a shared module, which is not a file this package owns.
from .players import _FANTASY

logger = logging.getLogger(__name__)

Scope = Literal["career", "season", "game"]
SCOPES: tuple[Scope, ...] = ("career", "season", "game")

SCOPE_LABELS: dict[str, str] = {
    "career": "Career",
    "season": "Single season",
    "game": "Single game",
}

#: Fantasy scoring formats, as a scope control rather than three separate boards
#: (SPEC correction 9). Half-PPR has no published column anywhere in nflverse, which
#: is the reason all three are computed from the box line instead of read.
SCORING_FORMATS: dict[str, float] = {"standard": 0.0, "half": 0.5, "ppr": 1.0}
SCORING_LABELS: dict[str, str] = {
    "standard": "Standard (no point per reception)",
    "half": "Half PPR (0.5 per reception)",
    "ppr": "PPR (1 point per reception)",
}
DEFAULT_SCORING = "ppr"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

#: Every board on this surface is regular season. Postseason totals are a different
#: population — four games against the best clubs, with no volume qualifier the league
#: publishes — and pooling them into a season board would silently reward playoff runs.
SEASON_TYPE = "REG"

_BOX_SEASON_TABLE = "player_season_reg"
_BOX_GAME_TABLE = "player_week"
_EPA_TABLE = "derived_player_game_epa"
_NGS_PASSING_TABLE = "ngs_passing"


class UnknownBoard(KeyError):
    """No such category, or no such stat inside it."""


# --- qualification -------------------------------------------------------------


@dataclass(frozen=True)
class Qualifier:
    """A volume bar expressed per team game, and everything needed to say it aloud.

    Per-team-game rather than per-season because the season is not a constant: 1999
    ran sixteen games and 2021 runs seventeen, and a fixed "224 attempts" would move
    the bar every time the schedule changed. `columns` is separate from the rate so
    the same league qualifier can be applied to a different denominator — the EPA
    boards count dropbacks, which include sacks — with `applied_to` saying so.
    """

    per_team_game: float
    noun: str
    #: "NFL" for the league's own published qualifier, "ours" for one we invented.
    #: Ours are labelled as ours everywhere they render.
    source: str
    columns: tuple[str, ...]
    applied_to: str = ""


def _league_qualifier(
    group: str | None,
    *,
    columns: tuple[str, ...] | None = None,
    noun: str | None = None,
    applied_to: str = "",
) -> Qualifier:
    """A qualifier whose *number* comes from `repo/percentiles.py` and nowhere else."""
    rule: Qualification = qualification_for(group)
    return Qualifier(
        per_team_game=rule.per_team_game,
        noun=noun or rule.noun,
        source=rule.source,
        columns=columns or rule.columns,
        applied_to=applied_to,
    )


_QB_VOLUME = _league_qualifier("QB")
_RB_VOLUME = _league_qualifier("RB")
_WR_VOLUME = _league_qualifier("WR")
#: The fallback for everything the league publishes no qualifier for: half the team's
#: games. Ours, and taken from percentiles so the two surfaces share the one number.
_GAMES_VOLUME = _league_qualifier(None)

_DROPBACK_QUALIFIER = _league_qualifier(
    "QB",
    columns=("plays",),
    noun="dropbacks",
    applied_to=(
        "applied to dropbacks, which include sacks, because that is the denominator "
        "this rate is divided by"
    ),
)
_CARRY_EPA_QUALIFIER = _league_qualifier("RB", columns=("plays",), noun="carries")
_TARGET_EPA_QUALIFIER = _league_qualifier("WR", columns=("plays",), noun="targets")

#: Kicking and returning have no league qualifier and no percentile cohort to borrow
#: one from, so these two are ours, labelled as ours, and stated in full on the board.
_FG_QUALIFIER = Qualifier(1.0, "field goal attempts", "ours", ("fg_att", "fg_attempts"))
_RETURN_QUALIFIER = Qualifier(0.75, "returns", "ours", ())


@dataclass(frozen=True)
class ResolvedQualification:
    """A qualifier turned into numbers for one request, plus the sentence for it."""

    applied: bool
    words: str
    column: str | None = None
    #: Career and game scope have one threshold; season scope has one per season,
    #: because a seventeen-game season asks for more volume than a sixteen-game one.
    threshold: float | None = None
    by_season: dict[int, float] = field(default_factory=dict)
    computed_by_us: bool = False


# --- the catalogue --------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    """One term of a stat we compute rather than read: columns and a coefficient."""

    id: str
    columns: tuple[str, ...]
    coefficient: float


@dataclass(frozen=True)
class Stat:
    """One board: what it measures, where it reads it, and what it may not claim."""

    id: str
    label: str
    definition: str
    #: "count" (a total), "rate" (pooled numerator over denominator), "computed"
    #: (a sum of coefficients over several columns — ours, and labelled as ours).
    kind: Literal["count", "rate", "computed"]
    #: "box" reads the player season/week stat files; "epa" the derived per-game
    #: table; "ngs_passing" the Next Gen Stats file with its own narrower window.
    source: Literal["box", "epa", "ngs_passing"] = "box"
    unit: str = "count"
    numerator: tuple[str, ...] = ()
    denominator: tuple[str, ...] = ()
    #: Set when `numerator` names a column that is *already* a rate. It is multiplied
    #: by this volume before summing, so a career figure is volume-weighted rather
    #: than the mean of the seasons.
    weight: tuple[str, ...] | None = None
    components: tuple[Component, ...] = ()
    aggregate: Literal["sum", "max"] = "sum"
    higher_is_better: bool = True
    decimals: int = 0
    scale: float = 1.0
    #: Offensive role in `derived_player_game_epa`; None pools every role.
    role: str | None = None
    qualifier: Qualifier | None = None
    #: Only when narrower than the source's own floor. Read from `sources`, never
    #: written as a year.
    first_season: int | None = None
    scopes: tuple[Scope, ...] = SCOPES
    support: tuple[tuple[str, tuple[str, ...], str], ...] = ()
    formula: str = ""
    note: str = ""
    #: A number nflverse does not publish, that we worked out. The UI marks these.
    computed_by_us: bool = False


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str
    stats: tuple[Stat, ...]

    @property
    def default_stat(self) -> str:
        return self.stats[0].id


_PASS_ATTEMPTS = ("attempts", "passing_attempts", "pass_attempts")
_CARRIES = ("carries", "rushing_attempts", "rush_atts")
_INTERCEPTIONS = ("passing_interceptions", "interceptions")

#: Touchdowns a player *scored*. A quarterback does not score on a throw, so
#: `passing_tds` is deliberately absent — it appears in "touchdowns accounted for",
#: which is a different question and says so.
_TD_SCORED: tuple[Component, ...] = (
    Component("rushing_tds", ("rushing_tds",), 1.0),
    Component("receiving_tds", ("receiving_tds",), 1.0),
    Component("special_teams_tds", ("special_teams_tds",), 1.0),
    Component("def_tds", ("def_tds",), 1.0),
    Component("fumble_recovery_tds", ("fumble_recovery_tds",), 1.0),
)

_TD_ACCOUNTED: tuple[Component, ...] = (
    Component("passing_tds", ("passing_tds",), 1.0),
    Component("rushing_tds", ("rushing_tds",), 1.0),
    Component("receiving_tds", ("receiving_tds",), 1.0),
)

_POINTS: tuple[Component, ...] = (
    Component("rushing_tds", ("rushing_tds",), 6.0),
    Component("receiving_tds", ("receiving_tds",), 6.0),
    Component("special_teams_tds", ("special_teams_tds",), 6.0),
    Component("def_tds", ("def_tds",), 6.0),
    Component("fumble_recovery_tds", ("fumble_recovery_tds",), 6.0),
    Component("fg_made", ("fg_made",), 3.0),
    Component("pat_made", ("pat_made",), 1.0),
    Component("rushing_2pt", ("rushing_2pt_conversions",), 2.0),
    Component("receiving_2pt", ("receiving_2pt_conversions",), 2.0),
)

#: Fantasy scoring minus the receptions term, which is the format control and is
#: added per request. Coefficients are `repo/players.py`'s, imported not restated.
_FANTASY_COMPONENTS: tuple[Component, ...] = tuple(
    Component(name, candidates, coefficient) for name, candidates, coefficient in _FANTASY
)

_FANTASY_FORMULA = (
    "0.04 per passing yard, 4 per passing touchdown, -2 per interception, 0.1 per "
    "rushing and receiving yard, 6 per rushing and receiving touchdown, -2 per lost "
    "fumble, plus the format's points per reception."
)


CATALOGUE: tuple[Category, ...] = (
    Category(
        "passing",
        "Passing",
        "Everything thrown, from the season stat files.",
        (
            Stat(
                "passing_yards", "Passing yards",
                "Net passing yards, pooled across every season in scope.",
                "count", unit="yards", numerator=("passing_yards",),
                support=(
                    ("attempts", _PASS_ATTEMPTS, "Att"),
                    ("completions", ("completions",), "Cmp"),
                    ("passing_tds", ("passing_tds",), "TD"),
                ),
            ),
            Stat(
                "passing_tds", "Passing touchdowns",
                "Touchdowns thrown.", "count", numerator=("passing_tds",),
                support=(("attempts", _PASS_ATTEMPTS, "Att"), ("passing_yards", ("passing_yards",), "Yds")),
            ),
            Stat(
                "completions", "Completions", "Completed passes.", "count",
                numerator=("completions",), support=(("attempts", _PASS_ATTEMPTS, "Att"),),
            ),
            Stat(
                "attempts", "Pass attempts", "Passes thrown, sacks excluded.", "count",
                numerator=_PASS_ATTEMPTS,
            ),
            Stat(
                "passing_first_downs", "Passing first downs",
                "First downs gained by pass.", "count", numerator=("passing_first_downs",),
            ),
            Stat(
                "passing_epa", "Passing EPA",
                "Total expected points added as a passer, pooled across the scope.",
                "count", unit="epa", numerator=("passing_epa",), decimals=1,
                support=(("attempts", _PASS_ATTEMPTS, "Att"),),
                note="Expected points are complete from the first season we hold.",
            ),
            Stat(
                "yards_per_attempt", "Yards per attempt",
                "Passing yards divided by attempts, pooled: total yards over total "
                "attempts, never the average of season figures.",
                "rate", unit="yards", numerator=("passing_yards",), denominator=_PASS_ATTEMPTS,
                decimals=2, qualifier=_QB_VOLUME,
            ),
            Stat(
                "completion_pct", "Completion percentage",
                "Completions over attempts, pooled across the scope.",
                "rate", unit="percent", numerator=("completions",), denominator=_PASS_ATTEMPTS,
                decimals=1, scale=100.0, qualifier=_QB_VOLUME,
            ),
            Stat(
                "interception_pct", "Interception rate",
                "Interceptions over attempts, pooled. Lower is better.",
                "rate", unit="percent", numerator=_INTERCEPTIONS, denominator=_PASS_ATTEMPTS,
                decimals=2, scale=100.0, higher_is_better=False, qualifier=_QB_VOLUME,
            ),
        ),
    ),
    Category(
        "rushing",
        "Rushing",
        "Carries and what came of them.",
        (
            Stat(
                "rushing_yards", "Rushing yards", "Yards gained rushing.", "count",
                unit="yards", numerator=("rushing_yards",),
                support=(("carries", _CARRIES, "Att"), ("rushing_tds", ("rushing_tds",), "TD")),
            ),
            Stat(
                "rushing_tds", "Rushing touchdowns", "Touchdowns scored rushing.",
                "count", numerator=("rushing_tds",), support=(("carries", _CARRIES, "Att"),),
            ),
            Stat("carries", "Carries", "Rushing attempts.", "count", numerator=_CARRIES),
            Stat(
                "rushing_first_downs", "Rushing first downs",
                "First downs gained rushing.", "count", numerator=("rushing_first_downs",),
            ),
            Stat(
                "rushing_epa", "Rushing EPA",
                "Total expected points added as a rusher.", "count", unit="epa",
                numerator=("rushing_epa",), decimals=1,
                support=(("carries", _CARRIES, "Att"),),
            ),
            Stat(
                "yards_per_carry", "Yards per carry",
                "Rushing yards over carries, pooled across the scope.",
                "rate", unit="yards", numerator=("rushing_yards",), denominator=_CARRIES,
                decimals=2, qualifier=_RB_VOLUME,
            ),
        ),
    ),
    Category(
        "receiving",
        "Receiving",
        "Targets, catches and the yards after them.",
        (
            Stat(
                "receiving_yards", "Receiving yards", "Yards gained receiving.", "count",
                unit="yards", numerator=("receiving_yards",),
                support=(
                    ("receptions", ("receptions",), "Rec"),
                    ("targets", ("targets",), "Tgt"),
                    ("receiving_tds", ("receiving_tds",), "TD"),
                ),
            ),
            Stat(
                "receptions", "Receptions", "Passes caught.", "count",
                numerator=("receptions",), support=(("targets", ("targets",), "Tgt"),),
            ),
            Stat(
                "receiving_tds", "Receiving touchdowns", "Touchdowns caught.", "count",
                numerator=("receiving_tds",), support=(("receptions", ("receptions",), "Rec"),),
            ),
            Stat("targets", "Targets", "Passes thrown at this receiver.", "count",
                 numerator=("targets",)),
            Stat(
                "receiving_epa", "Receiving EPA",
                "Total expected points added as a receiver.", "count", unit="epa",
                numerator=("receiving_epa",), decimals=1,
                support=(("targets", ("targets",), "Tgt"),),
            ),
            Stat(
                "receiving_yards_after_catch", "Yards after catch",
                "Yards gained after the ball arrived.", "count", unit="yards",
                numerator=("receiving_yards_after_catch",),
                first_season=sources.CHARTING_FIRST_SEASON,
                note=(
                    "Yards after catch were not charted before this board's first "
                    "season; earlier seasons hold no value, not a zero."
                ),
            ),
            Stat(
                "yards_per_reception", "Yards per reception",
                "Receiving yards over receptions, pooled across the scope.",
                "rate", unit="yards", numerator=("receiving_yards",), denominator=("receptions",),
                decimals=2, qualifier=_WR_VOLUME,
            ),
            Stat(
                "catch_rate", "Catch rate",
                "Receptions over targets, pooled across the scope.",
                "rate", unit="percent", numerator=("receptions",), denominator=("targets",),
                decimals=1, scale=100.0, qualifier=_WR_VOLUME,
            ),
        ),
    ),
    Category(
        "defence",
        "Defence",
        "Defensive production as the season stat files record it.",
        (
            Stat(
                "def_sacks", "Sacks", "Sacks, halves included as the source records them.",
                "count", numerator=("def_sacks",), decimals=1,
                support=(("def_qb_hits", ("def_qb_hits",), "QB hits"),),
            ),
            Stat(
                "def_interceptions", "Interceptions", "Passes intercepted.", "count",
                numerator=("def_interceptions",),
                support=(("def_pass_defended", ("def_pass_defended",), "PD"),),
            ),
            Stat(
                "def_tackles_solo", "Solo tackles", "Tackles made unassisted.", "count",
                numerator=("def_tackles_solo",),
            ),
            Stat(
                "def_tackles_for_loss", "Tackles for loss",
                "Tackles behind the line of scrimmage.", "count",
                numerator=("def_tackles_for_loss",), decimals=1,
            ),
            Stat(
                "def_pass_defended", "Passes defended", "Passes broken up.", "count",
                numerator=("def_pass_defended",),
            ),
            Stat(
                "def_fumbles_forced", "Forced fumbles", "Fumbles forced.", "count",
                numerator=("def_fumbles_forced",),
            ),
        ),
    ),
    Category(
        "kicking",
        "Kicking",
        "Place kicking, from the season stat files.",
        (
            Stat(
                "fg_made", "Field goals made", "Field goals converted.", "count",
                numerator=("fg_made",),
                support=(("fg_att", ("fg_att", "fg_attempts"), "Att"),),
            ),
            Stat(
                "fg_long", "Longest field goal",
                "The longest field goal made in the scope — a maximum, not a total.",
                "count", unit="yards", numerator=("fg_long",), aggregate="max",
                scopes=("career", "season"),
            ),
            Stat(
                "pat_made", "Extra points made", "Extra points converted.", "count",
                numerator=("pat_made",),
            ),
            Stat(
                "fg_pct", "Field goal percentage",
                "Field goals made over attempted, pooled across the scope.",
                "rate", unit="percent", numerator=("fg_made",),
                denominator=("fg_att", "fg_attempts"), decimals=1, scale=100.0,
                qualifier=_FG_QUALIFIER,
            ),
        ),
    ),
    Category(
        "returns",
        "Returns",
        "Punt and kickoff returns.",
        (
            Stat(
                "punt_return_yards", "Punt return yards", "Yards gained returning punts.",
                "count", unit="yards", numerator=("punt_return_yards",),
                support=(("punt_returns", ("punt_returns",), "Ret"),),
            ),
            Stat(
                "kickoff_return_yards", "Kickoff return yards",
                "Yards gained returning kickoffs.", "count", unit="yards",
                numerator=("kickoff_return_yards",),
                support=(("kickoff_returns", ("kickoff_returns",), "Ret"),),
            ),
            Stat(
                "special_teams_tds", "Return touchdowns",
                "Touchdowns scored on special teams.", "count",
                numerator=("special_teams_tds",),
            ),
            Stat(
                "yards_per_punt_return", "Yards per punt return",
                "Punt return yards over punt returns, pooled across the scope.",
                "rate", unit="yards", numerator=("punt_return_yards",),
                denominator=("punt_returns",), decimals=2,
                qualifier=Qualifier(
                    _RETURN_QUALIFIER.per_team_game, "punt returns", "ours", ("punt_returns",)
                ),
            ),
        ),
    ),
    Category(
        "scoring",
        "Scoring",
        "Points and touchdowns. Both are ours: nflverse publishes neither as a column.",
        (
            Stat(
                "touchdowns_scored", "Touchdowns scored",
                "Touchdowns this player scored himself — rushing, receiving, on "
                "defence and on special teams. A quarterback does not score on a "
                "throw, so passing touchdowns are not counted here.",
                "computed", components=_TD_SCORED, computed_by_us=True,
                formula="Sum of the touchdown columns this deployment has, passing excluded.",
            ),
            Stat(
                "touchdowns_accounted_for", "Touchdowns accounted for",
                "Touchdowns thrown, run in and caught — the quarterback's version of "
                "the question, and a different number from touchdowns scored.",
                "computed", components=_TD_ACCOUNTED, computed_by_us=True,
                formula="passing + rushing + receiving touchdowns.",
            ),
            Stat(
                "points", "Points scored",
                "Points this player put on the board: six a touchdown, three a field "
                "goal, one an extra point, two a conversion.",
                "computed", unit="points", components=_POINTS, computed_by_us=True,
                formula="6 x touchdowns scored + 3 x field goals + 1 x extra points + 2 x conversions.",
            ),
        ),
    ),
    Category(
        "advanced",
        "Advanced",
        "Expected points added, success rate and completion percentage over expected — "
        "each on the window its own model covers.",
        (
            Stat(
                "epa_per_dropback", "EPA per dropback",
                "Expected points added per dropback, pooled: total EPA over total "
                "dropbacks. Sacks are inside both.",
                "rate", source="epa", unit="epa", role="passer", decimals=3,
                qualifier=_DROPBACK_QUALIFIER,
                support=(("plays", (), "Dropbacks"),),
            ),
            Stat(
                "epa_per_carry", "EPA per carry",
                "Expected points added per carry, pooled across the scope.",
                "rate", source="epa", unit="epa", role="rusher", decimals=3,
                qualifier=_CARRY_EPA_QUALIFIER, support=(("plays", (), "Carries"),),
            ),
            Stat(
                "epa_per_target", "EPA per target",
                "Expected points added per target, pooled across the scope.",
                "rate", source="epa", unit="epa", role="receiver", decimals=3,
                qualifier=_TARGET_EPA_QUALIFIER, support=(("plays", (), "Targets"),),
            ),
            Stat(
                "success_rate_pass", "Passing success rate",
                "Share of dropbacks with positive expected points added, pooled.",
                "rate", source="epa", unit="percent", role="passer",
                numerator=("successes",), decimals=1, scale=100.0,
                qualifier=_DROPBACK_QUALIFIER,
                support=(("plays", (), "Dropbacks"),),
            ),
            Stat(
                "success_rate_rush", "Rushing success rate",
                "Share of carries with positive expected points added, pooled.",
                "rate", source="epa", unit="percent", role="rusher",
                numerator=("successes",), decimals=1, scale=100.0,
                qualifier=_CARRY_EPA_QUALIFIER,
                support=(("plays", (), "Carries"),),
            ),
            Stat(
                "epa_total", "Total EPA (all offensive roles)",
                "Expected points added as passer, rusher and receiver together.",
                "count", source="epa", unit="epa", decimals=1,
                support=(("plays", (), "Plays"),),
                note=(
                    "A passer's plays are charged nflfastR's qb_epa and a rusher's or "
                    "receiver's the play's own epa, so a player who did both has two "
                    "conventions inside one total."
                ),
            ),
            Stat(
                "cpoe", "CPOE (nflfastR)",
                "Completion percentage over expected, from nflfastR's own model, "
                "re-weighted by attempts before pooling so a career figure is not the "
                "mean of its seasons.",
                "rate", unit="percent", numerator=("passing_cpoe",), denominator=_PASS_ATTEMPTS,
                weight=_PASS_ATTEMPTS, decimals=2, qualifier=_QB_VOLUME,
                first_season=sources.CHARTING_FIRST_SEASON, scopes=("career", "season"),
                note=(
                    "Air yards were not charted before this board's first season, so "
                    "CPOE does not exist for the seasons before it — it is absent, "
                    "not zero. This is a different board from CPOE (Next Gen Stats), "
                    "which covers a shorter window from a different model."
                ),
            ),
            Stat(
                "ngs_cpoe", "CPOE (Next Gen Stats)",
                "Completion percentage over expected as the NFL's own tracking model "
                "computes it, re-weighted by attempts before pooling.",
                "rate", source="ngs_passing", unit="percent",
                numerator=("completion_percentage_above_expectation",),
                denominator=("attempts", "pass_attempts"),
                weight=("attempts", "pass_attempts"), decimals=2, qualifier=_QB_VOLUME,
                first_season=sources.NGS_FIRST_SEASON, scopes=("career", "season"),
                note=(
                    "Next Gen Stats begin later than our play-by-play does, so this "
                    "board covers a shorter window than the nflfastR CPOE board and "
                    "the two are not comparable season for season."
                ),
            ),
        ),
    ),
    Category(
        "fantasy",
        "Fantasy",
        "Fantasy points computed from the box line, in three scoring formats.",
        (
            Stat(
                "fantasy_points", "Fantasy points",
                "Fantasy points, computed from the published box line in the selected "
                "scoring format.",
                "computed", unit="points", components=_FANTASY_COMPONENTS,
                computed_by_us=True, decimals=1, formula=_FANTASY_FORMULA,
                scopes=("season", "game"),
                support=(
                    ("receptions", ("receptions",), "Rec"),
                    ("games", ("games",), "G"),
                ),
            ),
            Stat(
                "fantasy_points_per_game", "Fantasy points per game",
                "Fantasy points over games played, pooled across the scope.",
                "computed", unit="points", components=_FANTASY_COMPONENTS,
                denominator=("games",), computed_by_us=True, decimals=2,
                formula=_FANTASY_FORMULA + " Divided by games played.",
                qualifier=_GAMES_VOLUME, scopes=("season",),
            ),
        ),
    ),
)

BY_ID: dict[str, Category] = {c.id: c for c in CATALOGUE}


def find(category: str, stat: str) -> tuple[Category, Stat]:
    try:
        found = BY_ID[category]
    except KeyError as exc:
        raise UnknownBoard(f"No leaderboard category {category!r}") from exc
    for candidate in found.stats:
        if candidate.id == stat:
            return found, candidate
    raise UnknownBoard(f"No stat {stat!r} in the {category!r} leaderboards")


# --- what this deployment can actually answer ------------------------------------


class _Env:
    """One request's view of the database: what is loaded, and what columns it has.

    The hub asks forty-odd boards whether they can be built, and each answer needs a
    source ensured and a table described. Without this cache that is thousands of
    catalogue queries for one page, because `ensure_source` re-reads every season's
    load-log row every time it is called.
    """

    def __init__(self, loader: Any) -> None:
        self.loader = loader
        self._sources: dict[tuple[str, bool], bool] = {}
        self._derived: dict[str, bool] = {}
        self._columns: dict[str, frozenset[str]] = {}
        self._last_season: dict[str, int | None] = {}
        self._team_games: dict[int, int | None] = {}

    def have(self, source_id: str, *, load: bool = True) -> bool:
        """Whether a source's table is there, optionally fetching it first.

        Same split as `have_derived`, for the same reason. `ensure_source` asks the
        loader to fetch anything missing, and a source this deployment does not hold
        is re-attempted on every call — which on the hub, where every source in the
        catalogue is asked about, is one download attempt per menu render. The hub
        asks with `load=False` and reports what exists; a board that was actually
        requested asks with `load=True`.
        """
        key = (source_id, load)
        if key not in self._sources:
            self._sources[key] = (
                ensure_source(self.loader, source_id)
                if load
                else self.loader.table_exists(sources.get(source_id).table)
            )
        return self._sources[key]

    def have_derived(self, table: str, *, build: bool) -> bool:
        """Whether a play-derived table is there, optionally building it first.

        `build` is the difference between a menu and a job. Deriving the play tables
        means reading twenty-seven seasons of play-by-play, and the hub — a grid of
        links somebody clicked once — must never be the request that starts it.
        Measured on a database with no derived tables: the hub took 42 seconds with
        `build=True` and 40 milliseconds without. The board that actually needs the
        table asks for it with `build=True`; the hub asks whether it exists and, if
        it does not, names the board in `unavailable` with the reason.

        `SeasonBusy` is re-raised rather than swallowed: it means "try again in a
        moment", which the router turns into a 503. Reporting it as "no data" would
        tell a visitor a leaderboard does not exist when it is merely loading.
        """
        if not build:
            return self._derived.get(table, self.loader.table_exists(table))
        if table not in self._derived:
            try:
                derived.ensure(self.loader, PBP_DERIVED, table=table)
            except SeasonBusy:
                raise
            except Exception:  # noqa: BLE001 - availability, not failure
                logger.warning(
                    "Could not build %s; the boards that read it are omitted", table,
                    exc_info=True,
                )
            self._derived[table] = self.loader.table_exists(table)
        return self._derived[table]

    def columns(self, table: str) -> frozenset[str]:
        if table not in self._columns:
            self._columns[table] = table_columns(self.loader, table)
        return self._columns[table]

    def last_season(self, table: str) -> int | None:
        """The newest season a table actually holds — measured, never assumed.

        `latest_season()` is a date calculation: in August it names a season nobody
        has played a snap of, and a board claiming it as its ceiling would be
        claiming coverage it does not have.
        """
        if table not in self._last_season:
            value: int | None = None
            if self.loader.table_exists(table) and "season" in self.columns(table):
                row = self.loader.cursor().execute(f"SELECT max(season) FROM {table}").fetchone()
                value = int(row[0]) if row and row[0] is not None else None
            self._last_season[table] = value
        return self._last_season[table]

    def team_games(self, season: int) -> int | None:
        if season not in self._team_games:
            self._team_games[season] = team_games(self.loader, season)
        return self._team_games[season]

    def newest_player_season(self) -> int | None:
        if not self.have("players"):
            return None
        row = self.loader.cursor().execute("SELECT max(last_season) FROM players").fetchone()
        return int(row[0]) if row and row[0] is not None else None


def _table_for(stat: Stat, scope: str) -> str:
    if stat.source == "epa":
        return _EPA_TABLE
    if stat.source == "ngs_passing":
        return _NGS_PASSING_TABLE
    return _BOX_SEASON_TABLE if scope in ("career", "season") else _BOX_GAME_TABLE


def _table_available(env: _Env, stat: Stat, scope: str, *, build: bool) -> bool:
    if stat.source == "epa":
        return env.have_derived(_EPA_TABLE, build=build)
    if stat.source == "ngs_passing":
        return env.have("ngs_passing", load=build)
    return env.have(_table_for(stat, scope), load=build)


#: The column holding a player's gsis id, by however the file spells it. Next Gen
#: Stats writes `player_gsis_id` where the season stat files write `player_id`, and a
#: board that could not find the id column used to answer with an empty list instead
#: of saying it could not be built.
_PLAYER_ID_COLUMNS: tuple[str, ...] = ("player_id", "gsis_id", "player_gsis_id")


@dataclass(frozen=True)
class Resolution:
    """Which real columns a stat found, for one scope, in this deployment."""

    table: str
    player_column: str = "gsis_id"
    numerator: str | None = None
    denominator: str | None = None
    weight: str | None = None
    components: tuple[tuple[Component, str], ...] = ()
    missing_components: tuple[str, ...] = ()
    support: tuple[tuple[str, str, str], ...] = ()


def _resolve(env: _Env, stat: Stat, scope: str, *, build: bool = False) -> Resolution | None:
    """Bind a stat to columns that exist, or answer None so the board is left out.

    `build` is passed straight through to `_table_available`: resolving a board for
    the hub must not derive anything, resolving one because it was asked for must.
    """
    table = _table_for(stat, scope)
    if not _table_available(env, stat, scope, build=build):
        return None
    columns = env.columns(table)
    if not columns:
        return None
    player_column = first_present(columns, _PLAYER_ID_COLUMNS)
    if player_column is None:
        # Nothing can be ranked without an id to rank, and a board with no rankable
        # rows is a board that is not there — not one that answers with nobody on it.
        return None

    if stat.source == "epa":
        # This table is ours and `etl/pbp_derive.py` fixes its columns, so the only
        # question was whether it was built at all.
        support = tuple(
            (sid, "plays", label) for sid, _candidates, label in stat.support if "plays" in columns
        )
        return Resolution(table=table, player_column=player_column, support=support)

    numerator = denominator = weight = None
    components: list[tuple[Component, str]] = []
    missing: list[str] = []

    if stat.kind == "computed":
        for component in stat.components:
            column = first_present(columns, component.columns)
            if column is None:
                missing.append(component.id)
            else:
                components.append((component, column))
        if not components:
            return None
        if stat.denominator:
            denominator = first_present(columns, stat.denominator)
            if denominator is None:
                return None
    else:
        numerator = first_present(columns, stat.numerator)
        if numerator is None:
            return None
        if stat.kind == "rate":
            denominator = first_present(columns, stat.denominator)
            if denominator is None:
                return None
            if stat.weight is not None:
                weight = first_present(columns, stat.weight)
                if weight is None:
                    return None

    support = [
        (sid, column, label)
        for sid, candidates, label in stat.support
        if (column := first_present(columns, candidates)) is not None
    ]
    return Resolution(
        table=table,
        player_column=player_column,
        numerator=numerator,
        denominator=denominator,
        weight=weight,
        components=tuple(components),
        missing_components=tuple(missing),
        support=tuple(support),
    )


def _available_scopes(env: _Env, stat: Stat) -> list[str]:
    return [scope for scope in stat.scopes if _resolve(env, stat, scope) is not None]


# --- era windows ------------------------------------------------------------------


def _source_floor(stat: Stat) -> int:
    """The first season the data behind a board exists at all, read from the registry."""
    if stat.source == "ngs_passing":
        return sources.NGS_FIRST_SEASON
    if stat.source == "epa":
        return sources.get("pbp").first_season or sources.FIRST_SEASON
    return sources.get(_BOX_SEASON_TABLE).first_season or sources.FIRST_SEASON


_SOURCE_LABELS: dict[str, str] = {
    "box": "nflverse season and weekly player stats",
    "epa": "nflfastR play-by-play, via our derived per-game table",
    "ngs_passing": "Next Gen Stats",
}


def _era(env: _Env, stat: Stat, table: str) -> dict[str, Any]:
    """The window one board covers, and the sentence that has to appear beside it.

    Two windows meet here: the site's floor, and the metric's own. A CPOE board that
    borrowed the site's floor would be claiming twenty-seven seasons of a number that
    was not charted for the first seven of them.
    """
    floor = max(sources.FIRST_SEASON, stat.first_season or 0, _source_floor(stat))
    last = env.last_season(table)
    words = f"Seasons {floor} to {last}." if last is not None else f"Seasons from {floor}."
    if floor > sources.FIRST_SEASON:
        words += (
            f" This board starts later than the rest of the site: what it measures "
            f"was not recorded before {floor}, and the seasons before that hold no "
            "value rather than a zero."
        )
    else:
        words += (
            f" Modern era only — we hold no season before {sources.FIRST_SEASON}, so "
            "this board ranks the players of this window against each other and "
            "nobody else."
        )
    return {
        "from": floor,
        "to": last,
        "note": words,
        "source": _SOURCE_LABELS[stat.source],
    }


def _era_badge(env: _Env) -> dict[str, Any]:
    last = env.last_season(_BOX_SEASON_TABLE)
    return {
        "from": sources.FIRST_SEASON,
        "to": last,
        "note": (
            f"Modern era — {sources.FIRST_SEASON} to {last}. "
            if last is not None
            else f"Modern era — from {sources.FIRST_SEASON}. "
        )
        + (
            f"We hold no season before {sources.FIRST_SEASON}, so these boards rank "
            "the players of this window against each other and make no claim about "
            "the ones we do not hold."
        ),
    }


# --- the hub -----------------------------------------------------------------------


def _qualification_headline(qualifier: Qualifier) -> str:
    """The rule in words. The season's game count needs a request, so it is not here."""
    provenance = (
        "the NFL's own qualifier for its season leaders"
        if qualifier.source == "NFL"
        else "our own rule, because the league publishes no qualifier for this one"
    )
    applied = f", {qualifier.applied_to}" if qualifier.applied_to else ""
    return (
        f"At least {qualifier.per_team_game:g} {qualifier.noun} per team game{applied} "
        f"— {provenance}."
    )


def _stat_block(env: _Env, category: Category, stat: Stat, scopes: Sequence[str]) -> dict[str, Any]:
    resolution = _resolve(env, stat, scopes[0])
    block: dict[str, Any] = {
        "id": stat.id,
        "category": category.id,
        "label": stat.label,
        "definition": stat.definition,
        "unit": stat.unit,
        "higher_is_better": stat.higher_is_better,
        "scopes": list(scopes),
        "default_scope": scopes[0],
        "href": f"/leaders/{category.id}/{stat.id}",
        "era": _era(env, stat, _table_for(stat, scopes[0])),
        "computed_by_us": stat.computed_by_us,
    }
    if stat.formula:
        block["formula"] = stat.formula
    if stat.note:
        block["note"] = stat.note
    if stat.qualifier is not None:
        block["qualification"] = _qualification_headline(stat.qualifier)
    if resolution is not None:
        if resolution.missing_components:
            block["components_missing"] = list(resolution.missing_components)
        if resolution.numerator and resolution.numerator in GLOSSARY:
            block["glossary_key"] = resolution.numerator
            entry = GLOSSARY[resolution.numerator]
            if entry.get("formula") and not stat.formula:
                block["formula"] = entry["formula"]
    return block


def leaders_index(*, loader: Any = None) -> dict[str, Any]:
    """Every board this deployment can actually serve, with the window each covers.

    A stat whose columns are not loaded is not listed as a board that would return
    nothing; it is named in `unavailable` with the reason, so the grid is a list of
    things that work.
    """
    env = _Env(resolve_loader(loader))
    categories: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []

    for category in CATALOGUE:
        blocks: list[dict[str, Any]] = []
        for stat in category.stats:
            scopes = _available_scopes(env, stat)
            if not scopes:
                unavailable.append({
                    "category": category.id,
                    "stat": stat.id,
                    "label": stat.label,
                    "reason": (
                        "The columns this board reads are not in the data this "
                        "deployment has loaded."
                    ),
                })
                continue
            blocks.append(_stat_block(env, category, stat, scopes))
        if blocks:
            categories.append({
                "id": category.id,
                "label": category.label,
                "description": category.description,
                "default_stat": blocks[0]["id"],
                "href": f"/leaders/{category.id}/{blocks[0]['id']}",
                "stats": blocks,
            })

    payload: dict[str, Any] = {
        "era": _era_badge(env),
        "scopes": [{"id": scope, "label": SCOPE_LABELS[scope]} for scope in SCOPES],
        "scoring_formats": [
            {"id": key, "label": SCORING_LABELS[key]} for key in ("standard", "half", "ppr")
        ],
        "default_scoring": DEFAULT_SCORING,
        "categories": categories,
        "note": (
            "Regular season only. Every rate is pooled from totals rather than "
            "averaged across seasons, and every rate board states the minimum volume "
            "it applies before it applies it."
        ),
    }
    if unavailable:
        payload["unavailable"] = unavailable
    return payload


# --- qualification, resolved for one request ----------------------------------------


def _seasons_in_scope(env: _Env, table: str, first: int, last: int | None) -> list[int]:
    if not env.loader.table_exists(table) or "season" not in env.columns(table):
        return []
    params: list[Any] = [first]
    where = "season >= ?"
    if last is not None:
        where += " AND season <= ?"
        params.append(last)
    rows = env.loader.cursor().execute(
        f"SELECT DISTINCT season FROM {table} WHERE {where} ORDER BY season", params
    ).fetchall()
    return [int(row[0]) for row in rows if row[0] is not None]


def _resolve_qualification(
    env: _Env,
    stat: Stat,
    resolution: Resolution,
    scope: str,
    seasons: Sequence[int],
    *,
    requested: bool,
) -> ResolvedQualification:
    """Turn the per-team-game rate into this request's numbers, and into a sentence.

    Season scope gets one threshold per season, because a seventeen-game season asks
    for more volume than a sixteen-game one and a single number would be wrong at one
    end or the other. Career scope uses one qualifying season's worth: a bar that grew
    with career length would measure a fifteen-year starter against nobody. A single
    game is exactly one team game, which is the unit the league's rate is written in.
    """
    qualifier = stat.qualifier
    if qualifier is None:
        return ResolvedQualification(
            applied=False,
            words=(
                "No minimum applies: this board ranks a total, and a total is not "
                "made misleading by a small sample the way a rate is."
            ),
        )

    if not requested:
        return ResolvedQualification(
            applied=False,
            words=(
                "Minimum volume switched off. The rule that would otherwise apply is: "
                f"{_qualification_headline(qualifier)} Without it the top of this "
                "board is players with a handful of plays, and should not be read as "
                "a leaderboard."
            ),
            computed_by_us=qualifier.source != "NFL",
        )

    column = (
        "plays" if stat.source == "epa"
        else first_present(env.columns(resolution.table), qualifier.columns)
    )
    if column is None:
        return ResolvedQualification(
            applied=False,
            words=(
                "No minimum could be applied: the volume column this board qualifies "
                "on is not in the data this deployment has loaded, so every player "
                "with a value is listed."
            ),
            computed_by_us=True,
        )

    provenance = (
        "the NFL's own qualifier for its season leaders"
        if qualifier.source == "NFL"
        else "our own rule, because the league publishes no qualifier for this one"
    )
    applied_to = f" ({qualifier.applied_to})" if qualifier.applied_to else ""

    if scope == "game":
        return ResolvedQualification(
            applied=True,
            column=column,
            threshold=qualifier.per_team_game,
            words=(
                f"At least {qualifier.per_team_game:g} {qualifier.noun} in the "
                f"game{applied_to} — {provenance}, which is written per team game and "
                "so carries over to a single game unchanged."
            ),
            computed_by_us=qualifier.source != "NFL",
        )

    games = {season: env.team_games(season) for season in seasons}
    if not seasons or any(count is None for count in games.values()):
        return ResolvedQualification(
            applied=False,
            words=(
                "No minimum could be applied: the schedule file this board counts "
                "team games out of is not loaded, so every player with a value is "
                "listed."
            ),
            computed_by_us=True,
        )

    if scope == "season":
        by_season = {
            season: qualifier.per_team_game * float(count)
            for season, count in games.items()
            if count is not None
        }
        spread = sorted({round(value, 3) for value in by_season.values()})
        numbers = (
            f"{spread[0]:g} across a full season"
            if len(spread) == 1
            else f"{spread[0]:g} to {spread[-1]:g} across a full season, "
                 "depending on how many games that season ran"
        )
        return ResolvedQualification(
            applied=True,
            column=column,
            by_season=by_season,
            words=(
                f"At least {qualifier.per_team_game:g} {qualifier.noun} per team "
                f"game{applied_to} — {numbers} — {provenance}."
            ),
            computed_by_us=qualifier.source != "NFL",
        )

    reference = max(seasons)
    count = games[reference] or 0
    threshold = qualifier.per_team_game * float(count)
    return ResolvedQualification(
        applied=True,
        column=column,
        threshold=threshold,
        words=(
            f"At least {qualifier.per_team_game:g} {qualifier.noun} per team "
            f"game{applied_to} for one season — {threshold:g} in total, the volume of "
            f"a single {count}-game {reference} season — {provenance}. The career bar "
            "is one season's worth rather than a career's, or a long career would be "
            "measured against nobody."
        ),
        computed_by_us=qualifier.source != "NFL",
    )


# --- the board ----------------------------------------------------------------------


def _sum(column: str) -> str:
    return f'sum(CAST("{column}" AS DOUBLE))'


#: Decimal places every supporting number is rounded to before it leaves. The values
#: themselves are rounded in SQL to the stat's own precision; this is for the totals
#: beside them, where a summed DOUBLE arrives as 0.30000000000000004 and would render
#: as exactly that.
_SUPPORT_DECIMALS = 4


def _num(value: Any) -> float | int | None:
    """A whole number as an int, anything else rounded — 5,477.0 yards reads 5477."""
    if value is None:
        return None
    value = float(value)
    whole = round(value)
    return whole if abs(value - whole) < 1e-9 else round(value, _SUPPORT_DECIMALS)


def _is_fantasy(stat: Stat) -> bool:
    return stat.components is _FANTASY_COMPONENTS


def _value_parts(
    stat: Stat,
    resolution: Resolution,
    *,
    reception_points: float | None,
    receptions_column: str | None,
) -> tuple[str, str]:
    """The numerator and denominator aggregates, as SQL over the grouped rows."""
    if stat.source == "epa":
        # The derived table's columns are fixed by `etl/pbp_derive.py`, so the stat
        # names the one it counts rather than having it inferred from the unit — a
        # future percentage over this table would not have to be a success rate.
        column = stat.numerator[0] if stat.numerator else "epa_total"
        numerator = f'sum(CAST("{column}" AS DOUBLE))'
        return numerator, ("sum(CAST(plays AS DOUBLE))" if stat.kind == "rate" else "NULL")

    if stat.kind == "computed":
        terms = [
            f'{component.coefficient} * COALESCE(CAST("{column}" AS DOUBLE), 0)'
            for component, column in resolution.components
        ]
        if reception_points is not None and receptions_column:
            terms.append(
                f'{reception_points} * COALESCE(CAST("{receptions_column}" AS DOUBLE), 0)'
            )
        numerator = f"sum({' + '.join(terms)})"
        return numerator, (_sum(resolution.denominator) if resolution.denominator else "NULL")

    assert resolution.numerator is not None
    if stat.kind == "count":
        aggregate = "max" if stat.aggregate == "max" else "sum"
        return f'{aggregate}(CAST("{resolution.numerator}" AS DOUBLE))', "NULL"

    if stat.weight is not None and resolution.weight:
        # A stored rate. Weight it by the volume it was measured over, and let the
        # seasons where it is NULL contribute to neither side: counting their
        # attempts in the denominator would drag every career that starts before the
        # charting era toward zero and present that as a measurement.
        return (
            f'sum(CAST("{resolution.numerator}" AS DOUBLE) '
            f'* CAST("{resolution.weight}" AS DOUBLE))',
            f'sum(CASE WHEN "{resolution.numerator}" IS NOT NULL '
            f'THEN CAST("{resolution.weight}" AS DOUBLE) END)',
        )

    assert resolution.denominator is not None
    return _sum(resolution.numerator), _sum(resolution.denominator)


def _threshold_sql(qualification: ResolvedQualification, scope: str) -> str | None:
    if not qualification.applied or qualification.column is None:
        return None
    if scope == "season" and qualification.by_season:
        branches = " ".join(
            f"WHEN {season} THEN {value}"
            for season, value in sorted(qualification.by_season.items())
        )
        # No ELSE: a season with no threshold would otherwise pass silently. NULL
        # fails the comparison, which is the safe direction — but every season in
        # scope has a branch, because the seasons and the thresholds came from the
        # same list.
        return f"CASE season {branches} END"
    if qualification.threshold is None:
        return None
    return f"{qualification.threshold}"


def _team_list_sql(expression: str) -> str:
    """Every distinct club behind one player's line, in a stable order.

    Sorted rather than `string_agg(DISTINCT ...)`: a career line that reorders its
    own teams between two identical requests reads as data that changed.
    """
    return (
        f"array_to_string(list_sort(list_distinct(array_agg({expression}) "
        f"FILTER (WHERE {expression} IS NOT NULL))), ', ')"
    )


def _stat_summary(stat: Stat, resolution: Resolution | None, scoring: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": stat.id,
        "label": stat.label,
        "definition": stat.definition,
        "unit": stat.unit,
        "higher_is_better": stat.higher_is_better,
        "computed_by_us": stat.computed_by_us,
    }
    if stat.formula:
        summary["formula"] = stat.formula
    if stat.note:
        summary["note"] = stat.note
    if _is_fantasy(stat):
        summary["scoring_format"] = scoring
        summary["scoring_label"] = SCORING_LABELS[scoring]
    if resolution is not None:
        if resolution.components:
            summary["components_used"] = [column for _component, column in resolution.components]
        if resolution.missing_components:
            summary["components_missing"] = list(resolution.missing_components)
            summary["components_note"] = (
                "These components have no column in the loaded data, so they are not "
                "in the total. The number is the sum of the ones that are."
            )
        if resolution.numerator and resolution.numerator in GLOSSARY:
            summary["glossary_key"] = resolution.numerator
    return summary


def _qualification_block(qualification: ResolvedQualification) -> dict[str, Any]:
    """The rule as the payload carries it: always the sentence, then the numbers."""
    block: dict[str, Any] = {
        "applied": qualification.applied,
        "rule_text": qualification.words,
        "threshold": qualification.threshold,
        "column": qualification.column,
        "computed_by_us": qualification.computed_by_us,
    }
    if qualification.by_season:
        # Season scope has one threshold per season rather than one for the board,
        # because the seasons are not all the same length.
        block["thresholds_by_season"] = {
            str(season): value for season, value in sorted(qualification.by_season.items())
        }
    return block


def _support_columns(stat: Stat, resolution: Resolution) -> list[dict[str, str]]:
    """Headers for the supporting columns, so a table can label what it renders."""
    labels = [{"id": sid, "label": label} for sid, _column, label in resolution.support]
    if stat.kind == "rate":
        if stat.weight is None and resolution.numerator:
            labels.append({
                "id": "numerator",
                "label": GLOSSARY.get(resolution.numerator, {}).get("label", "Numerator"),
            })
        if resolution.denominator:
            labels.append({
                "id": "denominator",
                "label": GLOSSARY.get(resolution.denominator, {}).get("label", "Denominator"),
            })
    return labels


def _unavailable(
    env: _Env, category: Category, stat: Stat, scope: str, reason: str, **extra: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": {"id": category.id, "label": category.label},
        "stat": _stat_summary(stat, None, DEFAULT_SCORING),
        "scope": scope,
        "scope_label": SCOPE_LABELS.get(scope, scope),
        "era": _era(env, stat, _table_for(stat, stat.scopes[0])),
        "available": False,
        "note": reason,
    }
    payload.update(extra)
    return payload


def _rules(env: _Env, stat: Stat, resolution: Resolution, *, team: str | None, active_only: bool) -> dict[str, str]:
    rules = {
        "season_type": (
            "Regular season only. Postseason totals are not pooled in: four games "
            "against the best clubs in the league are a different population, and the "
            "league publishes no volume qualifier for them."
        ),
        "pooling": (
            "Career and multi-season figures are totals divided by totals, never the "
            "average of the seasons' own rates."
        ),
        "ties": (
            "Players level on the value shown share a rank, and every row says how "
            "many are tied there. Ranking is on the value as displayed, so two "
            "players a thousandth apart do not read as tied under a number that "
            "shows them as equal."
        ),
    }
    if stat.kind != "rate" and not resolution.denominator:
        rules["zeroes"] = (
            "A player whose total is exactly zero is left off. A player with no value "
            "at all was never counted, which is a different thing from a zero."
        )
    if team:
        rules["team"] = (
            f"Filtered to production for {team.upper()}. On a career board that is "
            "this player's total while at that club, not his career total."
        )
    if active_only:
        newest = env.newest_player_season()
        rules["active_only"] = (
            f"Active means a final season of {newest} — the newest season any player "
            "row on file claims — not a roster check."
            if newest is not None
            else "No player rows are loaded, so active and retired cannot be told apart."
        )
    return rules


def leaderboard(
    category_id: str,
    stat_id: str,
    *,
    scope: str = "career",
    position: str | None = None,
    season_min: int | None = None,
    season_max: int | None = None,
    active_only: bool = False,
    team: str | None = None,
    qualified: bool = True,
    scoring: str = DEFAULT_SCORING,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    loader: Any = None,
) -> dict[str, Any]:
    """One board, ranked, carrying its era window and its qualification rule.

    `rows` is absent — not empty — whenever the board cannot be built, so a page can
    leave the table out instead of rendering an empty one under a heading that
    promises a leaderboard. An empty `rows` means something different and narrower:
    the board exists and these filters matched nobody.
    """
    category, stat = find(category_id, stat_id)
    env = _Env(resolve_loader(loader))

    if scope not in SCOPES:
        raise ValueError(f"Unknown scope {scope!r}")
    if scoring not in SCORING_FORMATS:
        raise ValueError(f"Unknown scoring format {scoring!r}")
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    if scope not in stat.scopes:
        return _unavailable(
            env, category, stat, scope,
            f"{stat.label} has no {SCOPE_LABELS[scope].lower()} board. It is offered "
            f"for: {', '.join(SCOPE_LABELS[s].lower() for s in stat.scopes)}.",
            supported_scopes=list(stat.scopes),
        )

    resolution = _resolve(env, stat, scope, build=True)
    if resolution is None:
        return _unavailable(
            env, category, stat, scope,
            "This board is not available on this deployment: the columns it reads "
            "are not in the data that has been loaded.",
        )

    era = _era(env, stat, resolution.table)
    columns = env.columns(resolution.table)

    if active_only and env.newest_player_season() is None:
        return _unavailable(
            env, category, stat, scope,
            "Active players cannot be told from retired ones here: the player file "
            "this filter reads is not loaded.",
        )
    team_column = first_present(columns, ("team", "team_abbr", "recent_team"))
    if team and team_column is None:
        return _unavailable(
            env, category, stat, scope,
            "This board cannot be filtered by team: the table behind it carries no "
            "team column in the data that has been loaded.",
        )
    position_columns = [c for c in ("position", "position_group") if c in columns]
    if position and not position_columns and not env.have("players"):
        return _unavailable(
            env, category, stat, scope,
            "This board cannot be filtered by position: neither the table behind it "
            "nor the player file carries a position in the data that has been loaded.",
        )

    floor = era["from"]
    ceiling = era["to"]
    first = max(floor, season_min) if season_min is not None else floor
    last = season_max if season_max is not None else ceiling
    if last is not None and ceiling is not None:
        last = min(last, ceiling)
    seasons = _seasons_in_scope(env, resolution.table, first, last)

    qualification = _resolve_qualification(
        env, stat, resolution, scope, seasons, requested=qualified
    )
    rows, total = _run(
        env, stat, resolution,
        scope=scope, first=first, last=last, position=position, team=team,
        active_only=active_only, qualification=qualification, scoring=scoring,
        page=page, page_size=page_size,
    )

    payload: dict[str, Any] = {
        "category": {"id": category.id, "label": category.label},
        "stat": _stat_summary(stat, resolution, scoring),
        "scope": scope,
        "scope_label": SCOPE_LABELS[scope],
        "era": era,
        "available": True,
        "qualification": _qualification_block(qualification),
        "filters": {
            "position": position,
            "season_min": first,
            "season_max": last,
            "active_only": active_only,
            "team": team.upper() if team else None,
            "qualified": qualified,
            "scoring": scoring if _is_fantasy(stat) else None,
        },
        "seasons_in_scope": seasons,
        "support_columns": _support_columns(stat, resolution),
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "rules": _rules(env, stat, resolution, team=team, active_only=active_only),
    }
    if total == 0:
        payload["note"] = (
            "No player clears these filters. The board itself is here; this "
            "combination of filters is what is empty."
        )
    return payload


def _run(
    env: _Env,
    stat: Stat,
    resolution: Resolution,
    *,
    scope: str,
    first: int,
    last: int | None,
    position: str | None,
    team: str | None,
    active_only: bool,
    qualification: ResolvedQualification,
    scoring: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """The one query every board runs: group, value, qualify, rank, page."""
    loader = env.loader
    table = resolution.table
    columns = env.columns(table)
    has_players = env.have("players")

    player_column = resolution.player_column

    where = [f't."{player_column}" IS NOT NULL', "t.season >= ?"]
    params: list[Any] = [first]
    if last is not None:
        where.append("t.season <= ?")
        params.append(last)
    if "season_type" in columns:
        where.append("t.season_type = ?")
        params.append(SEASON_TYPE)
    if stat.role is not None:
        where.append("t.role = ?")
        params.append(stat.role)
    if stat.source == "ngs_passing" and "week" in columns:
        # Next Gen Stats ship a season-total row beside the weekly ones. Pooling the
        # weeks and then adding the season row would count every attempt twice, so
        # the aggregate is built from the weekly rows alone.
        where.append("t.week > 0")

    team_column = first_present(columns, ("team", "team_abbr", "recent_team"))
    if team and team_column:
        where.append(f't."{team_column}" = ?')
        params.append(team.upper())

    position_columns = [c for c in ("position", "position_group") if c in columns]
    if position:
        wanted = position.strip().upper()
        if position_columns:
            where.append(
                "(" + " OR ".join(f'upper(t."{c}") = ?' for c in position_columns) + ")"
            )
            params.extend([wanted] * len(position_columns))
        else:
            where.append("(upper(p.position) = ? OR upper(p.position_group) = ?)")
            params.extend([wanted, wanted])

    if active_only:
        where.append("p.last_season >= ?")
        params.append(env.newest_player_season())

    # `players` is joined only when a *filter* needs it. The name and position it
    # would otherwise supply are fetched for the page afterwards instead: joining
    # 24,826 player rows against 760,000 weekly ones to label twenty-five of them is
    # work the answer does not need.
    needs_players = has_players and (active_only or (bool(position) and not position_columns))
    join = f'LEFT JOIN players p ON p.gsis_id = t."{player_column}"' if needs_players else ""

    game_select = "any_value(t.game_id) AS game_id" if "game_id" in columns else "NULL AS game_id"

    name_column = first_present(columns, ("player_display_name", "player_name"))
    name_expr = f'any_value(t."{name_column}")' if name_column else "NULL"
    position_expr = f'any_value(t."{position_columns[0]}")' if position_columns else "NULL"

    reception_points = SCORING_FORMATS[scoring] if _is_fantasy(stat) else None
    receptions_column = "receptions" if "receptions" in columns else None
    numerator_sql, denominator_sql = _value_parts(
        stat, resolution,
        reception_points=reception_points,
        receptions_column=receptions_column,
    )

    group: list[str] = [f't."{player_column}"']
    select: list[str] = [f't."{player_column}" AS pid']
    if scope in ("season", "game"):
        group.append("t.season")
        select.append("t.season AS season")
    if scope == "game":
        group.append("t.week")
        select.append("t.week AS week")
        if team_column:
            group.append(f't."{team_column}"')
            select.append(f't."{team_column}" AS team')
        else:
            select.append("NULL AS team")
        opponent_column = first_present(columns, ("opponent_team", "opponent"))
        if opponent_column:
            group.append(f't."{opponent_column}"')
            select.append(f't."{opponent_column}" AS opponent')
        else:
            select.append("NULL AS opponent")
    else:
        team_reference = f't."{team_column}"' if team_column else None
        select.append(
            f"{_team_list_sql(team_reference)} AS team" if team_reference else "NULL AS team"
        )
        select.append("NULL AS opponent")

    select.extend([game_select, f"{name_expr} AS player", f"{position_expr} AS position"])
    if scope == "career":
        # Only the career line spans seasons. `count(DISTINCT ...)` is the most
        # expensive aggregate in this query and a season or game row would only be
        # using it to recount the one season it already knows it is.
        select.extend([
            "count(DISTINCT t.season) AS seasons",
            "min(t.season) AS first_season",
            "max(t.season) AS last_season",
        ])
    select.extend([f"{numerator_sql} AS n", f"{denominator_sql} AS d"])

    # Not at game scope: one game is one game, and summing a column of ones over
    # 760,000 rows to rediscover that is the most expensive way to print a 1.
    games_column = None if scope == "game" else first_present(columns, ("games",))
    select.append(f"{_sum(games_column)} AS games" if games_column else "NULL AS games")

    threshold_sql = _threshold_sql(qualification, scope)
    select.append(
        f"{_sum(qualification.column)} AS q"
        if qualification.applied and qualification.column else "NULL AS q"
    )

    support_ids = [sid for sid, _column, _label in resolution.support]
    for sid, column, _label in resolution.support:
        select.append(f'{_sum(column)} AS "sup_{sid}"')

    keep = ["value IS NOT NULL"]
    if stat.kind != "rate" and not resolution.denominator:
        keep.append("value <> 0")
    if threshold_sql:
        keep.append(f"q >= {threshold_sql}")

    direction = "DESC" if stat.higher_is_better else "ASC"
    cte = f"""
    WITH base AS (
        SELECT {', '.join(select)}
        FROM {table} t
        {join}
        WHERE {' AND '.join(where)}
        GROUP BY {', '.join(group)}
    ),
    valued AS (
        SELECT *, round(
            CASE WHEN d IS NULL THEN n
                 WHEN d = 0 THEN NULL
                 ELSE n / d * {stat.scale} END, {stat.decimals}) AS value
        FROM base
    ),
    kept AS (SELECT * FROM valued WHERE {' AND '.join(keep)})
    """
    # `through` is how many players are at this value or above it: a RANGE frame
    # spans the whole peer group, so the count of players tied here is
    # `through - rank + 1`. Written this way rather than as
    # `count(*) OVER (PARTITION BY value)` because it shares the sort `rank()`
    # already needs — measured on a 760,000-row weekly table, 645 ms as a partition
    # and 401 ms as a frame, for the same two numbers.
    page_sql = cte + f"""
    , ranked AS (
        SELECT *,
               rank() OVER (ORDER BY value {direction}) AS rnk,
               count(*) OVER (
                   ORDER BY value {direction}
                   RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS through,
               count(*) OVER () AS total
        FROM kept
    )
    SELECT *, through - rnk + 1 AS tied_count FROM ranked
    ORDER BY rnk, player NULLS LAST, pid
    LIMIT ? OFFSET ?
    """
    cursor = loader.cursor()
    result = cursor.execute(page_sql, [*params, page_size, (page - 1) * page_size])
    names = [description[0] for description in result.description]
    fetched = result.fetchall()

    if not fetched:
        # A page past the end still has to report the real total, or "page 40 of 3"
        # reads as an empty board rather than a request off the end of a full one.
        row = loader.cursor().execute(cte + " SELECT count(*) FROM kept", params).fetchone()
        return [], int(row[0]) if row and row[0] is not None else 0

    rows = []
    total = 0
    for raw in fetched:
        record = dict(zip(names, raw))
        total = int(record["total"])
        rows.append(_row(stat, record, scope, support_ids, resolution))
    _attach_identity(env, rows)
    if scope == "game":
        _attach_game_ids(env, rows)
    return rows, total


def _attach_identity(env: _Env, rows: list[dict[str, Any]]) -> None:
    """Give the page's rows the canonical name, and a position if the row has none.

    Names come from `players` so a leaderboard spells a player the way the rest of
    the site spells him. Doing it here rather than as a join means it runs against
    the page's twenty-five ids instead of against every row the board grouped.
    """
    if not rows or not env.have("players"):
        return
    columns = env.columns("players")
    if "gsis_id" not in columns:
        return
    ids = sorted({row["gsis_id"] for row in rows if row.get("gsis_id")})
    if not ids:
        return
    select = [
        "gsis_id",
        "display_name" if "display_name" in columns else "NULL",
        "position" if "position" in columns else "NULL",
    ]
    found = {
        gsis_id: (name, position)
        for gsis_id, name, position in env.loader.cursor().execute(
            f"SELECT {', '.join(select)} FROM players "
            f"WHERE gsis_id IN ({', '.join('?' * len(ids))})",
            ids,
        ).fetchall()
    }
    for row in rows:
        name, position = found.get(row["gsis_id"], (None, None))
        if name:
            row["player"] = name
        if position and not row.get("position"):
            row["position"] = position


def _attach_game_ids(env: _Env, rows: list[dict[str, Any]]) -> None:
    """Link each single-game row to the game it came from, for this page only.

    The weekly stat file carries no game id — nflverse keys it on season, week, team
    and opponent — so the link has to come from the schedule. Joining the schedule
    inside the aggregate puts it against every one of the ~760,000 weekly rows;
    doing it here runs one small query against the page's handful of weeks instead.
    Measured on a 760,000-row weekly table: 648 ms as a join, 90 ms as this.
    """
    wanted = {
        (row["season"], row["week"])
        for row in rows
        if row.get("game_id") is None
        and row.get("season") is not None
        and row.get("week") is not None
        and row.get("team")
        and row.get("opponent")
    }
    if not wanted or not env.have("games"):
        return
    columns = env.columns("games")
    if not {"game_id", "season", "week", "home_team", "away_team"} <= set(columns):
        return
    clause = " OR ".join("(season = ? AND week = ?)" for _ in wanted)
    params = [value for pair in sorted(wanted) for value in pair]
    found = env.loader.cursor().execute(
        f"SELECT season, week, home_team, away_team, game_id FROM games WHERE {clause}",
        params,
    ).fetchall()
    # Keyed on the unordered pair: the stat file says who the opponent was, not who
    # was at home, and `game_id` embeds the codes the clubs played under at the time
    # (SPEC 0.1b) so it cannot be rebuilt from the canonical ones.
    lookup = {
        (season, week, frozenset((home, away))): game_id
        for season, week, home, away, game_id in found
    }
    for row in rows:
        if row.get("game_id") is not None:
            continue
        game_id = lookup.get(
            (row.get("season"), row.get("week"), frozenset((row.get("team"), row.get("opponent"))))
        )
        if game_id:
            row["game_id"] = game_id
            row["game_href"] = f"/games/{game_id}"


def _row(
    stat: Stat,
    record: dict[str, Any],
    scope: str,
    support_ids: Sequence[str],
    resolution: Resolution,
) -> dict[str, Any]:
    pid = record["pid"]
    row: dict[str, Any] = {
        "rank": int(record["rnk"]),
        "tied": int(record["tied_count"]) > 1,
        "tied_count": int(record["tied_count"]),
        "gsis_id": pid,
        "href": f"/players/{pid}",
        "player": record.get("player") or pid,
        "position": record.get("position"),
        "team": record.get("team"),
        "value": _num(record["value"]),
    }
    if scope == "career":
        # Only the career line spans seasons, so only it carries a span. On a season
        # or game row these three would restate the row's own season and read as
        # three more facts than there are.
        row["seasons"] = int(record["seasons"]) if record.get("seasons") is not None else None
        row["first_season"] = record.get("first_season")
        row["last_season"] = record.get("last_season")
    if record.get("games") is not None:
        row["games"] = _num(record["games"])
    if scope in ("season", "game"):
        row["season"] = record.get("season")
    if scope == "game":
        row["week"] = record.get("week")
        if record.get("opponent"):
            row["opponent"] = record["opponent"]
        if record.get("game_id"):
            row["game_id"] = record["game_id"]
            row["game_href"] = f"/games/{record['game_id']}"
    support = {
        sid: _num(record.get(f"sup_{sid}"))
        for sid in support_ids
        if record.get(f"sup_{sid}") is not None
    }
    if stat.kind == "rate":
        # The two numbers the rate was made of, so a reader can check it instead of
        # trusting it: "312 of 480", not "65.0%" standing alone. Guarded by the same
        # conditions as `_support_columns`, so no row carries a number the table has
        # no header for — the derived EPA boards already show their denominator as
        # `plays` and would otherwise show it twice under two names.
        if stat.weight is None and resolution.numerator and record.get("n") is not None:
            support.setdefault("numerator", _num(record["n"]))
        if resolution.denominator and record.get("d") is not None:
            support.setdefault("denominator", _num(record["d"]))
    if support:
        row["support"] = support
    return row
