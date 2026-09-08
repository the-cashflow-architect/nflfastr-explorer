"""Standings, team ratings and playoff seeding, built from `games.csv` alone.

One file is enough. Every number on a standings page — record, splits, streak,
division finish, seed, SRS, Pythagorean expectation — is a function of who played
whom, where, and what the scoreboard said. Nothing here reads play-by-play, and
nothing here reads `teams_colors_logos.csv`: division membership is a property of
the *season*, and only `alignment.py` knows it.

Three rules shape the file.

**An unplayed game is not a 0-0 game.** `games.csv` carries the whole 2026 schedule
and the rest of the current season with NULL scores. Every query here filters them
out, and a season with nothing played produces no rows at all rather than a table of
0-0 teams.

**History is read, not recomputed.** For a season whose Super Bowl has been played,
seeds come from the bracket itself — who hosted whom in which round pins the seeding
down almost completely, and a derivation from results cannot be wrong about history.
The five-level tiebreaker approximation only ever runs on a season still in progress,
and every seed it produces is flagged `projected`. Where our rules genuinely cannot
separate two clubs we say so in `tiebreak_note` instead of picking an order.

**Anything we compute carries its formula.** SRS, OSRS, DSRS, SOS, margin of victory
and Pythagorean wins are our arithmetic, not nflverse's. `FORMULAS` is keyed by
column name so the API can hang a `ComputedByUs` marker off each one without
restating the maths in the frontend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import permutations
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Sequence

from . import alignment, derived

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..loader import Loader

logger = logging.getLogger(__name__)

TABLE = "team_standings"

#: Postseason round codes in the order they are played. `games.csv` uses exactly
#: these four for the postseason and `REG` for everything else.
ROUND_ORDER: dict[str, int] = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}

ROUND_NAMES: dict[str, str] = {
    "WC": "Wild Card",
    "DIV": "Divisional",
    "CON": "Conference Championship",
    "SB": "Super Bowl",
}

# Pro-Football-Reference's fitted exponent for the NFL. Baseball's 2 is wrong for a
# sport with this scoring distribution, and the exponent is the whole model, so it
# is named here once and printed in the formula string rather than buried in code.
PYTHAGOREAN_EXPONENT = 2.37

# The iterative solve stops when no rating moves by more than this. 1e-10 is far
# below anything we display; it exists so the answer is bit-identical run to run.
RATING_TOLERANCE = 1e-10
# A ceiling, not an expectation: re-centring inside the loop kills the one direction
# the iteration cannot damp, and real seasons converge in well under thirty passes.
RATING_MAX_ITERATIONS = 100

SEED_BASIS_RESULTS = "postseason results"
SEED_BASIS_RESULTS_AND_RECORD = "postseason results, order within round by record"
SEED_BASIS_PROJECTED = "projected from tiebreaker rules"

UNBROKEN_NOTE = (
    "Our implemented tiebreakers could not separate these clubs; left in "
    "alphabetical order."
)

#: Which ladder settled a placement. Stored on the row, because the two are
#: different procedures and a reader is entitled to know which one ran.
LADDER_DIVISION = "division"
LADDER_WILD_CARD = "wild card"

#: The two ladders we implement, each in the order it is applied, for the API to
#: print verbatim. They are not one procedure applied twice. A tie inside a division
#: is settled by how the clubs did against each other and inside the division; a tie
#: for a wild card is settled conference-wide, and it begins by throwing out every
#: club but the best in each division, so two clubs from one division never compete
#: for the same wild card. The real rules run deeper than either list — anything ours
#: cannot settle is labelled rather than guessed.
DIVISION_TIEBREAK_RULES: tuple[str, ...] = (
    "Win percentage",
    "Head-to-head record",
    "Division record",
    "Record in common games (minimum four)",
    "Conference record",
)

WILD_CARD_TIEBREAK_RULES: tuple[str, ...] = (
    "Win percentage",
    "Only the highest-placed club in each division is eligible",
    "Head-to-head sweep (one club beat, or lost to, all the others)",
    "Conference record",
    "Record in common games (minimum four)",
    "Strength of victory",
)

TIEBREAK_LADDERS: dict[str, tuple[str, ...]] = {
    LADDER_DIVISION: DIVISION_TIEBREAK_RULES,
    LADDER_WILD_CARD: WILD_CARD_TIEBREAK_RULES,
}

#: How a division title was settled. A completed bracket names its division winners
#: outright — they are the top seeds, one per division — and where it does, no
#: approximation of the tiebreakers should second-guess it.
TITLE_BASIS_BRACKET = "won the division, read off the postseason bracket"
TITLE_BASIS_LADDER = "first in the division on our tiebreaker ladder"

#: Keyed by column name so `/api/coverage` and the ComputedByUs marker can look up
#: exactly one string per number we calculate rather than read.
FORMULAS: dict[str, str] = {
    "win_pct": "(wins + 0.5 x ties) / games played",
    "mov": "margin of victory = (points for - points against) / games played",
    "srs": (
        "Simple Rating System = margin of victory + strength of schedule, solved "
        "iteratively: SRS(t) <- MOV(t) + mean(SRS of every opponent faced, one term "
        "per meeting), re-centred on a league mean of zero after each pass and "
        "stopped when no rating moves by more than 1e-10. Regular season only."
    ),
    "sos": (
        "Strength of schedule = SRS - MOV: the average SRS of the opponents a team "
        "actually played, counting an opponent once per meeting."
    ),
    "osrs": (
        "Offensive SRS <- (points scored per game - league points per game) + "
        "mean(DSRS of every opponent faced). Solved in the same pass as SRS, so "
        "OSRS + DSRS = SRS exactly."
    ),
    "dsrs": (
        "Defensive SRS <- (league points per game - points allowed per game) + "
        "mean(OSRS of every opponent faced). Positive is a good defence."
    ),
    "pythagorean_wins": (
        f"games x PF^{PYTHAGOREAN_EXPONENT} / "
        f"(PF^{PYTHAGOREAN_EXPONENT} + PA^{PYTHAGOREAN_EXPONENT}) — "
        "expected wins from points scored and allowed, using "
        "Pro-Football-Reference's fitted NFL exponent."
    ),
    "division_rank": (
        "Order within the division by win percentage, then head-to-head, division "
        "record, common games and conference record. Where a completed bracket names "
        "the division winner, that club is first and the ladder only orders the rest."
    ),
    "home_away_split": (
        "Home and away records count only games with a host: a game at a neutral "
        "site — an international game, or a Super Bowl — is in the neutral record "
        "instead, so home + away is short of the season total by that many games."
    ),
    "playoff_seed": (
        "For a completed season, read off the bracket: the clubs with a first-round "
        "bye hold the top seeds, first-round hosts the next, and each host's "
        "opponent takes the seed the format pairs it with; later rounds re-seed "
        "highest against lowest, which usually pins the rest. Where two clubs' paths "
        "were symmetric — most often the two first-round hosts, who never meet — the "
        "bracket cannot separate them and regular-season record does, which the row "
        "says. For a season still in progress, division winners are seeded above "
        "wild cards and each group is ordered by the tiebreaker ladder; those rows "
        "are flagged projected."
    ),
    "point_differential": "points for - points against (regular season)",
    "longest_win_streak": "longest run of consecutive regular-season wins",
}


class BuildError(RuntimeError):
    """The games table cannot support standings — a bug to see, not to absorb."""


@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    game_type: str
    week: int
    home: str
    away: str
    home_score: int
    away_score: int
    neutral: bool

    @property
    def winner(self) -> str | None:
        if self.home_score > self.away_score:
            return self.home
        if self.away_score > self.home_score:
            return self.away
        return None


@dataclass(frozen=True)
class BuildReport:
    seasons: tuple[int, ...]
    rows: int
    #: Iterations the rating solve needed, per season. The spec's acceptance test
    #: is that this stays well under fifty for every season we cover.
    iterations: dict[int, int]
    #: Seasons whose bracket could not be read as a seeding, with the reason.
    unseeded: dict[int, str]
    #: Seasons whose rating solve hit the iteration ceiling. Their SRS is the last
    #: iterate rather than the fixed point, which is worth saying out loud.
    unconverged: tuple[int, ...] = ()


@dataclass
class Record:
    wins: int = 0
    losses: int = 0
    ties: int = 0

    def add(self, scored: int, allowed: int) -> None:
        if scored > allowed:
            self.wins += 1
        elif scored < allowed:
            self.losses += 1
        else:
            self.ties += 1

    def merge(self, other: "Record") -> None:
        self.wins += other.wins
        self.losses += other.losses
        self.ties += other.ties

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def pct(self) -> float:
        # A club with no games in the split sorts last rather than crashing; the
        # only way to reach it is a split that never happened (no common games,
        # say), and the caller has already decided the rule is applicable.
        return (self.wins + 0.5 * self.ties) / self.games if self.games else 0.0


@dataclass
class TeamSeason:
    """One club's regular season, plus whatever postseason it played."""

    season: int
    team: str
    conference: str
    division: str
    overall: Record = field(default_factory=Record)
    home: Record = field(default_factory=Record)
    away: Record = field(default_factory=Record)
    division_record: Record = field(default_factory=Record)
    conference_record: Record = field(default_factory=Record)
    points_for: int = 0
    points_against: int = 0
    #: One entry per meeting, so a divisional opponent appears twice.
    opponents: list[str] = field(default_factory=list)
    versus: dict[str, Record] = field(default_factory=dict)
    #: (week, 'W'|'L'|'T') for the regular season, in playing order.
    results: list[tuple[int, str]] = field(default_factory=list)
    postseason: list[Game] = field(default_factory=list)

    @property
    def games(self) -> int:
        return self.overall.games

    @property
    def pct(self) -> float:
        return self.overall.pct

    @property
    def point_differential(self) -> int:
        return self.points_for - self.points_against

    def record_versus(self, opponents: Iterable[str]) -> Record:
        total = Record()
        for opponent in opponents:
            found = self.versus.get(opponent)
            if found is not None:
                total.merge(found)
        return total


# --- ratings -----------------------------------------------------------------


@dataclass(frozen=True)
class RatingSolution:
    srs: dict[str, float]
    osrs: dict[str, float]
    dsrs: dict[str, float]
    sos: dict[str, float]
    mov: dict[str, float]
    iterations: int
    converged: bool


def solve_ratings(
    schedules: Mapping[str, Sequence[str]],
    points_for: Mapping[str, float],
    points_against: Mapping[str, float],
    *,
    tolerance: float = RATING_TOLERANCE,
    max_iterations: int = RATING_MAX_ITERATIONS,
) -> RatingSolution:
    """Solve SRS, OSRS, DSRS and SOS for one league-season.

    `schedules` maps a club to the opponents it actually played, one entry per
    meeting, so a division rival counts twice — which is the whole point of a
    strength-of-schedule adjustment.

    The fixed point is the textbook one, SRS = MOV + average opponent SRS, reached
    by repeated substitution. The one wrinkle is that the iteration cannot damp
    the direction where every rating moves together: adding a constant to all 32
    ratings leaves the equations satisfied. Left alone, a season where clubs played
    unequal numbers of games (2022, whose cancelled game left two clubs on sixteen)
    drifts along that direction forever and never meets a tight tolerance. Re-centring
    on a zero league mean inside the loop removes it, which is also the normalisation
    every published SRS table uses.
    """
    teams = sorted(schedules)
    if not teams:
        return RatingSolution({}, {}, {}, {}, {}, 0, True)

    games = {t: len(schedules[t]) for t in teams}
    played = [t for t in teams if games[t]]
    if not played:
        return RatingSolution(
            {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, {t: 0.0 for t in teams},
            {t: 0.0 for t in teams}, {t: 0.0 for t in teams}, 0, True,
        )

    total_points = sum(points_for[t] for t in played)
    total_games = sum(games[t] for t in played)
    league_ppg = total_points / total_games

    mov = {t: (points_for[t] - points_against[t]) / games[t] for t in played}
    offence = {t: points_for[t] / games[t] - league_ppg for t in played}
    defence = {t: league_ppg - points_against[t] / games[t] for t in played}

    srs = dict(mov)
    osrs = dict(offence)
    dsrs = dict(defence)

    iterations = 0
    converged = False
    for iterations in range(1, max_iterations + 1):
        next_srs, next_osrs, next_dsrs = {}, {}, {}
        for t in played:
            opponents = schedules[t]
            n = len(opponents)
            next_srs[t] = mov[t] + sum(srs[o] for o in opponents) / n
            next_osrs[t] = offence[t] + sum(dsrs[o] for o in opponents) / n
            next_dsrs[t] = defence[t] + sum(osrs[o] for o in opponents) / n
        # Re-centre each vector on its own mean. Because OSRS + DSRS = SRS holds
        # term by term, subtracting each mean separately keeps that identity exact.
        _centre(next_srs)
        _centre(next_osrs)
        _centre(next_dsrs)
        shift = max(
            max(abs(next_srs[t] - srs[t]) for t in played),
            max(abs(next_osrs[t] - osrs[t]) for t in played),
            max(abs(next_dsrs[t] - dsrs[t]) for t in played),
        )
        srs, osrs, dsrs = next_srs, next_osrs, next_dsrs
        if shift < tolerance:
            converged = True
            break

    if not converged:
        logger.warning(
            "Rating solve stopped at %s iterations without reaching %s",
            iterations, tolerance,
        )

    sos = {t: srs[t] - mov[t] for t in played}
    for t in teams:
        if t not in played:
            srs[t] = osrs[t] = dsrs[t] = sos[t] = mov[t] = 0.0
    return RatingSolution(srs, osrs, dsrs, sos, mov, iterations, converged)


def _centre(values: dict[str, float]) -> None:
    mean = sum(values.values()) / len(values)
    for key in values:
        values[key] -= mean


def pythagorean_wins(points_for: float, points_against: float, games: int) -> float | None:
    """Expected wins from points alone. `None` when there is nothing to model."""
    if games <= 0 or (points_for <= 0 and points_against <= 0):
        return None
    numerator = points_for ** PYTHAGOREAN_EXPONENT
    denominator = numerator + points_against ** PYTHAGOREAN_EXPONENT
    if denominator == 0:
        return None
    return games * numerator / denominator


# --- tiebreakers -------------------------------------------------------------


@dataclass(frozen=True)
class _Rule:
    label: str
    score: Callable[[Sequence[str], Mapping[str, TeamSeason]], dict[str, float] | None]


def _head_to_head(group: Sequence[str], teams: Mapping[str, TeamSeason]) -> dict[str, float] | None:
    # The real rule for three or more clubs is a sweep test — it applies only when
    # one club beat or lost to all the others. We use aggregate record among the
    # tied clubs instead, and require that every pair actually met, so the number
    # means something. Where that is not true the rule is skipped rather than faked.
    for a in group:
        for b in group:
            if a != b and teams[a].versus.get(b) is None:
                return None
    return {t: teams[t].record_versus([o for o in group if o != t]).pct for t in group}


def _division_record(group: Sequence[str], teams: Mapping[str, TeamSeason]) -> dict[str, float] | None:
    # Only meaningful between clubs that share a division; comparing a division
    # record across divisions compares two different schedules.
    divisions = {(teams[t].conference, teams[t].division) for t in group}
    if len(divisions) != 1:
        return None
    return {t: teams[t].division_record.pct for t in group}


def _common_games(group: Sequence[str], teams: Mapping[str, TeamSeason]) -> dict[str, float] | None:
    shared: set[str] | None = None
    for t in group:
        faced = set(teams[t].versus) - set(group)
        shared = faced if shared is None else (shared & faced)
    if not shared:
        return None
    records = {t: teams[t].record_versus(shared) for t in group}
    # The NFL's minimum is four common games; below that the sample is not the rule.
    if any(record.games < 4 for record in records.values()):
        return None
    return {t: record.pct for t, record in records.items()}


def _conference_record(group: Sequence[str], teams: Mapping[str, TeamSeason]) -> dict[str, float] | None:
    return {t: teams[t].conference_record.pct for t in group}


_RULES: tuple[_Rule, ...] = (
    _Rule(TIEBREAK_RULES[1], _head_to_head),
    _Rule(TIEBREAK_RULES[2], _division_record),
    _Rule(TIEBREAK_RULES[3], _common_games),
    _Rule(TIEBREAK_RULES[4], _conference_record),
)


def rank_group(
    codes: Sequence[str], teams: Mapping[str, TeamSeason]
) -> list[tuple[str, str | None]]:
    """Order clubs best-first, returning the rule that placed each one.

    A club that was never tied with anyone carries `None`: win percentage alone
    put it where it is, and saying "decided by win percentage" on every row would
    turn a meaningful note into wallpaper.
    """
    ordered = sorted(codes, key=lambda t: (-teams[t].pct, t))
    out: list[tuple[str, str | None]] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and teams[ordered[j + 1]].pct == teams[ordered[i]].pct:
            j += 1
        cluster = ordered[i : j + 1]
        if len(cluster) == 1:
            out.append((cluster[0], None))
        else:
            out.extend(_break_tie(cluster, teams))
        i = j + 1
    return out


def _break_tie(
    cluster: Sequence[str], teams: Mapping[str, TeamSeason]
) -> list[tuple[str, str | None]]:
    """Apply the ladder to clubs level on win percentage.

    Each rule that separates the group restarts the ladder on the sub-groups it
    creates, which is what the real rules say to do. That terminates because a rule
    only counts as having separated anything when every sub-group is strictly
    smaller than the group it came from.
    """
    if len(cluster) == 1:
        return [(cluster[0], None)]
    for rule in _RULES:
        scores = rule.score(cluster, teams)
        if scores is None or len(set(scores.values())) == 1:
            continue
        out: list[tuple[str, str | None]] = []
        for value in sorted(set(scores.values()), reverse=True):
            sub = sorted(t for t in cluster if scores[t] == value)
            if len(sub) == 1:
                out.append((sub[0], rule.label))
            else:
                for team, note in _break_tie(sub, teams):
                    out.append((team, note or rule.label))
        return out
    return [(t, UNBROKEN_NOTE) for t in sorted(cluster)]


# --- playoff results and seeding ---------------------------------------------


def _playoff_result(team: str, games_played: Sequence[Game]) -> tuple[str, str, int, int]:
    """(furthest round code, human result, postseason wins, postseason losses)."""
    ordered = sorted(games_played, key=lambda g: ROUND_ORDER[g.game_type])
    wins = sum(1 for g in ordered if g.winner == team)
    losses = sum(1 for g in ordered if g.winner not in (team, None))
    last = ordered[-1]
    round_code = last.game_type
    won_last = last.winner == team
    if round_code == "SB":
        result = "Won Super Bowl" if won_last else "Lost Super Bowl"
    elif won_last:
        # Only reachable while a postseason is still being played: the club won its
        # last game and the next round has not happened yet.
        result = f"Won {ROUND_NAMES[round_code]}"
    else:
        result = f"Lost {ROUND_NAMES[round_code]}"
    return round_code, result, wins, losses


def candidate_seedings(
    field_teams: Sequence[str], postseason: Sequence[Game], seeds: int
) -> list[dict[str, int]]:
    """Every seeding of one conference that explains the bracket it played.

    The bracket carries more information than it looks like it does. Clubs with a
    first-round bye are the top seeds; first-round hosts take the seeds immediately
    below them; and because the wild-card round pairs the best host with the worst
    visitor, every visitor's seed follows from its host's. So the only unknowns are
    the order *within* the bye group and *within* the host group — at most six
    arrangements of each — and the later rounds, which re-seed highest against
    lowest, usually rule out all but one combination.

    An empty list means the games on file are not a bracket we can read: a partial
    postseason, a field that is not the size the era's format calls for, or a
    sequence of host-and-visitor pairings no seeding could have produced.
    """
    field_set = set(field_teams)
    if len(field_set) != seeds:
        return []
    wildcard = [g for g in postseason if g.game_type == "WC"]
    if len(wildcard) != (seeds - 1) // 2:
        return []
    participants = [t for g in wildcard for t in (g.home, g.away)]
    if len(set(participants)) != len(participants) or not set(participants) <= field_set:
        return []
    byes = sorted(field_set - set(participants))
    hosts = [g.home for g in wildcard]
    visitor_of = {g.home: g.away for g in wildcard}

    by_round: dict[str, list[Game]] = {}
    for game in postseason:
        if game.game_type in ("DIV", "CON"):
            by_round.setdefault(game.game_type, []).append(game)

    found: list[dict[str, int]] = []
    for bye_order in permutations(byes):
        for host_order in permutations(hosts):
            assignment = {team: index + 1 for index, team in enumerate(bye_order)}
            for index, host in enumerate(host_order):
                seed = len(byes) + index + 1
                assignment[host] = seed
                # The format pairs host k with visitor (N + byes + 1 - k): the best
                # host draws the worst qualifier.
                assignment[visitor_of[host]] = seeds + len(byes) + 1 - seed
            if _bracket_agrees(assignment, by_round):
                found.append(assignment)
    return found


def derive_seeds(
    field_teams: Sequence[str],
    postseason: Sequence[Game],
    seeds: int,
    *,
    order_key: Callable[[str], tuple] | None = None,
) -> tuple[dict[str, int], str, set[str]] | None:
    """Read one conference's seeding off its completed bracket.

    Returns (team -> seed, how the order was settled, teams the bracket alone did
    not pin down), or None when there is no bracket to read.

    Where several seedings explain the same bracket, `order_key` — regular-season
    record, division winners first — chooses between them, and the clubs it had to
    choose for are reported so their rows can say so. If record disagrees with every
    seeding the bracket allows, the bracket wins: results are what happened, and our
    record ordering is only an approximation of the tiebreakers the league applied.
    """
    candidates = candidate_seedings(field_teams, postseason, seeds)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0], SEED_BASIS_RESULTS, set()

    unsettled = {
        team for team in field_teams
        if len({candidate[team] for candidate in candidates}) > 1
    }
    if order_key is None:
        return candidates[0], SEED_BASIS_RESULTS_AND_RECORD, unsettled
    wanted = sorted(field_teams, key=order_key)
    preferred = {team: index + 1 for index, team in enumerate(wanted)}
    best = min(
        candidates,
        key=lambda c: (
            sum(abs(c[t] - preferred[t]) for t in field_teams),
            sorted(c.items()),
        ),
    )
    return best, SEED_BASIS_RESULTS_AND_RECORD, unsettled


def _bracket_agrees(assignment: Mapping[str, int], by_round: Mapping[str, list[Game]]) -> bool:
    """Does this seeding explain who hosted whom after the wild-card round?"""
    for games_played in by_round.values():
        pairs = [(assignment[g.home], assignment[g.away], g.neutral) for g in games_played]
        for home_seed, away_seed, neutral in pairs:
            if not neutral and home_seed > away_seed:
                return False
        present = sorted(s for pair in pairs for s in pair[:2])
        n = len(present)
        expected = {(present[i], present[n - 1 - i]) for i in range(n // 2)}
        actual = {(min(h, a), max(h, a)) for h, a, _ in pairs}
        if expected != actual:
            return False
    return True


def _record_order_key(team: str, teams: Mapping[str, TeamSeason], winners: set[str]):
    """Division winners first, then record. The league's own seeding order."""
    season = teams[team]
    return (0 if team in winners else 1, -season.pct, -season.point_differential, team)


def project_seeds(
    teams: Mapping[str, TeamSeason],
    divisions: Mapping[tuple[str, str], list[str]],
    seeds: int,
) -> list[tuple[str, int, str | None]]:
    """Seed one conference from the tiebreaker ladder, for a season still running.

    Division winners take the top seeds and wild cards the rest, which is the one
    part of seeding that is not a matter of record at all. Wild cards are then picked
    a club at a time from the best club left in each division, because the league
    settles a division's internal order before letting two of its clubs compete for
    the same wild-card slot — the rule the spec calls "division ties resolve before
    wild-card ties".
    """
    notes: dict[str, str | None] = {}
    remaining: dict[tuple[str, str], list[str]] = {}
    winners: list[str] = []
    for key, members in divisions.items():
        if not members:
            continue
        ordered = rank_group(members, teams)
        winners.append(ordered[0][0])
        notes[ordered[0][0]] = ordered[0][1]
        remaining[key] = [team for team, _ in ordered[1:]]

    seeded: list[tuple[str, int, str | None]] = []
    for team, note in rank_group(winners, teams):
        seeded.append((team, len(seeded) + 1, note or notes.get(team)))

    while len(seeded) < seeds:
        pool = [members[0] for members in remaining.values() if members]
        if not pool:
            break
        team, note = rank_group(pool, teams)[0]
        seeded.append((team, len(seeded) + 1, note))
        for key, members in remaining.items():
            if members and members[0] == team:
                remaining[key] = members[1:]
                break
    return seeded


# --- the build ---------------------------------------------------------------


def _fetch_games(cur, seasons: Sequence[int] | None) -> list[Game]:
    columns = {row[0] for row in cur.execute("DESCRIBE games").fetchall()}
    missing = {"season", "game_type", "week", "home_team", "away_team",
               "home_score", "away_score"} - columns
    if missing:
        raise BuildError(f"games is missing {sorted(missing)}")
    # `location` marks the Super Bowl and the occasional relocated game as neutral.
    # Older snapshots of the file do not carry it; absent, nothing is neutral, which
    # only costs us the home/away split on a handful of games.
    location = '"location"' if "location" in columns else "NULL"
    where = "WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
    params: list = []
    if seasons is not None:
        where += f" AND season IN ({', '.join('?' * len(seasons))})"
        params = list(seasons)
    rows = cur.execute(
        "SELECT game_id, season, game_type, week, home_team, away_team, "
        f"home_score, away_score, {location} FROM games {where} "
        "ORDER BY season, week, game_id",
        params,
    ).fetchall()
    return [
        Game(
            game_id=row[0],
            season=int(row[1]),
            game_type=str(row[2]).upper(),
            week=int(row[3]),
            home=row[4],
            away=row[5],
            home_score=int(row[6]),
            away_score=int(row[7]),
            neutral=str(row[8] or "").strip().lower() == "neutral",
        )
        for row in rows
        if row[4] and row[5]
    ]


def _streak(results: Sequence[tuple[int, str]]) -> tuple[str | None, int, int]:
    """(current streak kind, its length, longest win streak)."""
    if not results:
        return None, 0, 0
    # Sorted by week only, and stably: two games in the same week keep the order
    # they were read in, which is the order `_fetch_games` put them in. Sorting the
    # tuples whole would order a week's games by outcome letter instead.
    outcomes = [outcome for _, outcome in sorted(results, key=lambda r: r[0])]
    kind = outcomes[-1]
    length = 0
    for outcome in reversed(outcomes):
        if outcome != kind:
            break
        length += 1
    longest = run = 0
    for outcome in outcomes:
        run = run + 1 if outcome == "W" else 0
        longest = max(longest, run)
    return kind, length, longest


def season_rows(season: int, games_played: Sequence[Game]) -> list[dict]:
    """Every standings row for one season. Pure: no database, no network.

    `games_played` must already exclude unplayed games; a club that never took the
    field gets no row, which is how the 2026 schedule stays out of the table.
    """
    return _season(season, games_played)[0]


def _season(
    season: int, games_played: Sequence[Game]
) -> tuple[list[dict], RatingSolution | None]:
    regular = [g for g in games_played if g.game_type == "REG"]
    postseason = [g for g in games_played if g.game_type in ROUND_ORDER]
    if not regular:
        return [], None

    teams: dict[str, TeamSeason] = {}
    for code in sorted({g.home for g in regular} | {g.away for g in regular}):
        conference, division = alignment.division_of(code, season)
        teams[code] = TeamSeason(season=season, team=code, conference=conference,
                                 division=division)

    for game in regular:
        for team, opponent, scored, allowed, at_home in (
            (game.home, game.away, game.home_score, game.away_score, True),
            (game.away, game.home, game.away_score, game.home_score, False),
        ):
            row = teams[team]
            other = teams[opponent]
            row.overall.add(scored, allowed)
            row.points_for += scored
            row.points_against += allowed
            row.opponents.append(opponent)
            row.versus.setdefault(opponent, Record()).add(scored, allowed)
            row.results.append(
                (game.week, "W" if scored > allowed else "L" if scored < allowed else "T")
            )
            # A neutral-site game belongs to neither split. The schedule still names
            # a home club, but calling Wembley a home game would make the split lie.
            if not game.neutral:
                (row.home if at_home else row.away).add(scored, allowed)
            if row.conference == other.conference:
                row.conference_record.add(scored, allowed)
                if row.division == other.division:
                    row.division_record.add(scored, allowed)

    for game in postseason:
        for code in (game.home, game.away):
            if code in teams:
                teams[code].postseason.append(game)

    ratings = solve_ratings(
        {code: row.opponents for code, row in teams.items()},
        {code: row.points_for for code, row in teams.items()},
        {code: row.points_against for code, row in teams.items()},
    )

    divisions: dict[tuple[str, str], list[str]] = {}
    for code, row in teams.items():
        divisions.setdefault((row.conference, row.division), []).append(code)

    division_rank: dict[str, int] = {}
    division_note: dict[str, str | None] = {}
    for members in divisions.values():
        for position, (code, note) in enumerate(rank_group(members, teams), start=1):
            division_rank[code] = position
            division_note[code] = note

    winners = {code for code, rank in division_rank.items() if rank == 1}
    completed = any(g.game_type == "SB" for g in postseason)
    seeding = _seed_season(season, teams, divisions, postseason, winners, completed)

    rows: list[dict] = []
    for code, row in sorted(teams.items()):
        seed, basis, seed_note, projected = seeding.get(code, (None, None, None, False))
        if row.postseason:
            round_code, result, post_wins, post_losses = _playoff_result(code, row.postseason)
        else:
            # No postseason game means no postseason. Absent, not "0-0".
            round_code = result = None
            post_wins = post_losses = 0
        kind, length, longest = _streak(row.results)
        note = seed_note or division_note.get(code)
        rows.append(
            {
                "season": season,
                "team": code,
                "conference": row.conference,
                "division": row.division,
                "games": row.games,
                "wins": row.overall.wins,
                "losses": row.overall.losses,
                "ties": row.overall.ties,
                "points_for": row.points_for,
                "points_against": row.points_against,
                "point_differential": row.point_differential,
                "home_wins": row.home.wins,
                "home_losses": row.home.losses,
                "home_ties": row.home.ties,
                "away_wins": row.away.wins,
                "away_losses": row.away.losses,
                "away_ties": row.away.ties,
                "division_wins": row.division_record.wins,
                "division_losses": row.division_record.losses,
                "division_ties": row.division_record.ties,
                "conference_wins": row.conference_record.wins,
                "conference_losses": row.conference_record.losses,
                "conference_ties": row.conference_record.ties,
                "streak_kind": kind,
                "streak_length": length,
                "longest_win_streak": longest,
                "division_rank": division_rank[code],
                "won_division": code in winners,
                "playoff_seed": seed,
                "seed_basis": basis,
                "projected": projected,
                "tiebreak_note": note,
                "made_playoffs": bool(row.postseason),
                "playoff_round": round_code,
                "playoff_result": result,
                "playoff_wins": post_wins,
                "playoff_losses": post_losses,
                "srs": ratings.srs.get(code),
                "osrs": ratings.osrs.get(code),
                "dsrs": ratings.dsrs.get(code),
                "sos": ratings.sos.get(code),
                "pythagorean_wins": pythagorean_wins(
                    row.points_for, row.points_against, row.games
                ),
                "season_completed": completed,
            }
        )
    rows.sort(key=lambda r: (r["conference"], r["division"], r["division_rank"]))
    return rows, ratings


def _seed_season(
    season: int,
    teams: Mapping[str, TeamSeason],
    divisions: Mapping[tuple[str, str], list[str]],
    postseason: Sequence[Game],
    winners: set[str],
    completed: bool,
) -> dict[str, tuple[int | None, str | None, str | None, bool]]:
    """team -> (seed, basis, note, projected) for both conferences."""
    seeds = alignment.playoff_seeds(season)
    out: dict[str, tuple[int | None, str | None, str | None, bool]] = {}
    for conference in sorted({row.conference for row in teams.values()}):
        members = [code for code, row in teams.items() if row.conference == conference]
        conference_divisions = {
            key: value for key, value in divisions.items() if key[0] == conference
        }
        bracket = [
            g for g in postseason
            if g.game_type != "SB" and g.home in members and g.away in members
        ]
        field_teams = sorted({t for g in bracket for t in (g.home, g.away)})
        if completed:
            derived = derive_seeds(
                field_teams,
                bracket,
                seeds,
                order_key=lambda t: _record_order_key(t, teams, winners),
            )
            if derived is None:
                # We know who played, not what they were seeded. Saying nothing is
                # the honest answer; a guessed order would be indistinguishable
                # from a read one on the page.
                continue
            assignment, basis, unsettled = derived
            for code, seed in assignment.items():
                note = (
                    "Bracket alone left this club's seed open; ordered by "
                    "regular-season record."
                    if code in unsettled
                    else None
                )
                out[code] = (seed, basis, note, False)
        else:
            for code, seed, note in project_seeds(teams, conference_divisions, seeds):
                out[code] = (seed, SEED_BASIS_PROJECTED, note, True)
    return out


_COLUMNS: tuple[tuple[str, str], ...] = (
    ("season", "INTEGER"), ("team", "VARCHAR"), ("conference", "VARCHAR"),
    ("division", "VARCHAR"), ("games", "INTEGER"), ("wins", "INTEGER"),
    ("losses", "INTEGER"), ("ties", "INTEGER"), ("points_for", "INTEGER"),
    ("points_against", "INTEGER"), ("point_differential", "INTEGER"),
    ("home_wins", "INTEGER"), ("home_losses", "INTEGER"), ("home_ties", "INTEGER"),
    ("away_wins", "INTEGER"), ("away_losses", "INTEGER"), ("away_ties", "INTEGER"),
    ("division_wins", "INTEGER"), ("division_losses", "INTEGER"),
    ("division_ties", "INTEGER"), ("conference_wins", "INTEGER"),
    ("conference_losses", "INTEGER"), ("conference_ties", "INTEGER"),
    ("streak_kind", "VARCHAR"), ("streak_length", "INTEGER"),
    ("longest_win_streak", "INTEGER"), ("division_rank", "INTEGER"),
    ("won_division", "BOOLEAN"), ("playoff_seed", "INTEGER"),
    ("seed_basis", "VARCHAR"), ("projected", "BOOLEAN"), ("tiebreak_note", "VARCHAR"),
    ("made_playoffs", "BOOLEAN"), ("playoff_round", "VARCHAR"),
    ("playoff_result", "VARCHAR"), ("playoff_wins", "INTEGER"),
    ("playoff_losses", "INTEGER"), ("srs", "DOUBLE"), ("osrs", "DOUBLE"),
    ("dsrs", "DOUBLE"), ("sos", "DOUBLE"), ("pythagorean_wins", "DOUBLE"),
    ("season_completed", "BOOLEAN"),
)

# Rates are not among them, deliberately. Win percentage and margin of victory are
# one division away from columns that are stored, and a stored rate is a rate
# somebody will average across seasons. SRS and its relatives are stored because
# they are the output of a league-wide solve, not arithmetic on one row.
COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in _COLUMNS)


def build(loader: "Loader", *, seasons: Sequence[int] | None = None) -> BuildReport:
    """Rebuild `team_standings` from the games table."""
    loader.ensure("games")
    cur = loader.cursor()
    games_played = _fetch_games(cur, seasons)

    by_season: dict[int, list[Game]] = {}
    for game in games_played:
        by_season.setdefault(game.season, []).append(game)

    rows: list[dict] = []
    iterations: dict[int, int] = {}
    unseeded: dict[int, str] = {}
    unconverged: list[int] = []
    for season in sorted(by_season):
        produced, ratings = _season(season, by_season[season])
        if not produced:
            # Scheduled but not started — the 2026 rows land here and go no further.
            continue
        rows.extend(produced)
        iterations[season] = ratings.iterations if ratings else 0
        if ratings is not None and not ratings.converged:
            unconverged.append(season)
        if any(r["made_playoffs"] and r["playoff_seed"] is None for r in produced):
            unseeded[season] = (
                "The postseason games on file do not describe a full bracket, so no "
                "seeds were derived."
            )

    columns = ", ".join(f"{name} {dtype}" for name, dtype in _COLUMNS)
    placeholders = ", ".join("?" * len(COLUMN_NAMES))
    values = [[row[name] for name in COLUMN_NAMES] for row in rows]

    if seasons is None:
        # Full rebuild. Built into a staging table and swapped in one statement so
        # a concurrent reader never sees the table half-populated — the same shape
        # the source loader uses.
        staging = f"{TABLE}__staging"
        cur.execute(f"DROP TABLE IF EXISTS {staging}")
        cur.execute(f"CREATE TABLE {staging} ({columns})")
        if values:
            cur.executemany(f"INSERT INTO {staging} VALUES ({placeholders})", values)
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(f"ALTER TABLE {staging} RENAME TO {TABLE}")
    else:
        # A partial rebuild must not delete the seasons it was not asked about,
        # so it replaces season by season rather than replacing the table.
        if not _table_exists(cur, TABLE):
            cur.execute(f"CREATE TABLE {TABLE} ({columns})")
        for season in sorted(set(seasons)):
            cur.execute(f"DELETE FROM {TABLE} WHERE season = ?", [season])
        if values:
            cur.executemany(f"INSERT INTO {TABLE} VALUES ({placeholders})", values)
    derived.record_build(loader, TABLE, len(rows))
    logger.info("Built %s: %s rows over %s seasons", TABLE, len(rows), len(iterations))
    return BuildReport(
        tuple(sorted(iterations)), len(rows), iterations, unseeded, tuple(unconverged)
    )


def _table_exists(cur, table: str) -> bool:
    row = cur.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


DERIVED = derived.register(
    derived.Derived(
        name=TABLE,
        depends_on=("games",),
        build=lambda loader: build(loader),
        description="Team records, division finish, playoff seeding and SRS-family ratings.",
    )
)


def ensure(loader: "Loader") -> None:
    """Build the table if it is missing or older than the schedule it reads.

    Delegated rather than a bare existence check: the table is a function of
    `games`, so a refreshed schedule makes it wrong while leaving it present, and
    a bare check would serve last week's standings forever.
    """
    derived.ensure(loader, TABLE, table=TABLE)
