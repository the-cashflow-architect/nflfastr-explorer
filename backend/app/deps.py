"""The one Loader the application shares, and the FastAPI dependency for it.

A module-level singleton rather than app state so that scripts, the ETL and the
API all reach the same database through the same object. Tests replace it with
`use_loader`, which is why nothing imports `loader` directly.
"""

from __future__ import annotations

import threading

from .loader import Loader

_loader: Loader | None = None
_guard = threading.Lock()


def get_loader() -> Loader:
    global _loader
    if _loader is None:
        with _guard:
            if _loader is None:
                _loader = Loader()
    return _loader


def use_loader(loader: Loader | None) -> None:
    """Point the process at a different database. Tests only."""
    global _loader
    with _guard:
        _loader = loader
