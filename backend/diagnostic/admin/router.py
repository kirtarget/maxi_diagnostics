"""Protected HTML and JSON routes for diagnostic administration."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.templating import Jinja2Templates

from diagnostic.db.messages import MESSAGE_KEYS
from diagnostic.db.content import ContentDraftNotFound, ContentRevisionConflict
from diagnostic.catalog import Diagnostic, DiagnosticCatalog
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


class ExpectedRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=9_223_372_036_854_775_807, strict=True)


class QuestionWrite(ExpectedRevision):
    question: dict[str, Any]

    @field_validator("question")
    @classmethod
    def bound_question_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 65_536:
            raise ValueError("question_payload_too_large")
        return value


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


def _admin_context(request: Request) -> dict[str, str]:
    school = request.app.state.school
    return {
        "school_name": school.brand.name,
        "primary_color": school.brand.colors.primary,
        "accent_color": school.brand.colors.accent,
        "background_color": school.brand.colors.background,
    }


def _require_admin_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin != request.app.state.settings.miniapp_origin:
        raise HTTPException(status_code=403, detail="admin_origin_invalid")


def _draft_response(row: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(
        row,
        (
            "diagnostic_id", "payload", "edit_revision", "base_content_version",
            "payload_sha256", "updated_by", "updated_at",
        ),
    )


def _actor(request: Request) -> str:
    return request.app.state.settings.admin_username


def _diagnostic_or_404(request: Request, diagnostic_id: str) -> Diagnostic:
    try:
        return request.app.state.catalog.get(diagnostic_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="diagnostic_not_found") from exc


def _validate_diagnostic(payload: Mapping[str, Any], diagnostic_id: str) -> Diagnostic:
    try:
        diagnostic = Diagnostic.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="content_invalid") from exc
    if diagnostic.id != diagnostic_id:
        raise HTTPException(status_code=422, detail="diagnostic_id_immutable")
    return diagnostic


def _validate_full_catalog(request: Request, draft: Diagnostic) -> DiagnosticCatalog:
    published_assets = {
        asset
        for diagnostic in request.app.state.catalog.diagnostics
        for question in diagnostic.questions
        for asset in question.asset_paths
    }
    draft_assets = {
        asset for question in draft.questions for asset in question.asset_paths
    }
    if not draft_assets.issubset(published_assets):
        raise HTTPException(status_code=422, detail="content_asset_not_available")
    diagnostics = tuple(
        draft if diagnostic.id == draft.id else diagnostic
        for diagnostic in request.app.state.catalog.diagnostics
    )
    try:
        return DiagnosticCatalog(diagnostics=diagnostics)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="content_catalog_invalid") from exc


def _require_current_base(request: Request, row: Mapping[str, Any]) -> None:
    diagnostic_id = str(row["diagnostic_id"])
    current_version = request.app.state.catalog.content_version(
        diagnostic_id,
        request.app.state.settings.application_secret,
    )
    if row["base_content_version"] != current_version:
        raise HTTPException(status_code=409, detail="content_base_changed")


async def _draft_or_404(diagnostic_id: str):
    row = await repository.get_content_draft(diagnostic_id)
    if row is None:
        raise HTTPException(status_code=404, detail="content_draft_not_found")
    return row


def _content_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, ContentDraftNotFound):
        return HTTPException(status_code=404, detail="content_draft_not_found")
    if isinstance(exc, ContentRevisionConflict):
        return HTTPException(status_code=409, detail="content_revision_conflict")
    return HTTPException(status_code=500, detail="content_operation_failed")


@router.get("/admin/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context=_admin_context(request),
    )


@router.get("/admin/funnel", response_class=HTMLResponse)
async def funnel_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="funnel.html",
        context=_admin_context(request),
    )


@router.get("/api/admin/diagnostics/funnel")
async def funnel_report(
    days: int = Query(7, ge=7, le=30),
    exam: str | None = Query(default=None, max_length=32),
    subject: str | None = Query(default=None, max_length=128),
):
    if days not in (7, 30):
        raise HTTPException(status_code=422, detail="funnel_window_invalid")
    return await repository.get_funnel(days=days, exam=exam, subject=subject)


@router.get("/admin/content", response_class=HTMLResponse)
async def content_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="content.html",
        context=_admin_context(request),
    )


@router.get("/api/admin/diagnostics/content")
async def content_index(
    request: Request,
    exam: str | None = Query(default=None, min_length=1, max_length=32),
    subject: str | None = Query(default=None, min_length=1, max_length=128),
    question_type: str | None = Query(default=None, alias="type", pattern=r"^(single|multiple|matching|input)$"),
    query: str | None = Query(default=None, min_length=1, max_length=128),
):
    draft_rows = await repository.list_content_drafts()
    drafts = {row["diagnostic_id"]: row for row in draft_rows}
    items: list[dict[str, Any]] = []
    needle = query.casefold() if query else None
    for published in request.app.state.catalog.diagnostics:
        row = drafts.get(published.id)
        payload = row["payload"] if row is not None else published.model_dump(mode="json")
        try:
            diagnostic = Diagnostic.model_validate(payload)
        except Exception:
            diagnostic = published
        if exam and diagnostic.exam != exam:
            continue
        if subject and diagnostic.subject != subject:
            continue
        questions = []
        for question in diagnostic.questions:
            if question_type and question.type != question_type:
                continue
            if needle and needle not in " ".join(
                (question.id, question.title, question.topic, question.prompt)
            ).casefold():
                continue
            source = getattr(question, "source", None)
            questions.append(
                {
                    "id": question.id,
                    "type": question.type,
                    "topic": question.topic,
                    "title": question.title,
                    "max_primary_score": getattr(question, "max_primary_score", None),
                    "has_explanation": bool(question.explanation),
                    "has_source": source is not None,
                }
            )
        if questions:
            items.append(
                {
                    "diagnostic_id": diagnostic.id,
                    "exam": diagnostic.exam,
                    "subject": diagnostic.subject,
                    "is_draft": row is not None,
                    "edit_revision": row["edit_revision"] if row is not None else None,
                    "questions": questions,
                }
            )
    return {
        "catalog_question_count": sum(
            len(item.questions) for item in request.app.state.catalog.diagnostics
        ),
        "diagnostic_question_limit": 200,
        "items": items,
    }


@router.post(
    "/api/admin/diagnostics/content/{diagnostic_id}/draft",
    status_code=status.HTTP_201_CREATED,
)
async def content_draft_create(diagnostic_id: str, request: Request):
    _require_admin_origin(request)
    diagnostic = _diagnostic_or_404(request, diagnostic_id)
    row = await repository.create_content_draft(
        diagnostic_id=diagnostic.id,
        payload=diagnostic.model_dump(mode="json"),
        base_content_version=request.app.state.catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        ),
        actor=_actor(request),
    )
    return _draft_response(row)


@router.get("/api/admin/diagnostics/content/{diagnostic_id}/draft")
async def content_draft_get(diagnostic_id: str):
    return _draft_response(await _draft_or_404(diagnostic_id))


@router.post("/api/admin/diagnostics/content/{diagnostic_id}/draft/questions")
async def content_question_create(
    diagnostic_id: str, body: QuestionWrite, request: Request
):
    _require_admin_origin(request)
    row = await _draft_or_404(diagnostic_id)
    payload = dict(row["payload"])
    questions = list(payload.get("questions", []))
    question_id = body.question.get("id")
    if not isinstance(question_id, str):
        raise HTTPException(status_code=422, detail="content_invalid")
    if any(question.get("id") == question_id for question in questions):
        raise HTTPException(status_code=409, detail="question_already_exists")
    questions.append(body.question)
    payload["questions"] = questions
    diagnostic = _validate_diagnostic(payload, diagnostic_id)
    _validate_full_catalog(request, diagnostic)
    try:
        saved = await repository.save_content_draft(
            diagnostic_id=diagnostic_id,
            payload=diagnostic.model_dump(mode="json"),
            expected_revision=body.expected_revision,
            actor=_actor(request),
            action="question_created",
            question_id=question_id,
        )
    except RuntimeError as exc:
        raise _content_error(exc) from exc
    return _draft_response(saved)


@router.put(
    "/api/admin/diagnostics/content/{diagnostic_id}/draft/questions/{question_id}"
)
async def content_question_update(
    diagnostic_id: str, question_id: str, body: QuestionWrite, request: Request
):
    _require_admin_origin(request)
    if body.question.get("id") != question_id:
        raise HTTPException(status_code=422, detail="question_id_immutable")
    row = await _draft_or_404(diagnostic_id)
    payload = dict(row["payload"])
    questions = list(payload.get("questions", []))
    indexes = [index for index, item in enumerate(questions) if item.get("id") == question_id]
    if not indexes:
        raise HTTPException(status_code=404, detail="question_not_found")
    questions[indexes[0]] = body.question
    payload["questions"] = questions
    diagnostic = _validate_diagnostic(payload, diagnostic_id)
    _validate_full_catalog(request, diagnostic)
    try:
        saved = await repository.save_content_draft(
            diagnostic_id=diagnostic_id,
            payload=diagnostic.model_dump(mode="json"),
            expected_revision=body.expected_revision,
            actor=_actor(request),
            action="question_updated",
            question_id=question_id,
        )
    except RuntimeError as exc:
        raise _content_error(exc) from exc
    return _draft_response(saved)


@router.post("/api/admin/diagnostics/content/{diagnostic_id}/draft/validate")
async def content_draft_validate(
    diagnostic_id: str, body: ExpectedRevision, request: Request
):
    _require_admin_origin(request)
    row = await _draft_or_404(diagnostic_id)
    _require_current_base(request, row)
    diagnostic = _validate_diagnostic(row["payload"], diagnostic_id)
    catalog = _validate_full_catalog(request, diagnostic)
    try:
        await repository.record_content_action(
            diagnostic_id=diagnostic_id,
            expected_revision=body.expected_revision,
            actor=_actor(request),
            action="validated",
        )
    except RuntimeError as exc:
        raise _content_error(exc) from exc
    return {
        "ok": True,
        "edit_revision": body.expected_revision,
        "diagnostic_count": len(catalog.diagnostics),
        "question_count": sum(len(item.questions) for item in catalog.diagnostics),
    }


@router.post("/api/admin/diagnostics/content/{diagnostic_id}/draft/export")
async def content_draft_export(
    diagnostic_id: str, body: ExpectedRevision, request: Request
):
    _require_admin_origin(request)
    row = await _draft_or_404(diagnostic_id)
    _require_current_base(request, row)
    diagnostic = _validate_diagnostic(row["payload"], diagnostic_id)
    _validate_full_catalog(request, diagnostic)
    try:
        await repository.record_content_action(
            diagnostic_id=diagnostic_id,
            expected_revision=body.expected_revision,
            actor=_actor(request),
            action="exported",
        )
    except RuntimeError as exc:
        raise _content_error(exc) from exc
    encoded = (
        json.dumps(
            diagnostic.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    return Response(
        encoded,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{diagnostic.id}.json"'
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
