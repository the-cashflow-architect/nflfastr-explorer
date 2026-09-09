"""Tables we compute, and the rules for keeping them in step with the data.

A derived table is not like a source. A source is a file we fetched, and its load
log entry answers "is this current?" on its own. A derived table is a function of
several sources, so it goes stale silently the moment any of them is refreshed —
and nothing in the request path would ever notice, because the table exists and
returns rows.

Three problems this solves once, rather than three times:

* **Staleness.** Each table records when it was built and which sources it reads.
  A build newer than every input is current; anything else is rebuilt.
* **Races.** Two first requests both find the table missing and both run
  `CREATE OR REPLACE`. DuckDB answers the second with a catalog write-write
  conflict, and if it did not, a reader could observe a half-populated table.
  Building happens under a named lock, with the existence check repeated inside it.
* **Orchestration.** The build job should produce every derived table, not just
  the sources. Registering them here means `python -m app.build` picks up a new
  one without being edited.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..loader import Loader

logger = logging.getLogger(__name__)

DERIVED_LOG = "_derived_log"


@dataclass(frozen=True)
class Derived:
    name: str
    #: Source ids this table is computed from. Any of them being newer than the
    #: last build makes it stale.
    depends_on: tuple[str, ...]
    #: Does the work. Must be idempotent and must leave the table complete.
    build: Callable[["Loader"], None]
    description: str = ""
    #: The shape this builder currently produces, as a short string. Compared
    #: against the shape recorded at the last build.
    #:
    #: Without it, adding a column to a derived table leaves every existing
    #: database serving the old shape forever: the table is present, its inputs
    #: have not moved, so nothing is stale — and every query naming the new
    #: column fails at runtime with a binder error nobody sees in tests, because
    #: tests build their fixture from scratch every time. That is precisely how
    #: this was found: sixteen endpoints failed against a real database while
    #: 385 tests passed.
    schema: Callable[[], str] | None = None

    def fingerprint(self) -> str | None:
        return self.schema() if self.schema else None


_REGISTRY: dict[str, Derived] = {}


def register(derived: Derived) -> Derived:
    _REGISTRY[derived.name] = derived
    return derived


def all_derived() -> tuple[Derived, ...]:
    return tuple(_REGISTRY.values())


def get(name: str) -> Derived:
    return _REGISTRY[name]


def _ensure_log(cur) -> None:
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {DERIVED_LOG} ("
        "  name VARCHAR NOT NULL, built_at TIMESTAMP, row_count BIGINT,"
        "  schema_fingerprint VARCHAR)"
    )
    # A database written before the fingerprint existed has the older shape.
    existing = {row[0] for row in cur.execute(f"DESCRIBE {DERIVED_LOG}").fetchall()}
    if "schema_fingerprint" not in existing:
        cur.execute(f"ALTER TABLE {DERIVED_LOG} ADD COLUMN schema_fingerprint VARCHAR")


def record_build(loader: "Loader", name: str, row_count: int | None = None) -> None:
    cur = loader.cursor()
    _ensure_log(cur)
    entry = _REGISTRY.get(name)
    cur.execute(f"DELETE FROM {DERIVED_LOG} WHERE name = ?", [name])
    cur.execute(
        f"INSERT INTO {DERIVED_LOG} VALUES (?, ?, ?, ?)",
        [
            name,
            datetime.now(timezone.utc).replace(tzinfo=None),
            row_count,
            entry.fingerprint() if entry else None,
        ],
    )


def built_at(loader: "Loader", name: str) -> datetime | None:
    cur = loader.cursor()
    _ensure_log(cur)
    row = cur.execute(f"SELECT built_at FROM {DERIVED_LOG} WHERE name = ?", [name]).fetchone()
    return row[0] if row else None


def is_stale(loader: "Loader", derived: Derived, table: str | None = None) -> bool:
    """Missing, never recorded, older than an input, or a different shape."""
    if table and not loader.table_exists(table):
        return True
    cur = loader.cursor()
    _ensure_log(cur)
    row = cur.execute(
        f"SELECT built_at, schema_fingerprint FROM {DERIVED_LOG} WHERE name = ?",
        [derived.name],
    ).fetchone()
    if not row or row[0] is None:
        return True
    built, recorded_shape = row
    wanted_shape = derived.fingerprint()
    if wanted_shape is not None and recorded_shape != wanted_shape:
        logger.info(
            "%s was built with a different shape (%s, now %s) — rebuilding",
            derived.name,
            recorded_shape or "unrecorded",
            wanted_shape,
        )
        return True
    newest_input = loader.newest_load(*derived.depends_on)
    return newest_input is not None and newest_input > built


def ensure(loader: "Loader", name: str, *, table: str | None = None) -> None:
    """Build `name` if it is missing or stale. Cheap to call on every read."""
    derived = _REGISTRY[name]
    if not is_stale(loader, derived, table):
        return
    with loader.lock_for(f"derived:{name}"):
        # Another thread may have built it while we queued for the lock.
        if not is_stale(loader, derived, table):
            return
        logger.info("Building derived table %s", name)
        derived.build(loader)


def build_all(loader: "Loader", *, force: bool = False) -> dict[str, str]:
    """Every derived table, for the build job. Returns name -> outcome."""
    outcomes: dict[str, str] = {}
    for derived in all_derived():
        try:
            if force:
                with loader.lock_for(f"derived:{derived.name}"):
                    derived.build(loader)
                outcomes[derived.name] = "rebuilt"
            elif is_stale(loader, derived):
                ensure(loader, derived.name)
                outcomes[derived.name] = "rebuilt"
            else:
                outcomes[derived.name] = "current"
        except Exception:
            logger.exception("Failed to build derived table %s", derived.name)
            outcomes[derived.name] = "failed"
    return outcomes
