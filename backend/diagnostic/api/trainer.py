"""Authenticated trainer session endpoints."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from diagnostic.catalog import (
    is_valid_answer_shape,
    DiagnosticCatalog,
    public_question,
)
from diagnostic.db import trainer
from diagnostic.db.gameplay import serialize_gameplay_profile
from diagnostic.review import fallback_guidance, format_answer
from diagnostic.scoring import is_answer_correct

from .dependencies import telegram_user
from .models import (
    TrainerAnswerRequest,
    TrainerFinishRequest,
    TrainerLivesReminderRequest,
    TrainerStartRequest,
)
from .sessions import _require_current_session


def _validate_answer(question: Any, answer: Any) -> None:
    if not is_valid_answer_shape(question, answer, complete=True):
        raise HTTPException(status_code=422, detail="invalid_answer_value")


def _trainer_question(catalog: DiagnosticCatalog, diagnostic_id: str, question_id: str):
    try:
        diagnostic = catalog.get(diagnostic_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="trainer_content_changed") from exc
    for question in diagnostic.questions:
        if question.id == question_id:
            return diagnostic, question
    raise HTTPException(status_code=409, detail="trainer_question_not_found")


def _error(exc: ValueError) -> HTTPException:
    status = {
        "diagnostic_user_erased": 410,
        "trainer_session_not_found": 404,
        "trainer_no_lives": 409,
        "trainer_session_incomplete": 409,
        "trainer_answer_conflict": 409,
        "trainer_revision_stale": 409,
        "trainer_question_out_of_order": 409,
        "trainer_session_not_active": 409,
        "trainer_mistakes_source_not_found": 404,
        "trainer_mistakes_source_conflict": 409,
        "trainer_no_mistakes": 409,
    }.get(str(exc), 409)
    return HTTPException(status_code=status, detail=str(exc))


def create_trainer_router(catalog: DiagnosticCatalog) -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/trainer/start")
    async def start(body: TrainerStartRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            diagnostic = catalog.get(body.diagnostic_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        content_version = catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        )
        source_attempt_id = None
        resumable = None
        if body.mode == "mistakes":
            if body.source_attempt_id is None:
                raise HTTPException(status_code=409, detail="trainer_mistakes_source_required")
            source_attempt_id = body.source_attempt_id
            try:
                await trainer.validate_mistakes_source(
                    user_id=user["id"], diagnostic_id=diagnostic.id,
                    source_attempt_id=source_attempt_id,
                    content_version=content_version,
                )
                resumable = await trainer.get_resumable_session(
                    user_id=user["id"], diagnostic_id=diagnostic.id,
                    content_version=content_version, mode=body.mode,
                    source_attempt_id=source_attempt_id,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            if resumable is None:
                try:
                    question_ids = await trainer.seed_and_list_mistakes(
                        user_id=user["id"], diagnostic_id=diagnostic.id,
                        source_attempt_id=source_attempt_id,
                        content_version=content_version,
                    )
                except ValueError as exc:
                    raise _error(exc) from exc
                questions = tuple(
                    question for question in diagnostic.questions if question.id in question_ids
                )
                if not questions:
                    raise HTTPException(status_code=409, detail="trainer_no_mistakes")
            else:
                questions = tuple(
                    question for question in diagnostic.questions
                    if question.id in resumable[0]["question_ids"]
                )
        else:
            try:
                resumable = await trainer.get_resumable_session(
                    user_id=user["id"], diagnostic_id=diagnostic.id,
                    content_version=content_version, mode=body.mode,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            if resumable is not None:
                questions = tuple(
                    question for question in diagnostic.questions
                    if question.id in resumable[0]["question_ids"]
                )
            else:
                questions = diagnostic.questions
                if body.topic is not None:
                    questions = tuple(question for question in questions if question.topic == body.topic)
                if body.count > len(questions):
                    raise HTTPException(status_code=422, detail="trainer_not_enough_questions")
        selected = list(questions if resumable is not None else questions[: body.count])
        if not selected:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        session_id = secrets.token_urlsafe(24)
        if resumable is None:
            try:
                session, profile = await trainer.start_session(
                    session_id=session_id,
                    user_id=user["id"],
                    diagnostic_id=diagnostic.id,
                    content_version=content_version,
                    mode=body.mode,
                    selected_question_ids=[question.id for question in selected],
                    source_attempt_id=source_attempt_id,
                )
            except ValueError as exc:
                raise _error(exc) from exc
        else:
            session, profile = resumable
        session_question_ids = set(session.get("question_ids", ()))
        selected = [
            question for question in diagnostic.questions
            if question.id in session_question_ids
        ]
        if not selected:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        profile_payload = serialize_gameplay_profile(profile)
        return {
            "ok": True,
            **session,
            "questions": [public_question(question) for question in selected],
            "lives_remaining": profile_payload["lives_remaining"],
            "next_life_at": profile_payload["next_life_at"],
        }

    @router.post("/trainer/answer")
    async def answer(body: TrainerAnswerRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        session = await trainer.get_session(body.trainer_session_id, user["id"])
        if session is None:
            raise HTTPException(status_code=404, detail="trainer_session_not_found")
        expected_version = catalog.content_version(
            session["diagnostic_id"], request.app.state.settings.application_secret
        )
        if expected_version != session["content_version"]:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        _, question = _trainer_question(
            catalog, session["diagnostic_id"], body.question_id
        )
        _validate_answer(question, body.answer)
        key = body.idempotency_key or (
            f"trainer-answer/{body.question_id}/{body.revision}"
        )
        fingerprint = trainer.answer_fingerprint(
            session_id=body.trainer_session_id,
            question_id=body.question_id,
            answer=body.answer,
            revision=body.revision,
            idempotency_key=key,
        )
        correct_answer = format_answer(question, question.correct)
        explanation = question.explanation or fallback_guidance(question, correct_answer)
        feedback = {
            "correct_answer": correct_answer[:4000],
            "explanation": explanation[:4000],
        }
        try:
            result = await trainer.answer_question(
                session_id=body.trainer_session_id,
                user_id=user["id"],
                question_id=body.question_id,
                answer=body.answer,
                revision=body.revision,
                idempotency_key=key,
                fingerprint=fingerprint,
                is_correct=is_answer_correct(question, body.answer),
                public_feedback=feedback,
                timezone_name=request.app.state.settings.timezone,
            )
            is_correct = bool(result.get("is_correct"))
            return {
                **result,
                "max_primary_score": question.max_primary_score,
                "earned_primary_score": (
                    question.max_primary_score if is_correct else 0
                ),
            }
        except ValueError as exc:
            raise _error(exc) from exc

    @router.post("/trainer/lives-reminder")
    async def lives_reminder(
        body: TrainerLivesReminderRequest, request: Request
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            due_at = await trainer.schedule_lives_refill_reminder(user["id"])
        except ValueError as exc:
            raise _error(exc) from exc
        return {"ok": True, "due_at": due_at}

    @router.post("/trainer/finish")
    async def finish(body: TrainerFinishRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            return await trainer.finish_session(
                session_id=body.trainer_session_id,
                user_id=user["id"],
                revision=body.revision,
            )
        except ValueError as exc:
            raise _error(exc) from exc

    return router
