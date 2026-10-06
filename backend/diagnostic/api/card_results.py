"""Completed card attempts for the admission-card server."""

import hmac
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from diagnostic.card_auth import CARD_ID_PATTERN, card_user_id
from diagnostic.db import attempts
from diagnostic.scoring import round_half_up


class CardResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: str = Field(pattern=CARD_ID_PATTERN)


def create_card_results_router() -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/card-results")
    async def card_results(body: CardResultsRequest, request: Request):
        secret = request.app.state.settings.admission_diagnostics_secret
        supplied = request.headers.get("x-admission-diagnostics-secret", "")
        if not secret or not hmac.compare_digest(secret.encode(), supplied.encode()):
            raise HTTPException(status_code=403, detail="invalid_init_data")
        rows = await attempts.list_card_results(card_user_id(body.card_id))
        results = []
        for row in rows:
            snapshot = row["result_snapshot"] or {}
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)
            accuracy = snapshot.get("accuracy_percent")
            if accuracy is None:
                accuracy = round_half_up(row["correct_count"] / row["question_count"] * 100)
            results.append({
                "attempt_id": row["attempt_id"],
                "diagnostic_id": row["diagnostic_id"],
                "mode": row["mode"],
                "completed_at": row["completed_at"].isoformat(),
                "accuracy_percent": accuracy,
                "strong_topics": row["strong_topics"],
                "growth_topics": row["growth_topics"],
            })
        return {"results": results}

    return router
