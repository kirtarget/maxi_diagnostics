"""Authenticated trainer session endpoints."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from diagnostic.catalog import (
    is_valid_answer_shape,
    DiagnosticCatalog,
    public_question,
)
from diagnostic.daily_plan import ensure_today_plan, plan_status
from diagnostic.db import attempts, trainer
from diagnostic.db import topic_progress as topic_progress_store
from diagnostic.db import topic_checkpoints as topic_checkpoints_store
from diagnostic.db.gameplay import serialize_gameplay_profile
from diagnostic.review import fallback_guidance, format_answer
from diagnostic.scoring import is_answer_correct
from diagnostic.topic_checkpoint import (
    build_checkpoints,
    build_units,
    checkpoint_unit_question_ids,
    gate_path,
    is_passing,
    serialize_checkpoints,
)
from diagnostic.topic_path import (
    TODAY_SESSION_SIZE,
    build_topic_path,
    current_topic,
    estimate_minutes,
    select_today_question_ids,
    serialize_path,
)

from .dependencies import telegram_user
from .models import (
    CheckpointRecordRequest,
    CheckpointStartRequest,
    DailyPlanRequest,
    TodayRequest,
    TopicPathRequest,
    TrainerAnswerRequest,
    TrainerFinishRequest,
    TrainerLivesReminderRequest,
    TrainerStartRequest,
)
from .sessions import _funnel, _require_current_session


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
        "trainer_plan_unavailable": 409,
        "trainer_plan_conflict": 409,
    }.get(str(exc), 409)
    return HTTPException(status_code=status, detail=str(exc))


def create_trainer_router(catalog: DiagnosticCatalog) -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/trainer/start")
    async def start(body: TrainerStartRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
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
        plan = None
        session_topic = None
        today_started = False
        if body.mode == "today":
            progress_map = await topic_progress_store.get_progress_map(
                user["id"], diagnostic.id, content_version
            )
            passed_map = await topic_checkpoints_store.get_passed_map(
                user["id"], diagnostic.id, content_version
            )
            path = gate_path(
                build_topic_path(diagnostic.questions, progress_map), passed_map
            )
            node = current_topic(path)
            if node is None:
                raise HTTPException(status_code=409, detail="trainer_path_complete")
            session_topic = node.topic
            try:
                resumable = await trainer.get_resumable_session(
                    user_id=user["id"], diagnostic_id=diagnostic.id,
                    content_version=content_version, mode="today",
                    topic=session_topic,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            if resumable is not None:
                questions = tuple(
                    question for question in diagnostic.questions
                    if question.id in resumable[0]["question_ids"]
                )
            else:
                selected_ids = select_today_question_ids(
                    diagnostic.questions, path, progress_map, size=body.count
                )
                by_id = {question.id: question for question in diagnostic.questions}
                questions = tuple(by_id[qid] for qid in selected_ids)
            if not questions:
                raise HTTPException(status_code=409, detail="trainer_path_complete")
            today_started = True
        elif body.mode == "plan":
            try:
                plan = await ensure_today_plan(
                    user_id=user["id"],
                    catalog=catalog,
                    application_secret=request.app.state.settings.application_secret,
                    timezone_name=request.app.state.settings.timezone,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            if plan is None:
                raise HTTPException(status_code=409, detail="trainer_plan_unavailable")
            if plan["diagnostic_id"] != diagnostic.id:
                raise HTTPException(status_code=409, detail="trainer_plan_conflict")
            if plan["content_version"] != content_version:
                raise HTTPException(status_code=409, detail="trainer_content_changed")
            try:
                resumable = await trainer.get_resumable_session(
                    user_id=user["id"], diagnostic_id=diagnostic.id,
                    content_version=content_version, mode=body.mode,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            question_ids = (
                resumable[0]["question_ids"] if resumable is not None
                else plan["question_ids"]
            )
            by_id = {question.id: question for question in diagnostic.questions}
            questions = tuple(
                by_id[question_id] for question_id in question_ids if question_id in by_id
            )
            if not questions:
                raise HTTPException(status_code=409, detail="trainer_plan_unavailable")
        elif body.mode == "mistakes":
            if body.source_attempt_id is None:
                raise HTTPException(status_code=409, detail="trainer_mistakes_source_required")
            source_attempt_id = body.source_attempt_id
            session_topic = body.topic
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
                    topic=body.topic if body.mode == "mistakes" else None,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            if resumable is None:
                try:
                    question_ids = await trainer.seed_and_list_mistakes(
                        user_id=user["id"], diagnostic_id=diagnostic.id,
                        source_attempt_id=source_attempt_id,
                        content_version=content_version,
                        topic=body.topic,
                    )
                except ValueError as exc:
                    raise _error(exc) from exc
                questions = tuple(
                    question for question in diagnostic.questions
                    if question.id in question_ids and (body.topic is None or question.topic == body.topic)
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
        selected = list(
            questions if resumable is not None or body.mode in ("plan", "today")
            else questions[: body.count]
        )
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
                    topic=session_topic,
                )
            except ValueError as exc:
                raise _error(exc) from exc
        else:
            session, profile = resumable
        # The stored session order is authoritative: the answer endpoint checks the
        # question against `selected_question_ids[current_index]`.
        by_id = {question.id: question for question in diagnostic.questions}
        selected = [
            by_id[question_id]
            for question_id in session.get("question_ids", ())
            if question_id in by_id
        ]
        if not selected:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        profile_payload = serialize_gameplay_profile(profile)
        payload = {
            "ok": True,
            **session,
            "questions": [public_question(question) for question in selected],
            "lives_remaining": profile_payload["lives_remaining"],
            "next_life_at": profile_payload["next_life_at"],
        }
        if today_started:
            _funnel(background_tasks, request, user["id"], "daily_started",
                    diagnostic.exam, diagnostic.subject,
                    dedupe_key=f"today/{session['trainer_session_id']}")
        if plan is not None:
            _funnel(background_tasks, request, user["id"], "daily_started",
                    diagnostic.exam, diagnostic.subject,
                    dedupe_key=f"plan/{plan['plan_date']}")
            payload["plan"] = {
                "plan_date": plan["plan_date"],
                "total": plan["total"],
                "completed": plan["completed"],
                "reasons": plan["reasons"],
            }
        return payload

    @router.post("/daily-plan")
    async def daily_plan(body: DailyPlanRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            plan = await ensure_today_plan(
                user_id=user["id"],
                catalog=catalog,
                application_secret=request.app.state.settings.application_secret,
                timezone_name=request.app.state.settings.timezone,
            )
        except ValueError as exc:
            raise _error(exc) from exc
        if plan is None:
            return {
                "plan_date": None, "diagnostic_id": None, "subject": None,
                "exam": None, "total": 0, "completed": 0, "questions": [],
                "status": "no_diagnostic",
            }
        try:
            diagnostic = catalog.get(plan["diagnostic_id"])
        except ValueError:
            return {
                "plan_date": plan["plan_date"], "diagnostic_id": None, "subject": None,
                "exam": None, "total": 0, "completed": 0, "questions": [],
                "status": "no_diagnostic",
            }
        topics = {question.id: question.topic for question in diagnostic.questions}
        return {
            "plan_date": plan["plan_date"],
            "diagnostic_id": diagnostic.id,
            "subject": diagnostic.subject,
            "exam": diagnostic.exam,
            "total": plan["total"],
            "completed": plan["completed"],
            "questions": [
                {
                    "question_id": question_id,
                    "topic": topics.get(question_id, ""),
                    "reason": plan["reasons"].get(question_id, "growth_topic"),
                    "completed": question_id in set(plan["completed_question_ids"]),
                }
                for question_id in plan["question_ids"]
                if question_id in topics
            ],
            "status": plan_status(plan["total"], plan["completed"]),
        }

    @router.post("/path")
    async def topic_path(body: TopicPathRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            diagnostic = catalog.get(body.diagnostic_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        content_version = catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        )
        if content_version != body.content_version:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        progress_map = await topic_progress_store.get_progress_map(
            user["id"], diagnostic.id, content_version
        )
        passed_map = await topic_checkpoints_store.get_passed_map(
            user["id"], diagnostic.id, content_version
        )
        mastery_path = build_topic_path(diagnostic.questions, progress_map)
        path = gate_path(mastery_path, passed_map)
        checkpoints = build_checkpoints(path, passed_map)
        node = current_topic(path)
        return {
            "diagnostic_id": diagnostic.id,
            "content_version": content_version,
            "subject": diagnostic.subject,
            "exam": diagnostic.exam,
            "current_topic": node.topic if node is not None else None,
            "done_count": sum(1 for topic_node in path if topic_node.status == "done"),
            "total_count": len(path),
            "topics": serialize_path(path),
            "checkpoints": serialize_checkpoints(checkpoints),
        }

    @router.post("/today")
    async def today(body: TodayRequest, request: Request) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        gameplay_row = await attempts.get_gameplay_profile(user["id"])
        gameplay = serialize_gameplay_profile(gameplay_row)
        base = {
            "streak_days": gameplay["streak_days"],
            "daily_goal": gameplay["daily_goal"],
            "xp_total": gameplay["xp_total"],
        }
        diagnostic_id = body.diagnostic_id
        if diagnostic_id is None:
            diagnostic_id = await topic_progress_store.latest_completed_diagnostic(user["id"])
        diagnostic = None
        if diagnostic_id is not None:
            try:
                diagnostic = catalog.get(diagnostic_id)
            except ValueError:
                diagnostic = None
        if diagnostic is None:
            return {
                "status": "no_diagnostic",
                "diagnostic_id": None, "content_version": None,
                "subject": None, "exam": None, "topic": None,
                "topic_total": 0, "topic_mastered": 0,
                "size": 0, "estimated_minutes": 0, "path": [], **base,
            }
        content_version = catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        )
        progress_map = await topic_progress_store.get_progress_map(
            user["id"], diagnostic.id, content_version
        )
        passed_map = await topic_checkpoints_store.get_passed_map(
            user["id"], diagnostic.id, content_version
        )
        mastery_path = build_topic_path(diagnostic.questions, progress_map)
        path = gate_path(mastery_path, passed_map)
        checkpoints = build_checkpoints(path, passed_map)
        node = current_topic(path)
        selected_ids = select_today_question_ids(
            diagnostic.questions, path, progress_map, size=TODAY_SESSION_SIZE
        )
        size = len(selected_ids)
        pending_checkpoint = next(
            (item for item in checkpoints if item.status in ("available", "cooldown")),
            None,
        )
        if node is not None and size > 0:
            status = "ready"
        elif pending_checkpoint is not None:
            status = "checkpoint"
        else:
            status = "path_complete"
        return {
            "status": status,
            "diagnostic_id": diagnostic.id,
            "content_version": content_version,
            "subject": diagnostic.subject,
            "exam": diagnostic.exam,
            "topic": node.topic if node is not None else None,
            "topic_total": node.total if node is not None else 0,
            "topic_mastered": node.mastered if node is not None else 0,
            "size": size,
            "estimated_minutes": estimate_minutes(size),
            "path": serialize_path(path),
            "checkpoints": serialize_checkpoints(checkpoints),
            "checkpoint_unit_index": (
                pending_checkpoint.unit_index if pending_checkpoint is not None else None
            ),
            **base,
        }

    @router.post("/checkpoint/start")
    async def checkpoint_start(
        body: CheckpointStartRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            diagnostic = catalog.get(body.diagnostic_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        content_version = catalog.content_version(
            diagnostic.id, request.app.state.settings.application_secret
        )
        if content_version != body.content_version:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        progress_map = await topic_progress_store.get_progress_map(
            user["id"], diagnostic.id, content_version
        )
        passed_map = await topic_checkpoints_store.get_passed_map(
            user["id"], diagnostic.id, content_version
        )
        mastery_path = build_topic_path(diagnostic.questions, progress_map)
        path = gate_path(mastery_path, passed_map)
        checkpoints = build_checkpoints(path, passed_map)
        if body.unit_index >= len(checkpoints):
            raise HTTPException(status_code=422, detail="trainer_checkpoint_unit_unknown")
        node = checkpoints[body.unit_index]
        if node.status != "available":
            raise HTTPException(status_code=409, detail="trainer_checkpoint_unavailable")
        question_ids = checkpoint_unit_question_ids(
            diagnostic.questions, path, body.unit_index
        )
        if not question_ids:
            raise HTTPException(status_code=409, detail="trainer_checkpoint_unavailable")
        session_id = secrets.token_urlsafe(24)
        try:
            session, profile = await trainer.start_checkpoint_session(
                session_id=session_id,
                user_id=user["id"],
                diagnostic_id=diagnostic.id,
                content_version=content_version,
                selected_question_ids=question_ids,
            )
        except ValueError as exc:
            raise _error(exc) from exc
        by_id = {question.id: question for question in diagnostic.questions}
        selected = [
            by_id[question_id]
            for question_id in session.get("question_ids", ())
            if question_id in by_id
        ]
        if not selected:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        profile_payload = serialize_gameplay_profile(profile)
        _funnel(background_tasks, request, user["id"], "daily_started",
                diagnostic.exam, diagnostic.subject,
                dedupe_key=f"checkpoint/{session['trainer_session_id']}")
        return {
            "ok": True,
            **session,
            "unit_index": body.unit_index,
            "questions": [public_question(question) for question in selected],
            "lives_remaining": profile_payload["lives_remaining"],
            "next_life_at": profile_payload["next_life_at"],
        }

    @router.post("/checkpoint/record")
    async def checkpoint_record(
        body: CheckpointRecordRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        session = await trainer.get_session(body.trainer_session_id, user["id"])
        if session is None:
            raise HTTPException(status_code=404, detail="trainer_session_not_found")
        if session["mode"] != "checkpoint":
            raise HTTPException(status_code=409, detail="trainer_checkpoint_session_mismatch")
        content_version = catalog.content_version(
            session["diagnostic_id"], request.app.state.settings.application_secret
        )
        if content_version != session["content_version"]:
            raise HTTPException(status_code=409, detail="trainer_content_changed")
        try:
            diagnostic = catalog.get(session["diagnostic_id"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="trainer_content_changed") from exc
        progress_map = await topic_progress_store.get_progress_map(
            user["id"], diagnostic.id, content_version
        )
        passed_map = await topic_checkpoints_store.get_passed_map(
            user["id"], diagnostic.id, content_version
        )
        mastery_path = build_topic_path(diagnostic.questions, progress_map)
        path = gate_path(mastery_path, passed_map)
        units = build_units(path)
        if body.unit_index >= len(units):
            raise HTTPException(status_code=422, detail="trainer_checkpoint_unit_unknown")
        expected_ids = checkpoint_unit_question_ids(
            diagnostic.questions, path, body.unit_index
        )
        if set(session["selected_question_ids"]) != set(expected_ids):
            raise HTTPException(status_code=409, detail="trainer_checkpoint_session_mismatch")
        try:
            finished = await trainer.finish_session(
                session_id=body.trainer_session_id,
                user_id=user["id"],
                revision=body.revision,
            )
        except ValueError as exc:
            raise _error(exc) from exc
        correct_count = int(finished["correct_count"])
        question_count = int(finished["question_count"])
        passed = is_passing(correct_count, question_count)
        if passed and body.unit_index not in passed_map:
            try:
                await topic_checkpoints_store.record_pass(
                    user_id=user["id"],
                    diagnostic_id=diagnostic.id,
                    content_version=content_version,
                    unit_index=body.unit_index,
                    session_id=body.trainer_session_id,
                    correct_count=correct_count,
                    question_count=question_count,
                )
            except ValueError as exc:
                raise _error(exc) from exc
            _funnel(background_tasks, request, user["id"], "daily_completed",
                    dedupe_key=f"checkpoint/{body.trainer_session_id}")
        passed_map = await topic_checkpoints_store.get_passed_map(
            user["id"], diagnostic.id, content_version
        )
        path = gate_path(mastery_path, passed_map)
        checkpoints = build_checkpoints(path, passed_map)
        node = checkpoints[body.unit_index] if body.unit_index < len(checkpoints) else None
        return {
            "ok": True,
            "passed": passed,
            "unit_index": body.unit_index,
            "mastered_count": correct_count,
            "question_total": question_count,
            "checkpoint": serialize_checkpoints([node])[0] if node is not None else None,
            "checkpoints": serialize_checkpoints(checkpoints),
        }

    @router.post("/trainer/answer")
    async def answer(
        body: TrainerAnswerRequest, request: Request, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
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
        diagnostic, question = _trainer_question(
            catalog, session["diagnostic_id"], body.question_id
        )
        # A given-up question carries no answer to validate; it is graded wrong.
        if not body.give_up:
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
                is_correct=False if body.give_up else is_answer_correct(question, body.answer),
                public_feedback=feedback,
                timezone_name=request.app.state.settings.timezone,
                topic=question.topic,
                topic_question_ids=[
                    other.id for other in diagnostic.questions
                    if other.topic == question.topic
                ],
            )
            is_correct = bool(result.get("is_correct"))
            _funnel(
                background_tasks, request, user["id"], "trainer_answered",
                diagnostic.exam, diagnostic.subject,
                dedupe_key=f"trainer/{body.trainer_session_id}/{body.question_id}",
            )
            event_key = f"trainer/{body.trainer_session_id}/{body.question_id}"
            _funnel(background_tasks, request, user["id"], "question_answered",
                    diagnostic.exam, diagnostic.subject, dedupe_key=event_key)
            if result.get("life_delta", 0) < 0:
                _funnel(background_tasks, request, user["id"], "life_lost", dedupe_key=event_key)
            if result.get("xp_delta", 0) > 0:
                _funnel(background_tasks, request, user["id"], "streak_updated",
                        dedupe_key=datetime.now(ZoneInfo(request.app.state.settings.timezone)).date().isoformat())
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
    async def finish(body: TrainerFinishRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
        user = telegram_user(request, body.init_data)
        await _require_current_session(request, user["id"], body.session_scope)
        try:
            result = await trainer.finish_session(
                session_id=body.trainer_session_id,
                user_id=user["id"],
                revision=body.revision,
            )
            session = await trainer.get_session(body.trainer_session_id, user["id"])
            if session is not None and session["mode"] == "plan":
                _funnel(background_tasks, request, user["id"], "daily_completed",
                        dedupe_key=f"trainer/{body.trainer_session_id}")
            return result
        except ValueError as exc:
            raise _error(exc) from exc

    return router
