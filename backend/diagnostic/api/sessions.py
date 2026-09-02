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
    is_valid_answer_shape,
    Diagnostic,
    DiagnosticCatalog,
)
from diagnostic.analytics import emit_event
from diagnostic.db import attempts, funnel
from diagnostic.db.attempts import AttemptCompletion, AttemptProgress
from diagnostic.db.gameplay import serialize_gameplay_profile
from diagnostic.review import build_review_snapshot, public_review_items
from diagnostic.scoring import (
    ScoreResult, estimate_for_primary, round_half_up, score_answers,
)
from diagnostic.school import SchoolConfig
from diagnostic.session_identity import (
    new_session_generation,
    session_scope as make_session_scope,
    session_subject_key,
)

from .dependencies import telegram_user
from .models import (
    ApiRequest, CatalogRequest, CompletionRequest, ProgressRequest, SessionRequest,
)


def build_forecast(
    diagnostic: Diagnostic, result: ScoreResult, school: SchoolConfig
) -> dict[str, Any]:
    """Project the offer's recovery share of the missed growth-topic points."""
    scale = school.scale_for(diagnostic.exam, diagnostic.subject)
    points = []
    for offer in school.links.offers:
        recovered = round_half_up(
            result.recoverable_primary_score * offer.recovery_share / 100
        )
        forecast_primary = min(
            result.primary_score + recovered, result.max_primary_score
        )
        value = (
            estimate_for_primary(
                scale, forecast_primary, result.max_primary_score, result.question_count
            ).value
            if scale is not None
            else round_half_up(
                forecast_primary / result.max_primary_score * result.max_score
            )
        )
        points.append({"id": offer.id, "label": offer.label, "value": value})
    return {
        "kind": result.estimate.kind if result.estimate is not None else "accuracy_percent",
        "points": points,
    }


def build_completion(
    user: dict[str, Any], body: CompletionRequest, diagnostic: Diagnostic, result: ScoreResult,
    school: SchoolConfig,
    report_asset_bundle_id: str,
    timezone_name: str = "Europe/Moscow",
) -> AttemptCompletion:
    forecast = build_forecast(diagnostic, result, school)
    result_snapshot = result.model_dump(mode="json") | {
        "unassessed_part": school.brand.interface.unassessed_full if body.mode == "quick" else None,
        "forecast": forecast,
    }
    selected_questions = (
        diagnostic.questions[: diagnostic.quick_count]
        if body.mode == "quick" else diagnostic.questions
    )
    review_snapshot = build_review_snapshot(selected_questions, body.answers)
    public_review_snapshot = public_review_items({"review_snapshot": review_snapshot})
    report_snapshot = {
        "provenance": {
            "attempt_id": body.attempt_id,
            "diagnostic_id": diagnostic.id,
            "content_version": body.content_version,
            "exam": diagnostic.exam,
            "subject": diagnostic.subject,
            "mode": body.mode,
        },
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": [
                question.model_dump(mode="json", exclude={"correct", "explanation"})
                for question in selected_questions
            ],
        },
        "review_snapshot": review_snapshot,
        "public_review_snapshot": public_review_snapshot,
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
        activity_timezone=timezone_name,
    )


def _build_report_assets(
    school: SchoolConfig, questions: tuple[Any, ...]
) -> bytes:
    references = {school.brand.logo}
    references.update(
        asset
        for question in questions
        for asset in question.asset_paths
    )
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


def prepare_report_asset_bundles(
    school: SchoolConfig, catalog: DiagnosticCatalog
) -> dict[str, tuple[str, bytes]]:
    bundles: dict[str, tuple[str, bytes]] = {}
    for diagnostic in catalog.diagnostics:
        payload = _build_report_assets(school, diagnostic.questions)
        bundles[diagnostic.id] = (hashlib.sha256(payload).hexdigest(), payload)
    return bundles


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
    serialized = {key: row[key] for key in keys if key in available}
    snapshot = row["result_snapshot"] if "result_snapshot" in available else None
    estimate = snapshot.get("estimate") if isinstance(snapshot, Mapping) else None
    if isinstance(estimate, Mapping):
        serialized["estimate"] = dict(estimate)
    return serialized


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


def serialize_progress_profile(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"completion_count": 0, "achievement_keys": []}
    completion_count = row.get("completion_count", 0)
    if isinstance(completion_count, bool) or not isinstance(completion_count, int):
        completion_count = 0
    achievement_keys = row.get("achievement_keys", [])
    if not isinstance(achievement_keys, list):
        achievement_keys = []
    return {
        "completion_count": max(completion_count, 0),
        "achievement_keys": [key for key in achievement_keys if isinstance(key, str)],
    }


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


async def get_progress_profile(user_id: int):
    return await attempts.get_progress_profile(user_id)


def _funnel(
    background_tasks: BackgroundTasks,
    request: Request,
    user_id: int,
    action: str,
    exam: str | None = None,
    subject: str | None = None,
) -> None:
    """Queue one best-effort funnel row alongside the existing analytics event."""
    background_tasks.add_task(
        funnel.record_event,
        application_secret=request.app.state.settings.application_secret,
        user_id=user_id,
        action=action,
        exam=exam,
        subject=subject,
    )


async def get_gameplay_profile(user_id: int):
    return await attempts.get_gameplay_profile(user_id)


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
            _funnel(background_tasks, request, user["id"], "opened")
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
        progress_profile = await get_progress_profile(user["id"])
        try:
            gameplay_profile = await get_gameplay_profile(user["id"])
        except RuntimeError as exc:
            if str(exc) != "database_not_initialized":
                raise
            gameplay_profile = None
        school = request.app.state.school
        secret = request.app.state.settings.application_secret
        generation = await get_or_create_session_generation(
            session_subject_key(secret, user["id"])
        )
        return {
            "catalog_contract": 2,
            "session_scope": _session_scope(
                secret, user["id"], generation
            ),
            "latest_attempt_id": latest_attempt_id,
            "progress_profile": serialize_progress_profile(progress_profile),
            "gameplay_profile": serialize_gameplay_profile(gameplay_profile),
            "school": public_school_payload(school),
            "diagnostics": catalog.public_summaries(secret),
            "attempt": serialize_attempt(resumable),
            "results": [serialize_attempt(row) for row in completed],
        }

    @router.post("/catalog")
    async def catalog_detail(body: CatalogRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            diagnostic = catalog.get(body.diagnostic_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=404, detail="diagnostic_not_found"
            ) from exc
        secret = request.app.state.settings.application_secret
        current_version = catalog.content_version(diagnostic.id, secret)
        if not hmac.compare_digest(body.content_version, current_version):
            raise HTTPException(
                status_code=409, detail="diagnostic_content_changed"
            )
        return {"diagnostic": catalog.public_diagnostic(diagnostic.id, secret)}

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
            _funnel(
                background_tasks, request, user["id"], "started",
                diagnostic.exam, diagnostic.subject,
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
        school = request.app.state.school
        result = score_answers(
            catalog, body.diagnostic_id, body.mode, body.answers,
            school.scale_for(diagnostic.exam, diagnostic.subject),
        )
        try:
            completion = build_completion(
                user,
                body,
                diagnostic,
                result,
                school,
                request.app.state.report_asset_bundles[diagnostic.id][0],
                request.app.state.settings.timezone,
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
                _funnel(
                    background_tasks, request, user["id"], "started",
                    diagnostic.exam, diagnostic.subject,
                )
            background_tasks.add_task(
                emit_event, "diagnostic_completed", user["id"],
                {
                    "attempt_id": body.attempt_id, "diagnostic_id": diagnostic.id,
                    "mode": body.mode, "question_count": result.question_count,
                    "result_status": "completed", "delivery_status": "pending",
                },
            )
            _funnel(
                background_tasks, request, user["id"], "completed",
                diagnostic.exam, diagnostic.subject,
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
            _funnel(
                background_tasks, request, user["id"], "result_viewed",
                row.get("exam"), row.get("subject"),
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
        if question.id in answers and not is_valid_answer_shape(
            question, answers[question.id], complete=complete
        ):
            raise HTTPException(status_code=422, detail="invalid_answer_value")
