"""Every router the app mounts, collected in one place.

Each router module exposes a module-level `router = APIRouter(prefix="/api/...",
tags=[...])`. This module imports only the ones that exist and lists them in
`ALL_ROUTERS`; `main.py` mounts that tuple and nothing else, so adding a new
package is one import line and one tuple entry here, never a change to main.py's
route wiring.

    from . import <name>
    ALL_ROUTERS = (coverage.router, <name>.router, ...)
"""

from __future__ import annotations

from . import coverage, search

ALL_ROUTERS: tuple = (coverage.router, search.router)
