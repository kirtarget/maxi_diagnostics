"""Protected HTML and JSON routes for diagnostic administration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.templating import Jinja2Templates

from diagnostic.db.messages import MESSAGE_KEYS
from diagnostic.messages import validate_message_template
from diagnostic.session_identity import new_session_generation, session_subject_key

from . import repository
from .auth import require_admin


_ROOT = Path(__file__).resolve().parent
_environment = Environment(
    loader=FileSystemLoader(_ROOT / "templates"),
    autoescape=select_autoescape(
        enabled_extensions=("html", "xml"), default_for_string=True
    ),
)
templates = Jinja2Templates(env=_environment)
router = APIRouter(dependencies=[Depends(require_admin)])
ALLOWED_MESSAGE_KEYS = MESSAGE_KEYS

_ATTEMPT_FIELDS = (
    "attempt_id", "user_id", "diagnostic_id", "exam", "subject", "mode", "status",
    "question_index", "question_count", "correct_count", "score", "max_score", "score_unit",
    "unassessed_part", "strong_topics", "growth_topics", "pdf_status", "pdf_attempts",
    "pdf_delivered_at", "pdf_message_id", "completed_at", "result_viewed_at", "updated_at",
)
_DELIVERY_FIELDS = (
    "attempt_id", "user_id", "diagnostic_id", "exam", "subject", "mode",
    "pdf_status", "pdf_attempts", "completed_at", "updated_at",
)
_NOTIFICATION_FIELDS = (
    "id", "user_id", "attempt_id", "kind", "due_at", "status", "attempts",
    "sent_at", "updated_at",
)
_MESSAGE_FIELDS = ("key", "text", "description", "updated_at")


class MessageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2_048)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message_text_blank")
        return value


class DeleteUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(ge=1, le=9_223_372_036_854_775_807, strict=True)
    confirm: Literal[True]


def _value(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError):
        return None


def _sanitize(row: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _value(row, field) for field in fields}


def _page(total: int, rows: list, fields: tuple[str, ...], limit: int, offset: int):
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_sanitize(row, fields) for row in rows],
    }


@router.get("/admin/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request):
    school = request.app.state.school
    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context={
            "school_name": school.brand.name,
            "primary_color": school.brand.colors.primary,
            "accent_color": school.brand.colors.accent,
            "background_color": school.brand.colors.background,
        },
    )


@router.get("/api/admin/diagnostics/summary")
async def summary():
    return await repository.get_summary()


@router.get("/api/admin/diagnostics/attempts")
async def attempts_list(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    total, rows = await repository.list_attempts(limit=limit, offset=offset)
    return _page(total, rows, _ATTEMPT_FIELDS, limit, offset)


@router.get("/api/admin/diagnostics/delivery-issues")
async def delivery_issues(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    total, rows = await repository.list_delivery_issues(limit=limit, offset=offset)
    return _page(total, rows, _DELIVERY_FIELDS, limit, offset)


@router.get("/api/admin/diagnostics/notification-issues")
async def notification_issues(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    total, rows = await repository.list_notification_issues(limit=limit, offset=offset)
    return _page(total, rows, _NOTIFICATION_FIELDS, limit, offset)


@router.get("/api/admin/diagnostics/messages")
async def messages_list():
    rows = await repository.list_messages()
    return {"items": [_sanitize(row, _MESSAGE_FIELDS) for row in rows]}


@router.put("/api/admin/diagnostics/messages/{key}")
async def message_update(key: str, body: MessageUpdate, request: Request):
    if key not in ALLOWED_MESSAGE_KEYS:
        raise HTTPException(status_code=404, detail="message_not_found")
    try:
        validate_message_template(key, body.text, request.app.state.school)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="message_template_invalid") from exc
    row = await repository.update_message(key, body.text)
    if row is None:
        raise HTTPException(status_code=404, detail="message_not_found")
    return _sanitize(row, _MESSAGE_FIELDS)


@router.delete("/api/admin/diagnostics/users")
async def user_delete(body: DeleteUserRequest, request: Request):
    deleted = await repository.delete_diagnostic_user(
        body.user_id,
        session_subject_key(
            request.app.state.settings.application_secret, body.user_id
        ),
        new_session_generation(),
    )
    return {"ok": True, "deleted": deleted}
