"""Authenticated Mini App bootstrap and attempt routes."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from diagnostic.catalog import (
    Diagnostic,
    DiagnosticCatalog,
    InputQuestion,
    MatchingQuestion,
    MultipleQuestion,
    SingleQuestion,
)
from diagnostic.analytics import emit_event
from diagnostic.db import attempts
from diagnostic.db.attempts import AttemptCompletion, AttemptProgress
from diagnostic.numeric import is_valid_numeric_answer
from diagnostic.review import build_review_snapshot, public_review_items
from diagnostic.scoring import ScoreResult, score_answers
from diagnostic.school import SchoolConfig
from diagnostic.session_identity import (
    new_session_generation,
    session_scope as make_session_scope,
    session_subject_key,
)

from .dependencies import telegram_user
from .models import ApiRequest, CompletionRequest, ProgressRequest, SessionRequest


def build_completion(
    user: dict[str, Any], body: CompletionRequest, diagnostic: Diagnostic, result: ScoreResult,
    school: SchoolConfig,
    report_asset_bundle_id: str,
) -> AttemptCompletion:
    forecast = {
        "points": [
            {
                "id": offer.id,
                "label": offer.label,
                "value": min(result.max_score, result.score + offer.forecast_delta),
            }
            for offer in school.links.offers
        ]
    }
    result_snapshot = result.model_dump(mode="json") | {
        "unassessed_part": school.brand.interface.unassessed_full if body.mode == "quick" else None,
        "forecast": forecast,
    }
    selected_questions = (
        diagnostic.questions[: diagnostic.quick_count]
        if body.mode == "quick" else diagnostic.questions
    )
    report_snapshot = {
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": [
                question.model_dump(mode="json", exclude={"correct", "explanation"})
                for question in selected_questions
            ],
        },
        "review_snapshot": build_review_snapshot(selected_questions, body.answers),
        "mode": body.mode,
        "school": {
            "brand": school.brand.model_dump(mode="json"),
            "links": school.links.model_dump(mode="json"),
        },
    }
    return AttemptCompletion(
        attempt_id=body.attempt_id,
        user_id=user["id"],
        diagnostic_id=diagnostic.id,
        content_version=body.content_version,
        exam=diagnostic.exam,
        subject=diagnostic.subject,
        mode=body.mode,
        question_count=result.question_count,
        progress_revision=body.progress_revision,
        answers=body.answers,
        correct_count=result.correct_count,
        score=result.score,
        max_score=result.max_score,
        score_unit=result.score_unit,
        unassessed_part=(
            school.brand.interface.unassessed_full if body.mode == "quick" else None
        ),
        strong_topics=[item.topic for item in result.strong_topics],
        growth_topics=[item.topic for item in result.growth_topics],
        forecast=forecast,
        result_snapshot=result_snapshot,
        report_snapshot=report_snapshot,
        report_asset_bundle_id=report_asset_bundle_id,
        supersedes_attempt_id=body.supersedes_attempt_id,
    )


def _build_report_assets(
    school: SchoolConfig, questions: tuple[Any, ...]
) -> bytes:
    references = {school.brand.logo}
    references.update(question.asset for question in questions if question.asset)
    if len(references) > 201:
        raise ValueError("too_many_report_assets")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in sorted(references):
            info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, school.resolve_asset(relative).read_bytes())
    payload = output.getvalue()
    if len(payload) > 25 * 1024 * 1024:
        raise ValueError("report_assets_too_large")
    return payload


def prepare_report_assets(
    school: SchoolConfig, catalog: DiagnosticCatalog
) -> tuple[str, bytes]:
    questions = tuple(
        question
        for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
    )
    payload = _build_report_assets(school, questions)
    return hashlib.sha256(payload).hexdigest(), payload


def serialize_attempt(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = (
        "attempt_id", "diagnostic_id", "content_version", "exam", "subject", "mode", "status", "question_index",
        "question_count", "progress_revision", "answers", "correct_count", "score", "max_score", "score_unit",
        "unassessed_part", "strong_topics", "growth_topics", "forecast", "pdf_status",
        "completed_at", "result_viewed_at",
    )
    available = set(row.keys())
    return {key: row[key] for key in keys if key in available}


def serialize_result(row: Mapping[str, Any], fallback: ScoreResult | None) -> dict[str, Any]:
    available = set(row.keys())
    snapshot = row["result_snapshot"] if "result_snapshot" in available else None
    if snapshot:
        return snapshot
    keys = (
        "diagnostic_id", "mode", "correct_count", "question_count", "score", "max_score",
        "score_unit", "strong_topics", "growth_topics",
    )
    persisted = {key: row[key] for key in keys if key in available}
    return persisted or (fallback.model_dump(mode="json") if fallback is not None else {})


def _transitioned(row: Mapping[str, Any] | None, key: str) -> bool:
    return row is not None and key in set(row.keys()) and row[key] is True


def _session_scope(application_secret: str, user_id: int, generation: str) -> str:
    return make_session_scope(application_secret, user_id, generation)


async def get_or_create_session_generation(subject_key: str) -> str:
    return await attempts.get_or_create_session_generation(
        subject_key, new_session_generation()
    )


async def get_session_generation(subject_key: str) -> str | None:
    return await attempts.get_session_generation(subject_key)


async def _require_current_session(request: Request, user_id: int, supplied: str) -> None:
    secret = request.app.state.settings.application_secret
    subject_key = session_subject_key(secret, user_id)
    generation = await get_session_generation(subject_key)
    if generation is None or not hmac.compare_digest(
        supplied, _session_scope(secret, user_id, generation)
    ):
        raise HTTPException(status_code=409, detail="session_expired")


def public_school_payload(school: SchoolConfig) -> dict[str, Any]:
    brand = school.brand
    links = school.links
    return {
        "brand": {
            "school_id": brand.school_id,
            "name": brand.name,
            "short_name": brand.short_name,
            "colors": brand.colors.model_dump(mode="json"),
            "logo": brand.logo,
            "interface": brand.interface.model_dump(mode="json"),
        },
        "links": {
            "website": str(links.website),
            "support": str(links.support),
            "privacy": str(links.privacy),
            "offers": [
                {
                    "id": offer.id,
                    "label": offer.label,
                    "button": offer.button,
                    "url": str(offer.url),
                }
                for offer in links.offers
            ],
        },
    }


async def get_resumable_attempt(user_id: int):
    return await attempts.get_resumable_attempt(user_id)


async def list_completed_attempts(user_id: int) -> list:
    return await attempts.list_completed_attempts(user_id)


async def get_latest_attempt_id(user_id: int) -> str | None:
    return await attempts.get_latest_attempt_id(user_id)


def create_router(catalog: DiagnosticCatalog) -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/bootstrap")
    async def bootstrap(
        body: ApiRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        try:
            first_open = await attempts.mark_opened(user["id"])
        except ValueError as exc:
            if str(exc) == "diagnostic_user_erased":
                raise HTTPException(status_code=410, detail="diagnostic_user_erased") from exc
            raise
        if first_open:
            background_tasks.add_task(emit_event, "diagnostic_opened", user["id"], {})
        resumable = await get_resumable_attempt(user["id"])
        if resumable is not None:
            resumable_diagnostic = next(
                (
                    item for item in catalog.diagnostics
                    if item.id == resumable["diagnostic_id"]
                ),
                None,
            )
            expected_version = (
                catalog.content_version(
                    resumable_diagnostic.id,
                    request.app.state.settings.application_secret
                )
                if resumable_diagnostic is not None else None
            )
            if resumable["content_version"] != expected_version:
                await attempts.supersede_stale_attempt(
                    resumable["attempt_id"], user["id"]
                )
                resumable = None
        completed = await list_completed_attempts(user["id"])
        latest_attempt_id = await get_latest_attempt_id(user["id"])
        school = request.app.state.school
        secret = request.app.state.settings.application_secret
        generation = await get_or_create_session_generation(
            session_subject_key(secret, user["id"])
        )
        return {
            "session_scope": _session_scope(
                secret, user["id"], generation
            ),
            "latest_attempt_id": latest_attempt_id,
            "school": public_school_payload(school),
            "diagnostics": catalog.public_payload(
                request.app.state.settings.application_secret
            )["diagnostics"],
            "attempt": serialize_attempt(resumable),
            "results": [serialize_attempt(row) for row in completed],
        }

    @router.post("/session/progress")
    async def progress(
        body: ProgressRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        diagnostic, expected_ids = _expected_questions(catalog, body.diagnostic_id, body.mode)
        current_version = catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        )
        if body.content_version != current_version:
            existing = await attempts.get_attempt(body.attempt_id, user["id"])
            if existing is not None and existing["status"] == "completed":
                if (
                    existing["diagnostic_id"] == body.diagnostic_id
                    and existing["content_version"] == body.content_version
                    and existing["mode"] == body.mode
                    and existing["question_count"] == body.question_count
                ):
                    return {"ok": True, "attempt": serialize_attempt(existing)}
                raise HTTPException(status_code=409, detail="attempt_conflict")
            raise HTTPException(status_code=409, detail="diagnostic_content_changed")
        if body.question_count != len(expected_ids) or body.question_index >= body.question_count:
            raise HTTPException(status_code=422, detail="invalid_question_progress")
        if set(body.answers) - expected_ids:
            raise HTTPException(status_code=422, detail="unknown_question")
        _validate_answer_values(catalog, body.diagnostic_id, body.mode, body.answers)
        try:
            row = await attempts.upsert_progress(
                AttemptProgress(
                    attempt_id=body.attempt_id,
                    user_id=user["id"],
                    diagnostic_id=diagnostic.id,
                    content_version=body.content_version,
                    exam=diagnostic.exam,
                    subject=diagnostic.subject,
                    mode=body.mode,
                    question_index=body.question_index,
                    question_count=body.question_count,
                    answers=body.answers,
                    progress_revision=body.progress_revision,
                    supersedes_attempt_id=body.supersedes_attempt_id,
                )
            )
        except ValueError as exc:
            if str(exc) == "diagnostic_attempt_conflict":
                raise HTTPException(status_code=409, detail="attempt_conflict") from exc
            if str(exc) == "diagnostic_progress_stale":
                raise HTTPException(status_code=409, detail="attempt_progress_stale") from exc
            if str(exc) == "diagnostic_rate_limited":
                raise HTTPException(status_code=429, detail="attempt_rate_limited") from exc
            if str(exc) == "diagnostic_user_erased":
                raise HTTPException(status_code=410, detail="diagnostic_user_erased") from exc
            raise
        if _transitioned(row, "started_transition"):
            background_tasks.add_task(
                emit_event, "diagnostic_started", user["id"],
                {"attempt_id": body.attempt_id, "diagnostic_id": diagnostic.id, "mode": body.mode},
            )
        return {"ok": True, "attempt": serialize_attempt(row)}

    @router.post("/session/complete")
    async def complete(
        body: CompletionRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        existing = await attempts.get_attempt(body.attempt_id, user["id"])
        if existing is not None and existing["status"] == "completed":
            if (
                existing["diagnostic_id"] != body.diagnostic_id
                or existing["content_version"] != body.content_version
                or existing["mode"] != body.mode
                or existing["question_count"] != body.question_count
            ):
                raise HTTPException(status_code=409, detail="attempt_conflict")
            return {
                "ok": True,
                "attempt": serialize_attempt(existing),
                "result": serialize_result(existing, None),
            }
        if existing is not None:
            if (
                existing["diagnostic_id"] != body.diagnostic_id
                or existing["content_version"] != body.content_version
                or existing["mode"] != body.mode
                or existing["question_count"] != body.question_count
            ):
                raise HTTPException(status_code=409, detail="attempt_conflict")
            if body.progress_revision < existing["progress_revision"]:
                raise HTTPException(status_code=409, detail="attempt_progress_stale")
        diagnostic, expected_ids = _expected_questions(catalog, body.diagnostic_id, body.mode)
        if body.content_version != catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        ):
            raise HTTPException(status_code=409, detail="diagnostic_content_changed")
        if body.question_count != len(expected_ids):
            raise HTTPException(status_code=422, detail="invalid_question_count")
        if set(body.answers) != expected_ids:
            raise HTTPException(status_code=422, detail="incomplete_or_unknown_answers")
        _validate_answer_values(
            catalog, body.diagnostic_id, body.mode, body.answers, complete=True
        )
        result = score_answers(catalog, body.diagnostic_id, body.mode, body.answers)
        try:
            completion = build_completion(
                user,
                body,
                diagnostic,
                result,
                request.app.state.school,
                request.app.state.report_asset_bundle_id,
            )
            row = await attempts.complete_attempt(completion)
        except ValueError as exc:
            if str(exc) == "diagnostic_attempt_conflict":
                raise HTTPException(status_code=409, detail="attempt_conflict") from exc
            if str(exc) == "diagnostic_progress_stale":
                raise HTTPException(status_code=409, detail="attempt_progress_stale") from exc
            if str(exc) == "diagnostic_rate_limited":
                raise HTTPException(status_code=429, detail="attempt_rate_limited") from exc
            if str(exc) == "diagnostic_user_erased":
                raise HTTPException(status_code=410, detail="diagnostic_user_erased") from exc
            raise
        if _transitioned(row, "completed_transition"):
            if _transitioned(row, "started_transition"):
                background_tasks.add_task(
                    emit_event, "diagnostic_started", user["id"],
                    {
                        "attempt_id": body.attempt_id,
                        "diagnostic_id": diagnostic.id,
                        "mode": body.mode,
                        "question_index": 0,
                    },
                )
            background_tasks.add_task(
                emit_event, "diagnostic_completed", user["id"],
                {
                    "attempt_id": body.attempt_id, "diagnostic_id": diagnostic.id,
                    "mode": body.mode, "question_count": result.question_count,
                    "result_status": "completed", "delivery_status": "pending",
                },
            )
        return {
            "ok": True,
            "attempt": serialize_attempt(row),
            "result": serialize_result(row, result),
        }

    @router.post("/session/review")
    async def review(body: SessionRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        row = await attempts.get_review_attempt(body.attempt_id, user["id"])
        if row is None:
            raise HTTPException(status_code=404, detail="result_not_found")
        if row["status"] != "completed":
            raise HTTPException(status_code=409, detail="review_not_ready")
        items = public_review_items(row["report_snapshot"] or {})
        return {
            "ok": True,
            "available": items is not None,
            "items": items or [],
            "pdf_status": row["pdf_status"],
        }

    @router.post("/session/viewed")
    async def viewed(
        body: SessionRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            row = await attempts.mark_result_viewed(body.attempt_id, user["id"])
        except ValueError as exc:
            if str(exc) == "diagnostic_attempt_conflict":
                raise HTTPException(status_code=409, detail="attempt_conflict") from exc
            raise
        if _transitioned(row, "viewed_transition"):
            background_tasks.add_task(
                emit_event, "diagnostic_result_viewed", user["id"],
                {"attempt_id": body.attempt_id, "result_status": "viewed"},
            )
        return {"ok": True, "attempt": serialize_attempt(row)}

    return router


def _expected_questions(
    catalog: DiagnosticCatalog, diagnostic_id: str, mode: str
) -> tuple[Diagnostic, set[str]]:
    try:
        diagnostic = catalog.get(diagnostic_id)
        return diagnostic, {question.id for question in catalog.questions_for_mode(diagnostic_id, mode)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _validate_answer_values(
    catalog: DiagnosticCatalog,
    diagnostic_id: str,
    mode: str,
    answers: dict[str, Any],
    *,
    complete: bool = False,
) -> None:
    for question in catalog.questions_for_mode(diagnostic_id, mode):
        if question.id not in answers:
            continue
        answer = answers[question.id]
        if isinstance(question, SingleQuestion):
            valid = isinstance(answer, str) and answer in {
                option.id for option in question.options
            }
        elif isinstance(question, InputQuestion):
            valid = _is_valid_numeric_answer(answer)
        elif isinstance(question, MultipleQuestion):
            allowed = {option.id for option in question.options}
            valid = (
                isinstance(answer, list)
                and all(isinstance(value, str) for value in answer)
                and len(answer) == len(set(answer))
                and set(answer) <= allowed
                and len(answer) <= question.selection_limit
                and (not complete or len(answer) == question.selection_limit)
            )
        else:
            item_ids = {item.id for item in question.items}
            option_ids = {option.id for option in question.options}
            valid = (
                isinstance(answer, dict)
                and set(answer) <= item_ids
                and all(
                    isinstance(value, str) and value in option_ids
                    for value in answer.values()
                )
                and (not complete or set(answer) == item_ids)
            )
        if not valid:
            raise HTTPException(status_code=422, detail="invalid_answer_value")


def _is_valid_numeric_answer(value: object) -> bool:
    return is_valid_numeric_answer(value)
