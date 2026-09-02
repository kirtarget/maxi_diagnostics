from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from diagnostic.jsonutil import load_json_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = REPOSITORY_ROOT / "school" / "diagnostics" / "ege-mathematics-1212.json"
FIPI_2026_MATH_URL = (
    "https://doc.fipi.ru/ege/demoversii-specifikacii-kodifikatory/2026/"
    "ma_11_2026.zip"
)


def test_original_ege_math_pilot_is_ready_for_expert_review() -> None:
    diagnostic = load_json_file(PILOT_PATH, max_bytes=1024 * 1024)
    questions = {question["id"]: question for question in diagnostic["questions"]}

    expected = {
        "q9891": ("1", "98"),
        "q9892": ("3", "126"),
        "q9894": ("6", "2"),
        "q9895": ("10", "28"),
    }
    assert set(expected) <= set(questions)

    for question_id, (position, answer) in expected.items():
        question = questions[question_id]
        assert question["correct"] == [answer]
        assert question["max_primary_score"] == 1
        assert question["explanation"]
        assert question.get("asset") is None
        assert question.get("assets") is None
        assert question["source"] == {
            "provider": "maximum",
            "official_year": 2026,
            "approval_status": "draft",
            "source_kind": "original",
            "source_url": "https://maximumtest.ru/",
            "exam_position": position,
            "official_criteria_url": FIPI_2026_MATH_URL,
            "rights_status": "original",
            "verified_at": "2026-09-01",
        }


def test_original_ege_math_pilot_answers_are_recomputed() -> None:
    recomputed = {
        "q9891": (Decimal(10) + Decimal(18)) / 2 * Decimal(7),
        "q9892": Decimal(18) * Decimal(7),
        "q9894": (Decimal(3) + 1) / 2,
        "q9895": (Decimal(180) - Decimal(180) * Decimal("0.3") - 42) / 3,
    }
    diagnostic = load_json_file(PILOT_PATH, max_bytes=1024 * 1024)
    questions = {question["id"]: question for question in diagnostic["questions"]}

    for question_id, value in recomputed.items():
        assert Decimal(questions[question_id]["correct"][0]) == value
