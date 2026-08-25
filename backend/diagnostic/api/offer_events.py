"""Authenticated privacy-safe offer event endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from diagnostic.db import offer_events
from diagnostic.db.core import get_pool
from diagnostic.session_identity import session_subject_key

from .dependencies import telegram_user
from .models import OfferEventRequest
from .sessions import _require_current_session


def create_offer_events_router() -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/offer-events")
    async def record(body: OfferEventRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        if body.placement not in offer_events.OFFER_PLACEMENTS:
            raise HTTPException(status_code=422, detail="offer_placement_invalid")
        if not any(offer.id == body.offer_id for offer in request.app.state.school.links.offers):
            raise HTTPException(status_code=422, detail="offer_not_found")

        subject_hash = session_subject_key(
            request.app.state.settings.application_secret,
            user["id"],
        )
        pool = await get_pool()
        try:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    recorded = await offer_events.record_offer_event(
                        connection,
                        event_id=body.event_id,
                        subject_hash=subject_hash,
                        placement=body.placement,
                        offer_id=body.offer_id,
                        event_type=body.event_type,
                    )
        except ValueError as exc:
            status = 429 if str(exc) == "offer_event_rate_limited" else 409
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        return {"ok": True, "recorded": recorded}

    return router
