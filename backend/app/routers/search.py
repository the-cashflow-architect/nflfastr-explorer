"""GET /api/search — the one global search the whole product navigates through.

All the work is in `app.repo.search`; this module stays as thin as
`routers/coverage.py`.

The response model is declared rather than returned as a bare dict, and that is
load-bearing. The frontend's types are generated from this schema, so an
undeclared shape arrives there as `{}` — every field access unchecked. This
endpoint shipped that way once: the palette had been hand-typed against
`hits`/`kind`/`title` while the server sends `items`/`type`/`label`, nothing
caught it, and typing a second character into the search box threw.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from ..repo import search as search_repo

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchItem(BaseModel):
    """One result. `label`, `href` and `id` are the contract; the rest is context.

    Extra keys are allowed through because each group carries its own — a player
    has a headshot and seasons, a game has a score — and enumerating every
    variant here would be a second place to keep in step with the repo.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    label: str
    href: str
    sublabel: str | None = None
    headshot_url: str | None = None
    logo: str | None = None


class SearchGroup(BaseModel):
    #: player, team, team_season, game, season, draft, navigation — returned in a
    #: fixed order, and returned even when empty so the order is stable.
    type: str
    items: list[SearchItem]


class SearchResponse(BaseModel):
    query: str
    groups: list[SearchGroup]


@router.get("", response_model=SearchResponse)
def get_search(
    q: str = Query(default="", description="Search text; queries under two characters answer empty."),
    limit: int = Query(default=search_repo.DEFAULT_LIMIT, ge=1, le=50, description="Max results per group."),
) -> Any:
    return search_repo.search(q, limit)
