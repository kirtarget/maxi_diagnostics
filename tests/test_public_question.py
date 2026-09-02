from pathlib import Path

import pytest

from diagnostic.catalog import (
    InputQuestion,
    MatchingQuestion,
    MultipleQuestion,
    SingleQuestion,
    load_catalog,
    public_question,
    server_only_fields,
)
from diagnostic.school import load_school

SAMPLE_SCHOOL = Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school"
QUESTION_TYPES = (SingleQuestion, MultipleQuestion, MatchingQuestion, InputQuestion)


@pytest.mark.parametrize("model", QUESTION_TYPES)
def test_every_question_type_marks_its_answer_key_server_only(model):
    assert {"correct", "explanation", "learning_material_text", "learning_material_url"} <= server_only_fields(model)


def test_public_question_never_contains_a_server_only_field():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    for diagnostic in catalog.diagnostics:
        for question in diagnostic.questions:
            payload = public_question(question)
            assert not server_only_fields(type(question)) & set(payload), question.id
            assert payload["id"] == question.id and payload["type"] == question.type
