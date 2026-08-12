import json
from pathlib import Path

from diagnostic.catalog import load_catalog
from diagnostic.review import build_review_snapshot, public_review_items
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests" / "fixtures" / "sample-school"


def test_review_snapshot_formats_every_question_type():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {"q1": "1", "q2": ["1", "2"], "q3": {"a": "1", "b": "2"}, "q4": "41"},
    )

    assert [item["question_id"] for item in snapshot] == ["q1", "q2", "q3", "q4"]
    assert snapshot[0]["user_answer"] == "3"
    assert snapshot[0]["expected_answer"] == "4"
    assert snapshot[1]["expected_answer"] == "2/4, 3/6"
    assert snapshot[2]["expected_answer"] == "2 + 2: 4; 3 + 3: 6"
    assert snapshot[3]["expected_answer"] == "42"
    assert all(item["is_correct"] is False for item in snapshot)


def test_individual_explanation_wins_and_public_review_drops_raw_values():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "42"},
    )
    payload = public_review_items({"review_snapshot": snapshot})

    assert payload is not None
    assert payload[0]["guidance_kind"] == "individual"
    assert payload[0]["guidance"] == "Сложите два и два: получится четыре."
    assert "expected_value" not in payload[0]
    assert "user_value" not in payload[0]


def test_review_snapshot_freezes_question_options_and_matching_items():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(questions, {})

    assert snapshot[0]["options"] == [
        {"id": "1", "label": "3"},
        {"id": "2", "label": "4"},
    ]
    assert snapshot[1]["options"] == [
        {"id": "1", "label": "2/4"},
        {"id": "2", "label": "2/3"},
        {"id": "3", "label": "3/6"},
    ]
    assert snapshot[2]["items"] == [
        {"id": "a", "label": "2 + 2"},
        {"id": "b", "label": "3 + 3"},
    ]
    assert snapshot[2]["options"] == [
        {"id": "1", "label": "6"},
        {"id": "2", "label": "4"},
    ]
    json.dumps(snapshot, ensure_ascii=False)

    snapshot[0]["options"][0]["label"] = "changed"
    snapshot[2]["items"][0]["label"] = "changed"

    assert questions[0].options[0].label == "3"
    assert questions[2].items[0].label == "2 + 2"


def test_review_snapshot_keeps_a_verified_learning_material_text():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    question = catalog.get("demo-math").questions[0].model_copy(
        update={
            "learning_material_text": "Найдите грамматическую основу: подлежащее и сказуемое."
        }
    )

    snapshot = build_review_snapshot((question,), {})

    assert snapshot[0]["learning_material_text"] == (
        "Найдите грамматическую основу: подлежащее и сказуемое."
    )


def test_review_snapshot_does_not_invent_guidance_without_a_source():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))

    question = catalog.get("demo-math").questions[0].model_copy(
        update={"explanation": None}
    )
    snapshot = build_review_snapshot((question,), {})

    assert snapshot[0]["guidance"] == (
        "Подтверждённый разбор в учебнике MAXIMUM для этого задания пока не добавлен."
    )


def test_public_review_never_exposes_unanswered_as_the_expected_answer():
    public = public_review_items(
        {
            "review_snapshot": [
                {
                    "question_id": "q1",
                    "expected_answer": "Не отвечено",
                    "expected_value": None,
                }
            ]
        }
    )

    assert public == [
        {"question_id": "q1", "expected_answer": "Эталонный ответ не сохранён"}
    ]
