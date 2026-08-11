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
