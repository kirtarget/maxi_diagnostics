from pathlib import Path

import pytest

from diagnostic.catalog import load_catalog
from diagnostic.school import SCORE_SCALES_ADAPTER, load_school
from diagnostic.scoring import score_answers

SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"


def sample_catalog():
    return load_catalog(load_school(SAMPLE_SCHOOL))


def test_server_scores_all_question_types():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "42,0"},
    )

    assert result.correct_count == 4
    assert result.score == 100
    assert result.primary_score == 4
    assert result.max_primary_score == 4


def test_server_weights_accuracy_by_primary_score():
    catalog = sample_catalog()
    diagnostic = catalog.get("demo-math")
    weighted = diagnostic.model_copy(
        update={
            "questions": (
                diagnostic.questions[0].model_copy(update={"max_primary_score": 3}),
                diagnostic.questions[1],
            ),
            "quick_count": 2,
        }
    )
    bounded = catalog.model_copy(update={"diagnostics": (weighted,)})

    result = score_answers(bounded, "demo-math", "full", {"q1": "2"})

    assert result.correct_count == 1
    assert result.question_count == 2
    assert result.primary_score == 3
    assert result.max_primary_score == 4
    assert result.score == 75


def test_topic_strength_uses_primary_score_weighting():
    catalog = sample_catalog()
    diagnostic = catalog.get("demo-math")
    questions = (
        diagnostic.questions[0].model_copy(
            update={"topic": "Общая тема", "max_primary_score": 3}
        ),
        diagnostic.questions[1].model_copy(update={"topic": "Общая тема"}),
    )
    weighted = diagnostic.model_copy(
        update={"questions": questions, "quick_count": 2}
    )
    bounded = catalog.model_copy(update={"diagnostics": (weighted,)})

    result = score_answers(bounded, "demo-math", "full", {"q1": "2"})

    assert result.strong_topics[0].topic == "Общая тема"
    assert result.strong_topics[0].correct_count == 1
    assert result.strong_topics[0].ratio == 0.75


def test_server_rejects_unknown_answer_key():
    with pytest.raises(ValueError, match="unknown_question"):
        score_answers(sample_catalog(), "demo-math", "quick", {"bad": "1"})


@pytest.mark.parametrize("answer", ["sNaN", "NaN", "Infinity"])
def test_server_treats_non_finite_input_as_incorrect(answer: str):
    result = score_answers(sample_catalog(), "demo-math", "full", {"q4": answer})

    assert result.correct_count == 0


@pytest.mark.parametrize("answer", [" 42", "42 ", "1e1000", "1" * 65])
def test_server_treats_unsubmitable_numeric_grammar_as_incorrect(answer: str):
    result = score_answers(sample_catalog(), "demo-math", "full", {"q4": answer})

    assert result.correct_count == 0


def test_score_result_is_immutable_and_exposes_ranked_topics():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "0"},
    )

    with pytest.raises(Exception):
        result.score = 0
    assert len(result.strong_topics) == 2
    assert len(result.growth_topics) == 1
    assert {item.topic for item in result.strong_topics}.isdisjoint(
        item.topic for item in result.growth_topics
    )
    assert result.growth_topics[0].topic == "Уравнения"


@pytest.mark.parametrize("topic_count", [1, 2, 3])
def test_topic_groups_are_disjoint_for_small_diagnostics(topic_count: int):
    catalog = sample_catalog()
    diagnostic = catalog.get("demo-math")
    selected = diagnostic.questions[:topic_count]
    bounded = catalog.model_copy(update={
        "diagnostics": (
            diagnostic.model_copy(update={"questions": selected, "quick_count": topic_count}),
        )
    })
    answers = {question.id: question.correct for question in selected}
    if topic_count > 1:
        answers[selected[-1].id] = "incorrect"

    result = score_answers(bounded, "demo-math", "full", answers)

    assert {item.topic for item in result.strong_topics}.isdisjoint(
        item.topic for item in result.growth_topics
    )


def demo_scale():
    return SCORE_SCALES_ADAPTER.validate_python(
        {
            "scales": [
                {
                    "id": "demo-mathematics",
                    "exam": "demo",
                    "subject": "Математика",
                    "kind": "test_score",
                    "max_primary": 8,
                    "min_pass": 27,
                    "table": [0, 10, 20, 35, 50, 65, 80, 90, 100],
                    "interpolated_primary": [],
                    "notes": "",
                    "source": {
                        "title": "Источник",
                        "url": "https://example.org/scale.pdf",
                        "date": "2026-05-07",
                        "confidence": "secondary",
                    },
                }
            ]
        }
    ).scales[0]


def test_result_carries_no_estimate_without_a_scale():
    result = score_answers(sample_catalog(), "demo-math", "full", {"q1": "2"})

    assert result.estimate is None


def test_result_projects_the_sample_onto_the_exam_scale():
    result = score_answers(
        sample_catalog(), "demo-math", "full", {"q1": "2", "q2": ["1", "3"]},
        demo_scale(),
    )

    assert result.primary_score == 2
    assert result.max_primary_score == 4
    assert result.estimate is not None
    assert result.estimate.scaled_primary == 4
    assert result.estimate.value == 50
    assert result.estimate.sample_size == 4
    assert result.estimate.sample_max_primary == 4
    assert result.estimate.exam_max_primary == 8
    assert result.estimate.min_pass == 27


def test_growth_topics_carry_the_primary_points_still_on_the_table():
    result = score_answers(
        sample_catalog(), "demo-math", "full", {"q1": "2", "q2": ["1", "3"]},
    )

    assert [topic.topic for topic in result.growth_topics] == [
        "Соответствия",
        "Уравнения",
    ]
    assert all(topic.primary_score == 0 for topic in result.growth_topics)
    assert all(topic.max_primary_score == 1 for topic in result.growth_topics)
    assert result.recoverable_primary_score == 2


def test_recoverable_points_are_zero_for_a_perfect_attempt():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "42"},
    )

    assert result.growth_topics == ()
    assert result.recoverable_primary_score == 0
