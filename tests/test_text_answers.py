import unicodedata

import pytest
from pydantic import ValidationError

from diagnostic.catalog import MatchingQuestion, SingleQuestion, TextQuestion, is_valid_answer_shape
from diagnostic.scoring import is_answer_correct
from diagnostic.text_answers import is_valid_text_answer, normalize_text_answer


def text_question(**overrides):
    payload = {
        "id": "q-text",
        "type": "text",
        "topic": "Союзы",
        "title": "Задание 1",
        "prompt": "Выпишите союз.",
        "correct": ["но", "однако"],
    }
    return TextQuestion.model_validate(payload | overrides)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("но", "но"),
        ("  но  ", "но"),
        ("НО", "но"),
        ("Нестерпимая", "нестерпимая"),
        ("ещё", "еще"),
        ("Ёлка", "елка"),
        ("но однако", "но однако"),
        ("но \t\n однако", "но однако"),
        ("однако.", "однако"),
        ("однако!?", "однако"),
        ("однако,", "однако"),
        ("однако;", "однако"),
        ("что-то", "что-то"),
        ("что–то", "что-то"),
        ("что—то", "что-то"),
        (unicodedata.normalize("NFD", "нёбо"), "небо"),
        ("...", ""),
        ("   ", ""),
    ],
)
def test_normalization_folds_the_documented_differences(raw, expected):
    assert normalize_text_answer(raw) == expected


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("но", True),
        ("", False),
        ("   ", False),
        (".", False),
        ("но\x00", False),
        (42, False),
        (["но"], False),
        ("с" * 80, True),
        ("с" * 81, False),
    ],
)
def test_valid_text_answer_checks_type_length_and_content(value, valid):
    assert is_valid_text_answer(value) is valid


def test_max_length_bounds_the_accepted_answer():
    question = text_question(max_length=3, correct=["но"])

    assert is_valid_answer_shape(question, "но", complete=True) is True
    assert is_valid_answer_shape(question, "нооо", complete=True) is False
    assert is_valid_answer_shape(question, ["но"], complete=True) is False


def test_partial_text_answers_use_the_same_shape_rule():
    question = text_question()

    assert is_valid_answer_shape(question, "од", complete=False) is True
    assert is_valid_answer_shape(question, "", complete=False) is False


@pytest.mark.parametrize(
    ("answer", "correct"),
    [
        ("но", True),
        ("  ОДНАКО.  ", True),
        ("Однако", True),
        ("нo", False),
        ("но однако", False),
        ("", False),
        (None, False),
        (["но"], False),
    ],
)
def test_scoring_compares_normalized_forms(answer, correct):
    assert is_answer_correct(text_question(), answer) is correct


def test_yo_and_dash_variants_score_as_the_stored_answer():
    question = text_question(correct=["всё-таки"])

    assert is_answer_correct(question, "все—таки") is True
    assert is_answer_correct(question, "ВСЁ–ТАКИ!") is True

    assert is_answer_correct(
        text_question(correct=["давным-давно"]), "ДАВНЫМ—ДАВНО"
    ) is True


def test_explicit_word_metadata_keeps_q14_spaced_variant_and_acute_significant():
    question = text_question(
        answer_format="words",
        lang="ru",
        correct=["вскорепотому", "вскоре потому"],
    )

    assert is_answer_correct(question, "ВСКОРЕ ПОТОМУ") is True
    assert is_answer_correct(question, "электропрово\u0301д") is False


def test_word_metadata_requires_format_and_language_together():
    with pytest.raises(ValidationError):
        text_question(answer_format="word")
    with pytest.raises(ValidationError):
        text_question(lang="ru")


def test_stress_display_matches_label_and_has_one_combining_acute():
    from diagnostic.catalog import QuestionOption

    option = QuestionOption(
        id="a", label="электропровод", stress="электропрово\u0301д"
    )
    assert option.stress.count("\u0301") == 1
    with pytest.raises(ValidationError):
        QuestionOption(id="a", label="электропровод", stress="другое\u0301")
    with pytest.raises(ValidationError):
        QuestionOption(id="a", label="электропровод", stress="электропрово\u0301\u0301д")
    with pytest.raises(ValidationError, match="stress_must_follow_cyrillic_vowel"):
        QuestionOption(id="a", label="электропровод", stress="электропровд\u0301")


def test_public_single_question_rejects_partial_stress_that_could_reveal_the_key():
    with pytest.raises(ValidationError, match="partial_stress_metadata"):
        SingleQuestion.model_validate({
            "id": "q-stress",
            "type": "single",
            "topic": "Ударение",
            "title": "Задание 4",
            "prompt": "Выпишите слово.",
            "options": [
                {"id": "a", "label": "партер", "stress": "парте\u0301р"},
                {"id": "b", "label": "позвонит"},
            ],
            "correct": "a",
        })


def test_matching_questions_forbid_unsupported_stress_metadata():
    with pytest.raises(ValidationError, match="unsupported_stress_metadata"):
        MatchingQuestion.model_validate({
            "id": "q-matching-stress",
            "type": "matching",
            "topic": "Ударение",
            "title": "Задание 4",
            "prompt": "Установите соответствие.",
            "items": [{"id": "i1", "label": "А"}],
            "options": [{"id": "o1", "label": "партер", "stress": "парте\u0301р"}],
            "correct": {"i1": "o1"},
        })


@pytest.mark.parametrize(
    "correct",
    [
        [],
        ["   "],
        ["..."],
        ["но", "НО."],
        ["но", "но"],
        ["с" * 81],
        ["но\x00"],
        ["но"] * 21,
    ],
)
def test_catalog_rejects_unusable_variant_lists(correct):
    with pytest.raises(ValidationError):
        text_question(correct=correct)


@pytest.mark.parametrize("max_length", [0, 201, 1.5, True])
def test_catalog_bounds_max_length(max_length):
    with pytest.raises(ValidationError):
        text_question(max_length=max_length)


def test_max_length_defaults_to_eighty_and_variants_must_fit_it():
    assert text_question().max_length == 80
    with pytest.raises(ValidationError):
        text_question(max_length=2, correct=["однако"])


def test_distinct_variants_that_differ_only_in_dash_style_collide():
    with pytest.raises(ValidationError):
        text_question(correct=["что-то", "что—то"])


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("«реализм»", "реализм"),
        ('"реализм"', "реализм"),
        ("„реализм“", "реализм"),
        (":реализм", "реализм"),
        ("don’t", "don't"),
        ("don`t", "don't"),
    ],
)
def test_quotation_marks_and_apostrophes_do_not_decide_the_answer(typed, expected):
    assert normalize_text_answer(typed) == normalize_text_answer(expected)


def test_a_hyphen_still_decides_the_answer():
    """In an orthography task the hyphen is the whole question."""
    assert normalize_text_answer("по-моему") != normalize_text_answer("по моему")
    assert not is_answer_correct(text_question(correct=["по-моему"]), "по моему")


def test_quotation_marks_alone_are_not_an_answer():
    assert not is_valid_text_answer("«»")
    assert not is_valid_text_answer("...")
