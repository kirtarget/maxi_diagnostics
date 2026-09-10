"""Completing the onboarding diagnostic seeds the topic path. Needs PostgreSQL."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import attempts, topic_progress
from diagnostic.db.core import close_db, init_db


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

VERSION = "a" * 64
DIAGNOSTIC = "math-10"


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    yield
    await close_db()


def new_user_id() -> int:
    return 9_600_000_000 + uuid4().int % 100_000_000


def review_item(question_id: str, topic: str, *, correct: bool) -> dict:
    return {
        "question_id": question_id,
        "topic": topic,
        "is_correct": correct,
        "user_value": "A",
        "expected_value": "A" if correct else "B",
    }


def completion(attempt_id: str, user_id: int, items: list[dict], *, revision: int = 1):
    return attempts.AttemptCompletion(
        attempt_id=attempt_id,
        user_id=user_id,
        diagnostic_id=DIAGNOSTIC,
        content_version=VERSION,
        exam="ege",
        subject="math",
        mode="quick",
        question_count=len(items),
        progress_revision=revision,
        answers={item["question_id"]: "A" for item in items},
        correct_count=sum(1 for item in items if item["is_correct"]),
        score=50,
        max_score=100,
        score_unit="points",
        unassessed_part=None,
        report_snapshot={"review_snapshot": items},
    )


@pytest.mark.asyncio
async def test_completion_seeds_only_correct_answers_per_topic():
    user_id = new_user_id()
    attempt_id = f"seed-{uuid4()}"
    items = [
        review_item("q1", "Алгебра", correct=True),
        review_item("q2", "Геометрия", correct=False),
    ]
    await attempts.complete_attempt(completion(attempt_id, user_id, items))

    progress = await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION)
    assert progress["Алгебра"].correct_ids == frozenset({"q1"})
    # A wrong answer never seeds its topic.
    assert "Геометрия" not in progress
    # A quick subset never prematurely stamps done_at.
    assert progress["Алгебра"].done_at is None


@pytest.mark.asyncio
async def test_re_completion_and_supersede_never_double_seed():
    user_id = new_user_id()
    first_attempt = f"seed-{uuid4()}"
    items = [review_item("q1", "Алгебра", correct=True)]
    await attempts.complete_attempt(completion(first_attempt, user_id, items))
    # A replay of the same completed attempt returns the immutable result.
    await attempts.complete_attempt(completion(first_attempt, user_id, items))

    # A later attempt that also gets q1 right unions to the same single id.
    second_attempt = f"seed-{uuid4()}"
    await attempts.complete_attempt(
        completion(second_attempt, user_id, items, revision=1)
    )

    progress = await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION)
    assert progress["Алгебра"].correct_ids == frozenset({"q1"})
