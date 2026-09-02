"""Server-owned «план на сегодня»: one small, deterministic task list per day.

The builder below is pure. It turns the owner's latest completed attempt, the
catalog for that diagnostic and the spaced-review state of past mistakes into an
ordered set of at most five questions. Persistence and locking live in
``diagnostic.db.daily_plan``; the catalog lookups live in the API and bot layers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from typing import Any, Literal
from zoneinfo import ZoneInfo


PLAN_SIZE = 5
"""Days between a review and the next one, indexed by successful review count."""
REVIEW_INTERVALS = (1, 3, 7)

PlanReason = Literal["mistake_review", "growth_topic"]


def plan_date_for(timezone_name: str, now: datetime | None = None) -> date:
    """Resolve the school-local day, matching the gameplay activity date."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ZoneInfo(timezone_name)).date()


def next_review(review_count: int, *, correct: bool, today: date) -> tuple[int, date]:
    """Advance one mistake's spaced-review state after a plan answer."""
    count = max(int(review_count), 0) + 1 if correct else 0
    interval = REVIEW_INTERVALS[min(count, len(REVIEW_INTERVALS) - 1)]
    return count, today + timedelta(days=interval)


@dataclass(frozen=True)
class MistakeState:
    """One row of the mistake ledger, reduced to what scheduling needs."""

    question_id: str
    review_count: int
    next_review_on: date | None


@dataclass(frozen=True)
class PlanQuestion:
    question_id: str
    topic: str
    reason: PlanReason


@dataclass(frozen=True)
class PlanSource:
    """The completed attempt a plan is derived from."""

    attempt_id: str | None
    diagnostic_id: str
    growth_topics: tuple[str, ...]
    answered_question_ids: frozenset[str]


@dataclass(frozen=True)
class DailyPlan:
    plan_date: date
    diagnostic_id: str
    content_version: str
    source_attempt_id: str | None
    questions: tuple[PlanQuestion, ...]

    @property
    def question_ids(self) -> list[str]:
        return [question.question_id for question in self.questions]

    @property
    def reasons(self) -> dict[str, str]:
        return {question.question_id: question.reason for question in self.questions}


def _shuffle_key(user_id: int, plan_date: date, question_id: str) -> str:
    seed = f"{user_id}:{plan_date.isoformat()}:{question_id}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def topic_names(topics: Iterable[Any]) -> tuple[str, ...]:
    """Growth topics reach us either as plain strings or as scored objects."""
    names: list[str] = []
    for topic in topics:
        value = topic.get("topic") if isinstance(topic, Mapping) else topic
        if isinstance(value, str) and value:
            names.append(value)
    return tuple(names)


def build_daily_plan(
    *,
    user_id: int,
    plan_date: date,
    content_version: str,
    source: PlanSource,
    questions: Sequence[Any],
    mistakes: Sequence[MistakeState],
    size: int = PLAN_SIZE,
) -> DailyPlan | None:
    """Pick at most ``size`` questions: due mistakes, then growth, then the rest.

    ``questions`` are catalog questions for ``source.diagnostic_id``; only their
    ``id`` and ``topic`` are read, so the caller keeps the correct answer server
    side. Ordering inside each bucket is seeded by user and date, so the same
    inputs always produce the same plan.
    """
    by_id = {question.id: question for question in questions}
    if not by_id:
        return None

    due = [
        mistake for mistake in mistakes
        if mistake.question_id in by_id
        and (mistake.next_review_on is None or mistake.next_review_on <= plan_date)
    ]
    due.sort(
        key=lambda mistake: (
            mistake.next_review_on or plan_date,
            mistake.review_count,
            _shuffle_key(user_id, plan_date, mistake.question_id),
        )
    )

    picked: list[PlanQuestion] = []
    used: set[str] = set()
    for mistake in due[:size]:
        picked.append(
            PlanQuestion(
                question_id=mistake.question_id,
                topic=by_id[mistake.question_id].topic,
                reason="mistake_review",
            )
        )
        used.add(mistake.question_id)

    growth = set(source.growth_topics)

    def fill(candidates: Iterable[Any]) -> None:
        ordered = sorted(
            candidates, key=lambda question: _shuffle_key(user_id, plan_date, question.id)
        )
        for question in ordered:
            if len(picked) >= size:
                return
            if question.id in used:
                continue
            picked.append(
                PlanQuestion(
                    question_id=question.id,
                    topic=question.topic,
                    reason="growth_topic",
                )
            )
            used.add(question.id)

    fill(
        question for question in questions
        if question.topic in growth and question.id not in source.answered_question_ids
    )
    fill(questions)

    if not picked:
        return None
    return DailyPlan(
        plan_date=plan_date,
        diagnostic_id=source.diagnostic_id,
        content_version=content_version,
        source_attempt_id=source.attempt_id,
        questions=tuple(picked),
    )


def plan_status(total: int, completed: int) -> str:
    if total <= 0:
        return "no_diagnostic"
    return "done" if completed >= total else "ready"


async def ensure_today_plan(
    *, user_id: int, catalog: Any, application_secret: str,
    timezone_name: str = "Europe/Moscow", now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build or reuse the owner's plan for the current school-local day.

    The catalog lookup lives here so the persistence layer stays free of content
    imports; the import below is local for the same reason.
    """
    from diagnostic.db import daily_plan as store

    today = plan_date_for(timezone_name, now)

    def build(inputs: store.PlanInputs) -> DailyPlan | None:
        source = inputs.source
        if source is None:
            return None
        try:
            diagnostic = catalog.get(source.diagnostic_id)
        except ValueError:
            return None
        return build_daily_plan(
            user_id=user_id,
            plan_date=inputs.plan_date,
            content_version=catalog.content_version(diagnostic.id, application_secret),
            source=source,
            questions=diagnostic.questions,
            mistakes=inputs.mistakes,
        )

    return await store.ensure_plan(user_id=user_id, plan_date=today, build=build)


def plan_summary(plan: Mapping[str, Any] | None, catalog: Any) -> dict[str, Any]:
    """Compact plan payload for the bootstrap response and the bot."""
    if plan is None:
        return {
            "plan_date": None, "diagnostic_id": None, "subject": None,
            "exam": None, "total": 0, "completed": 0, "status": "no_diagnostic",
        }
    subject = None
    exam = None
    try:
        diagnostic = catalog.get(plan["diagnostic_id"])
    except ValueError:
        diagnostic = None
    if diagnostic is not None:
        subject = diagnostic.subject
        exam = diagnostic.exam
    return {
        "plan_date": plan["plan_date"],
        "diagnostic_id": plan["diagnostic_id"],
        "subject": subject,
        "exam": exam,
        "total": plan["total"],
        "completed": plan["completed"],
        "status": plan_status(plan["total"], plan["completed"]),
    }
