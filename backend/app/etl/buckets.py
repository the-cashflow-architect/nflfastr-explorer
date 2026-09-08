"""The sixteen situational buckets, as data.

A split is only useful if the same sixteen rows exist for every player in every
season since 1999, so the list is fixed here and nowhere else. Two rules keep it
honest:

**It is a list, not a cross-product.** "3rd and long in the red zone while
trailing" is four buckets deep and would multiply into thousands of rows per
player, most of them holding two plays. Sixteen flat buckets is one row set a
career query can SUM without a scan of the plays.

**Buckets overlap on purpose.** A play is in `down_3`, `dist_long`, `second_half`
and `trailing` at once; the numbers are not a partition and must never be added
together across buckets. Every play does land in at least one — `qtr` and
`score_differential` are populated on every row nflfastR publishes — which is what
makes "no bucket" a detectable bug rather than a silent hole.

Quarters were deliberately removed (SPEC section 3, correction 3): halves plus the
two-minute bucket carry the intent, and four more buckets per player-season is
real storage for a split nobody sorts by.

Roles are offence only. A defender has no `passer_player_id`, `rusher_player_id`
or `receiver_player_id`, so a defensive split built from these columns would be
empty rather than wrong — the Splits page hides itself instead.

**The passer role includes sacks.** A review claimed `passer_player_id` is NULL on
sacks — the raw-feed behaviour nflfastR added its own `passer_id` to work around.
Measured against the published files, it is not: of 1,297 sacks in 1999, 1,234 in
2005, 1,202 in 2006, 1,250 in 2015 and 1,392 in 2024, **none** has a NULL
`passer_player_id`, and the passer frame's sack total equals the season's sack
total exactly. So a quarterback's EPA per dropback already carries the plays that
hurt him most, and `sacks` / `sack_epa` are written alongside it so a reader can
see how much of the total is sacks rather than take it on trust.

What `passer_player_id` does drop is the **scramble**: 1,211 of 1,211 in 2024 and
984 of 986 in 1999 have no passer id. Those plays are not lost — they carry
`rusher_player_id` for the same quarterback, so a scramble is filed under his
Rushing row, which is where a run belongs. The one column that would credit both
under Passing is `passer_id`, and it is not in `sources.PBP_COLUMNS`; it also
carries 1,288 penalty-negated `no_play` rows in 2024, which are nobody's
production.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bucket:
    """One situation, as a key, a label and the SQL that selects its plays.

    The predicate is written against the play columns in `sources.PBP_COLUMNS`
    and must survive a NULL: `down = 1` is false for a kickoff rather than
    filing it under first down.
    """

    key: str
    label: str
    predicate: str


@dataclass(frozen=True)
class Role:
    """An offensive role, and the play columns that credit a player with it."""

    key: str
    label: str
    #: The gsis_id column that is non-NULL when the player filled this role.
    id_column: str
    #: Touchdowns credited to this role. A passer must not be credited with a
    #: pick-six, so this is never the play-level `touchdown` flag.
    touchdown_column: str
    #: The EPA column this role is charged with. `epa` is the play's; `qb_epa` is
    #: nflfastR's passer-credit variant of it.
    epa_column: str = "epa"


ROLES: tuple[Role, ...] = (
    # `qb_epa`, not `epa`: measured on the published files, the two are identical
    # on every passer play except a lost fumble — 62 plays worth +293.6 EPA in
    # 2024, 64 worth +288.5 in 1999 — where `epa` charges the quarterback for a
    # receiver coughing the ball up after the catch and `qb_epa` stops at the
    # catch. They agree to the last decimal on all 1,392 sacks in 2024, so this
    # is a fumble convention, not a way of hiding a sack.
    Role("passer", "Passing", "passer_player_id", "pass_touchdown", "qb_epa"),
    Role("rusher", "Rushing", "rusher_player_id", "rush_touchdown"),
    Role("receiver", "Receiving", "receiver_player_id", "pass_touchdown"),
)


BUCKETS: tuple[Bucket, ...] = (
    Bucket("down_1", "1st down", "down = 1"),
    Bucket("down_2", "2nd down", "down = 2"),
    Bucket("down_3", "3rd down", "down = 3"),
    Bucket("down_4", "4th down", "down = 4"),
    Bucket("dist_short", "Short (1-3 to go)", "ydstogo BETWEEN 1 AND 3"),
    Bucket("dist_medium", "Medium (4-7 to go)", "ydstogo BETWEEN 4 AND 7"),
    Bucket("dist_long", "Long (8+ to go)", "ydstogo >= 8"),
    Bucket("red_zone", "Red zone (inside 20)", "yardline_100 <= 20"),
    # Field position, not the rule: a true goal-to-go needs ydstogo = yardline_100.
    # SPEC section 3 defines this bucket as inside the 5, so the label says inside
    # the 5 rather than letting the key imply a down-and-distance test we do not run.
    Bucket("goal_to_go", "Goal to go (inside the 5)", "yardline_100 <= 5"),
    Bucket("first_half", "1st half", "qtr <= 2"),
    # Overtime is filed under the second half. There is no third half, and dropping
    # qtr 5 would quietly lose every overtime play from the only split that claims
    # to cover a whole game.
    Bucket("second_half", "2nd half", "qtr >= 3"),
    Bucket("two_minute", "Two-minute (either half)", "half_seconds_remaining <= 120"),
    # score_differential is posteam minus defteam, which is what these three mean
    # for an offensive role. They are not valid for a defensive one.
    Bucket("leading", "Leading", "score_differential > 0"),
    Bucket("tied", "Tied", "score_differential = 0"),
    Bucket("trailing", "Trailing", "score_differential < 0"),
    # The one bucket that needs a threshold rather than a rule of the game. We use
    # nflfastR's own win-probability field and the conventional 5%/95% bounds, and
    # we put the bounds in the label so the page states the definition instead of
    # asking the reader to trust the word "garbage". `wp` is the posteam's win
    # probability, so this is symmetric: blowouts count from both sidelines.
    Bucket("garbage_time", "Garbage time (win probability outside 5-95%)",
           "wp <= 0.05 OR wp >= 0.95"),
)

BUCKET_KEYS: tuple[str, ...] = tuple(b.key for b in BUCKETS)
BY_KEY: dict[str, Bucket] = {b.key: b for b in BUCKETS}
ROLE_KEYS: tuple[str, ...] = tuple(r.key for r in ROLES)
ROLES_BY_KEY: dict[str, Role] = {r.key: r for r in ROLES}


def bucket(key: str) -> Bucket:
    try:
        return BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown situational bucket {key!r}") from exc


def role(key: str) -> Role:
    try:
        return ROLES_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown role {key!r}") from exc


def any_bucket_sql() -> str:
    """A predicate that is true for a play in at least one bucket.

    Used by the ETL's own test to prove the sixteen cover the league: a play that
    matches none of them means a column we assumed was populated is not.
    """
    return " OR ".join(f"({b.predicate})" for b in BUCKETS)
