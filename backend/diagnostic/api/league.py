"""Authenticated weekly league endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from diagnostic.db import league
from diagnostic.db.core import get_pool

from .dependencies import telegram_user
from .sessions import _require_current_session


class LeagueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    init_data: str = Field(min_length=1, max_length=16_384)
    session_scope: str = Field(pattern=r"^[0-9a-f]{24}$")


def create_league_router() -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/league")
    async def weekly_league(body: LeagueRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        pool = await get_pool()
        async with pool.acquire() as connection:
            return await league.get_weekly_league(
                connection,
                user_id=user["id"],
                application_secret=request.app.state.settings.application_secret,
                timezone_name=request.app.state.settings.timezone,
            )

    return router
