from pathlib import Path

import pytest

from diagnostic.catalog import is_valid_answer_shape, load_catalog
from diagnostic.school import load_school

SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"


def question(question_id: str):
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    return next(q for q in catalog.get("demo-math").questions if q.id == question_id)


@pytest.mark.parametrize(
    ("question_id", "answer", "in_progress", "complete"),
    [
        ("q1", "2", True, True),
        ("q1", "9", False, False),
        ("q1", ["2"], False, False),
        ("q2", ["1"], True, False),
        ("q2", ["1", "3"], True, True),
        ("q2", ["1", "1"], False, False),
        ("q2", ["1", "3", "2"], False, False),
        ("q3", {"a": "2"}, True, False),
        ("q3", {"a": "2", "b": "1"}, True, True),
        ("q3", {"a": "2", "zzz": "1"}, False, False),
        ("q4", "42,0", True, True),
        ("q4", "abc", False, False),
    ],
)
def test_partial_answers_pass_only_while_in_progress(question_id, answer, in_progress, complete):
    q = question(question_id)
    assert is_valid_answer_shape(q, answer, complete=False) is in_progress
    assert is_valid_answer_shape(q, answer, complete=True) is complete
