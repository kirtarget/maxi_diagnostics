from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from diagnostic.daily_plan import (
    MistakeState,
    PlanSource,
    REVIEW_INTERVALS,
    build_daily_plan,
    next_review,
    plan_date_for,
    plan_status,
    plan_summary,
)


TODAY = date(2026, 9, 2)
VERSION = "a" * 64


@dataclass(frozen=True)
class FakeQuestion:
    id: str
    topic: str


def catalog_questions(count: int = 8) -> list[FakeQuestion]:
    topics = ("Алгебра", "Геометрия")
    return [FakeQuestion(f"q{index}", topics[index % 2]) for index in range(count)]


def source(**overrides) -> PlanSource:
    values = {
        "attempt_id": "attempt_1",
        "diagnostic_id": "demo-math",
        "growth_topics": ("Геометрия",),
        "answered_question_ids": frozenset({"q0", "q1"}),
    }
    return PlanSource(**(values | overrides))


def build(**overrides):
    values = {
        "user_id": 42,
        "plan_date": TODAY,
        "content_version": VERSION,
        "source": source(),
        "questions": catalog_questions(),
        "mistakes": (),
    }
    return build_daily_plan(**(values | overrides))


def test_plan_is_deterministic_for_the_same_user_and_day():
    first = build()
    second = build()
    assert first is not None and second is not None
    assert first.question_ids == second.question_ids
    assert first.reasons == second.reasons


def test_plan_order_differs_between_users_and_days():
    baseline = build().question_ids
    assert build(user_id=43).question_ids != baseline or build(plan_date=date(2026, 9, 3)).question_ids != baseline


def test_plan_caps_at_five_questions_and_names_a_reason_for_each():
    plan = build(questions=catalog_questions(20))
    assert plan is not None
    assert len(plan.questions) == 5
    assert set(plan.reasons.values()) <= {"mistake_review", "growth_topic"}
    assert len(set(plan.question_ids)) == 5


def test_due_mistakes_come_first_and_future_reviews_are_skipped():
    plan = build(
        mistakes=(
            MistakeState("q5", review_count=0, next_review_on=TODAY),
            MistakeState("q3", review_count=1, next_review_on=date(2026, 8, 30)),
            MistakeState("q7", review_count=0, next_review_on=date(2026, 9, 9)),
        )
    )
    assert plan is not None
    assert plan.question_ids[:2] == ["q3", "q5"]
    assert plan.reasons["q3"] == "mistake_review"
    assert plan.reasons["q5"] == "mistake_review"
    assert plan.reasons.get("q7") != "mistake_review"


def test_growth_topic_questions_fill_before_the_rest_of_the_diagnostic():
    plan = build(questions=catalog_questions(10))
    assert plan is not None
    growth = [
        question_id for question_id in plan.question_ids
        if int(question_id[1:]) % 2 == 1 and question_id not in {"q1"}
    ]
    assert growth, "growth-topic questions should be preferred"
    assert "q1" not in plan.question_ids[:4] or len(plan.question_ids) == 5


def test_plan_prefers_unseen_growth_questions_over_answered_ones():
    plan = build(
        questions=catalog_questions(6),
        source=source(growth_topics=("Геометрия",), answered_question_ids=frozenset({"q1"})),
    )
    assert plan is not None
    unseen_growth = {"q3", "q5"}
    assert unseen_growth <= set(plan.question_ids)
    assert plan.question_ids.index("q3") < plan.question_ids.index("q1")
    assert plan.question_ids.index("q5") < plan.question_ids.index("q1")


def test_plan_is_none_without_a_source_diagnostic_or_questions():
    assert build(questions=()) is None


def test_spaced_review_intervals_advance_on_correct_and_reset_on_wrong():
    assert REVIEW_INTERVALS == (1, 3, 7)
    count, due = next_review(0, correct=True, today=TODAY)
    assert (count, due) == (1, date(2026, 9, 5))
    count, due = next_review(count, correct=True, today=TODAY)
    assert (count, due) == (2, date(2026, 9, 9))
    count, due = next_review(count, correct=True, today=TODAY)
    assert (count, due) == (3, date(2026, 9, 9))
    assert next_review(3, correct=False, today=TODAY) == (0, date(2026, 9, 3))


def test_plan_date_uses_the_school_timezone():
    late = datetime(2026, 9, 2, 22, 30, tzinfo=timezone.utc)
    assert plan_date_for("Europe/Moscow", late) == date(2026, 9, 3)
    assert plan_date_for("UTC", late) == date(2026, 9, 2)


def test_plan_status_reports_done_only_when_every_question_is_answered():
    assert plan_status(0, 0) == "no_diagnostic"
    assert plan_status(5, 2) == "ready"
    assert plan_status(5, 5) == "done"


class _Catalog:
    def get(self, diagnostic_id):
        if diagnostic_id != "demo-math":
            raise ValueError("diagnostic_not_found")
        return type("D", (), {"subject": "Математика", "exam": "ЕГЭ"})()


def test_plan_summary_is_empty_without_a_plan():
    assert plan_summary(None, _Catalog()) == {
        "plan_date": None, "diagnostic_id": None, "subject": None,
        "exam": None, "total": 0, "completed": 0, "status": "no_diagnostic",
    }


def test_plan_summary_names_the_subject_and_progress():
    summary = plan_summary(
        {
            "plan_date": "2026-09-02", "diagnostic_id": "demo-math",
            "total": 5, "completed": 2,
        },
        _Catalog(),
    )
    assert summary == {
        "plan_date": "2026-09-02", "diagnostic_id": "demo-math",
        "subject": "Математика", "exam": "ЕГЭ",
        "total": 5, "completed": 2, "status": "ready",
    }


def test_today_plan_practises_questions_the_full_diagnostic_leaves_out():
    import asyncio

    from diagnostic.catalog import load_catalog
    from diagnostic.daily_plan import ensure_today_plan
    from diagnostic.db import daily_plan as store
    from diagnostic.school import load_school

    root = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"
    catalog = load_catalog(load_school(root))
    diagnostic = catalog.get("demo-math")
    shortened = diagnostic.model_copy(update={"full_count": 2})
    catalog = catalog.model_copy(update={"diagnostics": (shortened,)})
    captured: dict[str, object] = {}

    async def ensure_plan(*, user_id, plan_date, build):
        captured["plan"] = build(
            store.PlanInputs(
                plan_date=plan_date,
                source=PlanSource(
                    attempt_id="attempt_1",
                    diagnostic_id="demo-math",
                    growth_topics=(),
                    answered_question_ids=frozenset(),
                ),
                mistakes=(),
            )
        )
        return None

    original = store.ensure_plan
    store.ensure_plan = ensure_plan
    try:
        asyncio.run(
            ensure_today_plan(user_id=42, catalog=catalog, application_secret="s" * 32)
        )
    finally:
        store.ensure_plan = original

    plan = captured["plan"]
    assert shortened.full_question_count == 2
    assert len(shortened.questions) == 5
    assert set(plan.question_ids) <= {question.id for question in shortened.questions}
    assert any(
        question_id
        not in {question.id for question in shortened.questions_for_mode("full")}
        for question_id in plan.question_ids
    )
