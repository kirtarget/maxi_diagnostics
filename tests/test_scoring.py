from pathlib import Path

import pytest

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
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
