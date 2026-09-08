from pathlib import Path

import pytest

from diagnostic.catalog import InputQuestion, load_catalog
from diagnostic.school import SCORE_SCALES_ADAPTER, load_school
from diagnostic.scoring import is_answer_correct, score_answers

SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"


def sample_catalog():
    return load_catalog(load_school(SAMPLE_SCHOOL))


def test_server_scores_all_question_types():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {
            "q1": "2",
            "q2": ["1", "3"],
            "q3": {"a": "2", "b": "1"},
            "q4": "42,0",
            "q5": "  ОДНАКО.  ",
        },
    )

    assert result.correct_count == 5
    assert result.score == 100
    assert result.primary_score == 5
    assert result.max_primary_score == 5


def test_server_counts_canonical_skips_as_incorrect():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {"q1": "", "q2": [], "q3": {}, "q4": "", "q5": ""},
    )

    assert result.correct_count == 0
    assert result.skipped_count == 5
    assert result.question_count == 5
    assert result.score == 0


def test_server_result_exposes_only_safe_per_question_outcomes():
    result = score_answers(
        sample_catalog(), "demo-math", "full",
        {"q1": "2", "q2": [], "q3": {}, "q4": "", "q5": ""},
    )

    assert [item.model_dump() for item in result.per_question] == [
        {"question_id": "q1", "number": 1, "topic": "Вычисления", "status": "correct", "is_correct": True},
        {"question_id": "q2", "number": 2, "topic": "Дроби", "status": "skipped", "is_correct": False},
        {"question_id": "q3", "number": 3, "topic": "Соответствия", "status": "skipped", "is_correct": False},
        {"question_id": "q4", "number": 4, "topic": "Уравнения", "status": "skipped", "is_correct": False},
        {"question_id": "q5", "number": 5, "topic": "Союзы", "status": "skipped", "is_correct": False},
    ]


def test_real_chemistry_catalog_freezes_official_semantic_topics():
    catalog = load_catalog(load_school())
    result = score_answers(catalog, "oge-chemistry-192", "full", {})
    by_id = {item.question_id: item.topic for item in result.per_question}

    assert by_id["sp-chemistry-oge-2022-q9"] == "Химические свойства неорганических веществ"
    assert by_id["sp-chemistry-oge-2022-q15"] == "Окислительно-восстановительные реакции"
    assert all(not topic.startswith("Задание ") for topic in by_id.values())


def test_every_canonical_skip_is_an_incorrect_answer():
    questions = sample_catalog().get("demo-math").questions
    skipped_answers = ("", [], {}, "", "")

    for question, answer in zip(questions, skipped_answers, strict=True):
        assert not is_answer_correct(question, answer)


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


@pytest.mark.parametrize("answer", ["42,0", "42.0"])
def test_server_normalizes_decimal_separators(answer: str):
    result = score_answers(sample_catalog(), "demo-math", "full", {"q4": answer})

    assert result.correct_count == 1


def test_server_normalizes_unicode_minus_for_negative_answers():
    question = InputQuestion.model_validate({
        "id": "negative-input",
        "type": "input",
        "topic": "Числа",
        "title": "Задание 1",
        "prompt": "Введите число.",
        "correct": ["-3"],
    })

    assert is_answer_correct(question, "−3")


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
    assert len(result.growth_topics) == 2
    assert {item.topic for item in result.strong_topics}.isdisjoint(
        item.topic for item in result.growth_topics
    )
    assert result.growth_topics[0].topic == "Союзы"


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


def test_a_perfect_quick_result_does_not_imply_a_perfect_exam():
    catalog = load_catalog(load_school())
    diagnostic = catalog.get("ege-mathematics-1212")
    questions = diagnostic.questions_for_mode("quick")
    result = score_answers(
        catalog, diagnostic.id, "quick",
        {
            question.id: question.correct[0]
            if question.type in {"input", "text"} else question.correct
            for question in questions
        },
        load_school().scale_for(diagnostic.exam, diagnostic.subject),
    )
    assert result.correct_count == result.question_count == diagnostic.quick_count
    assert result.accuracy_percent == 100
    assert result.estimate is None


def test_result_does_not_project_the_sample_onto_the_exam_scale():
    result = score_answers(
        sample_catalog(), "demo-math", "full", {"q1": "2", "q2": ["1", "3"]},
        demo_scale(),
    )

    assert result.primary_score == 2
    assert result.max_primary_score == 5
    assert result.estimate is None
    assert result.accuracy_percent == 40


def test_growth_topics_carry_the_primary_points_still_on_the_table():
    result = score_answers(
        sample_catalog(), "demo-math", "full", {"q1": "2", "q2": ["1", "3"]},
    )

    assert [topic.topic for topic in result.growth_topics] == [
        "Соответствия",
        "Союзы",
    ]
    assert all(topic.primary_score == 0 for topic in result.growth_topics)
    assert all(topic.max_primary_score == 1 for topic in result.growth_topics)
    assert result.recoverable_primary_score == 2


def test_recoverable_points_are_zero_for_a_perfect_attempt():
    result = score_answers(
        sample_catalog(),
        "demo-math",
        "full",
        {
            "q1": "2",
            "q2": ["1", "3"],
            "q3": {"a": "2", "b": "1"},
            "q4": "42",
            "q5": "но",
        },
    )

    assert result.growth_topics == ()
    assert result.recoverable_primary_score == 0
