import json
import re
import shutil
from pathlib import Path

import pytest

from diagnostic.catalog import (
    Diagnostic,
    DiagnosticCatalog,
    InputQuestion,
    MatchingQuestion,
    public_question,
    SingleQuestion,
    TextQuestion,
    is_skipped_answer,
    is_valid_answer_shape,
    load_catalog,
)
from diagnostic.school import load_school
from diagnostic.scoring import is_answer_correct

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"
SCHOOL_ROOT = ROOT / "school"


def test_real_word_metadata_and_stress_are_public_without_correct_answers():
    catalog = load_catalog(load_school(SCHOOL_ROOT))
    russian = next(
        question for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.id == "sp-russian-language-ege-2022-q14"
    )
    english = next(
        question for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.id == "sp-english-language-ege-2022-q10"
    )
    stress = next(
        question for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.id == "sp-russian-language-ege-2022-q4"
    )

    assert isinstance(russian, TextQuestion)
    assert (russian.answer_format, russian.lang) == ("words", "ru")
    assert is_answer_correct(russian, "ВСКОРЕ ПОТОМУ") is True
    assert isinstance(english, TextQuestion)
    assert (english.answer_format, english.lang) == ("word", "en")
    assert isinstance(stress, SingleQuestion)
    assert stress.options[2].label == "электропровод"
    assert stress.options[2].stress == "электропрово\u0301д"
    public = public_question(stress)
    assert "correct" not in public
    assert public["options"][2]["stress"] == "электропрово\u0301д"


def test_canonical_skipped_answers_are_recognized_for_every_question_type():
    questions = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math").questions
    skipped_answers = ("", [], {}, "", "")

    for question, answer in zip(questions, skipped_answers, strict=True):
        assert is_skipped_answer(question, answer)


def test_trainer_shape_validation_does_not_accept_skips():
    questions = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math").questions
    skipped_answers = ("", [], {}, "", "")

    for question, answer in zip(questions, skipped_answers, strict=True):
        assert not is_valid_answer_shape(question, answer, complete=True)


@pytest.mark.parametrize("answer", [None, " "])
def test_noncanonical_empty_values_are_not_skipped(answer):
    question = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math").questions[0]

    assert not is_skipped_answer(question, answer)


def test_public_catalog_omits_explanation_and_correct():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    payload = catalog.public_diagnostic("demo-math", "test-secret")

    assert payload["question_count"] == len(payload["questions"])
    assert '"correct"' not in json.dumps(payload, ensure_ascii=False)
    assert '"explanation"' not in json.dumps(payload, ensure_ascii=False)
    assert '"learning_material_text"' not in json.dumps(payload, ensure_ascii=False)
    assert '"learning_material_url"' not in json.dumps(payload, ensure_ascii=False)
    assert '"scoring"' not in json.dumps(payload, ensure_ascii=False)
    assert payload != catalog.public_diagnostic("demo-math", "other-secret")


def test_public_summaries_contain_counts_without_questions():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))

    summaries = catalog.public_summaries("test-secret")

    assert summaries == [
        {
            "id": "demo-math",
            "content_version": catalog.content_version("demo-math", "test-secret"),
            "exam": "demo",
            "subject": "Математика",
            "mark": "Демо",
            "quick_count": 2,
            "full_count": 5,
            "question_count": 5,
        }
    ]
    assert "questions" not in summaries[0]


def test_public_catalog_exposes_primary_score_and_safe_source_attribution():
    data = sample_diagnostic_data()
    data["questions"][0].update(
        max_primary_score=2,
        source={
            "provider": "fipi",
            "official_year": 2026,
            "approval_status": "approved",
            "source_kind": "open_bank",
            "source_url": "https://ege.fipi.ru/bank/questions.php?proj=1&qid=2",
            "fipi_project_id": "1",
            "fipi_question_id": "2",
            "exam_position": "1",
            "official_criteria_url": "https://doc.fipi.ru/ege/specification.pdf",
            "rights_status": "link_only",
            "verified_at": "2026-09-01",
        },
    )

    diagnostic = Diagnostic.model_validate(data)
    catalog = DiagnosticCatalog(diagnostics=(diagnostic,))
    question = catalog.public_diagnostic("demo-math", "test-secret")["questions"][0]

    assert question["max_primary_score"] == 2
    assert question["source"]["provider"] == "fipi"
    assert question["source"]["source_url"].startswith("https://ege.fipi.ru/")
    assert "correct" not in question
    assert "explanation" not in question


@pytest.mark.parametrize(
    ("source_url", "rights_status"),
    [
        ("https://example.com/copied-question", "link_only"),
        ("https://ege.fipi.ru/bank/questions.php", "original"),
    ],
)
def test_fipi_source_requires_an_official_domain_and_valid_rights(
    source_url: str, rights_status: str
):
    data = sample_diagnostic_data()
    data["questions"][0]["source"] = {
        "provider": "fipi",
        "official_year": 2026,
        "approval_status": "approved",
        "source_kind": "open_bank",
        "source_url": source_url,
        "rights_status": rights_status,
        "verified_at": "2026-09-01",
    }

    with pytest.raises(ValueError, match="invalid_fipi_source"):
        Diagnostic.model_validate(data)


def test_catalog_rejects_a_broad_subject_as_a_question_topic():
    data = sample_diagnostic_data()
    data["questions"][0]["topic"] = "Математика"

    with pytest.raises(ValueError, match="question_topic_too_broad"):
        Diagnostic.model_validate(data)


def test_sample_catalog_covers_all_question_types():
    diagnostic = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math")

    assert {question.type for question in diagnostic.questions} == {
        "single",
        "multiple",
        "matching",
        "input",
        "text",
    }


def test_quick_mode_is_stable():
    catalog = load_catalog(load_school())
    diagnostic = catalog.diagnostics[0]

    first = catalog.questions_for_mode(diagnostic.id, "quick")
    second = catalog.questions_for_mode(diagnostic.id, "quick")

    assert [question.id for question in first] == [question.id for question in second]
    assert len(first) == diagnostic.quick_count


def test_full_mode_stops_at_full_count_and_defaults_to_every_question():
    data = sample_diagnostic_data()
    without = Diagnostic.model_validate(data)
    shortened = Diagnostic.model_validate({**data, "full_count": 3})

    assert without.full_count is None
    assert without.full_question_count == len(without.questions)
    assert without.questions_for_mode("full") == without.questions
    assert [question.id for question in shortened.questions_for_mode("full")] == [
        question.id for question in shortened.questions[:3]
    ]
    assert shortened.questions_for_mode("quick") == shortened.questions[
        : shortened.quick_count
    ]


@pytest.mark.parametrize("value", [1, 6, 0, -1])
def test_catalog_rejects_full_count_outside_quick_count_and_question_count(value: int):
    data = sample_diagnostic_data()

    with pytest.raises(ValueError, match="invalid_full_count|greater_than_equal"):
        Diagnostic.model_validate({**data, "full_count": value})


def test_full_count_accepts_its_own_bounds():
    data = sample_diagnostic_data()

    lower = Diagnostic.model_validate({**data, "full_count": 2})
    upper = Diagnostic.model_validate({**data, "full_count": 5})

    assert lower.full_question_count == lower.quick_count == 2
    assert upper.full_question_count == len(upper.questions) == 5


def test_catalog_rejects_diagnostic_with_invalid_option_reference(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    diagnostic_path = school_root / "diagnostics" / "demo-math.json"
    shutil.copyfile("tests/fixtures/invalid-diagnostic.json", diagnostic_path)

    with pytest.raises(ValueError, match="catalog_invalid:demo-math.json"):
        load_catalog(load_school(school_root))


def test_runtime_catalog_errors_do_not_reveal_private_answer_values(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    path = school_root / "diagnostics/demo-math.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    private_probe = "private-answer-probe"
    data["questions"][0]["correct"] = private_probe
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError) as captured:
        load_catalog(load_school(school_root))

    assert str(captured.value) == "catalog_invalid:demo-math.json"
    assert private_probe not in str(captured.value)


def sample_diagnostic_data() -> dict:
    return json.loads(
        (SAMPLE_SCHOOL / "diagnostics/demo-math.json").read_text(encoding="utf-8")
    )


def test_catalog_rejects_multiple_choice_that_cannot_be_answered_correctly():
    data = sample_diagnostic_data()
    data["questions"][1]["correct"] = ["1"]

    with pytest.raises(ValueError, match="invalid_selection_limit"):
        Diagnostic.model_validate(data)


def test_sequence_hint_alone_keeps_a_numeric_task_numeric():
    """KIR-239: the editorial footer "Введите последовательность цифр" sits under
    ordinary numeric tasks too, so it must not turn "200" into a 3-cell sequence."""
    data = sample_diagnostic_data()["questions"][3] | {
        "prompt": (
            "Чему равна удельная теплоёмкость вещества этого тела?\n"
            "Ответ дайте в Дж/(кг·°С).\n"
            "Введите последовательность цифр без пробелов."
        ),
        "correct": ["200"],
    }

    question = InputQuestion.model_validate(data)

    assert question.answer_format == "number"
    assert question.answer_length is None
    assert is_valid_answer_shape(question, "12", complete=True)
    assert is_valid_answer_shape(question, "200,0", complete=True)


def test_kir254_catalog_targets_expose_sequence_contracts():
    expected = {
        "sp-physics-ege-2022-q13": (2, True, ("А", "Б")),
        "sp-chemistry-ege-2022-q6": (2, False, ("А", "Б")),
        "sp-chemistry-ege-2022-q9": (2, False, ("А", "Б")),
        "sp-chemistry-ege-2022-q21": (4, False, ("1", "2", "3", "4")),
        "sp-chemistry-ege-2022-q23": (2, False, ("А", "Б")),
        "sp-biology-ege-2022-q8": (5, False, ("1", "2", "3", "4", "5")),
    }
    catalog = load_catalog(load_school())
    questions = {
        question.id: question
        for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.id in expected
    }

    assert set(questions) == set(expected)
    for question_id, (answer_length, allow_reuse, markers) in expected.items():
        question = questions[question_id]
        assert isinstance(question, InputQuestion)
        assert question.answer_format == "sequence"
        assert question.answer_length == answer_length
        assert question.allow_reuse is allow_reuse
        assert question.markers == markers


def test_numeric_input_accepts_optional_display_unit():
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_unit": "м",
        "correct": ["0,25", "0.25"],
    }
    question = InputQuestion.model_validate(data)
    assert question.answer_unit == "м"


@pytest.mark.parametrize("answer_unit", ["", "   ", "м\u0000", "м" * 33])
def test_numeric_input_rejects_invalid_display_unit(answer_unit: str):
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_unit": answer_unit,
        "correct": ["0,25", "0.25"],
    }
    with pytest.raises(ValueError):
        InputQuestion.model_validate(data)


def test_sequence_input_rejects_numeric_display_unit():
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_format": "sequence",
        "answer_length": 3,
        "allow_reuse": False,
        "markers": ["А", "Б", "В"],
        "answer_unit": "м",
        "correct": ["132"],
    }
    with pytest.raises(ValueError, match="sequence_answer_unit"):
        InputQuestion.model_validate(data)


def test_legacy_sequence_input_infers_contract_four_metadata():
    data = sample_diagnostic_data()["questions"][3] | {
        "prompt": (
            "Установите соответствие между понятиями и определениями.\n"
            "А) Теплопроводность\nБ) Изохорический процесс\nВ) Адиабатический процесс\n"
            "1) Явление передачи тепла\n2) Процесс при постоянном объёме\n"
            "В ответ запишите последовательность цифр, соответствующую буквам АБВ."
        ),
        "correct": ["211"],
    }

    question = InputQuestion.model_validate(data)

    assert question.answer_format == "sequence"
    assert question.answer_length == 3
    assert question.allow_reuse is True
    assert question.markers == ("А", "Б", "В")


def test_ordering_task_infers_a_sequence_from_its_numbered_items():
    data = sample_diagnostic_data()["questions"][3] | {
        "prompt": (
            "Расположите химические элементы\n1) Калий\n2) Алюминий\n3) Литий\n"
            "в порядке ослабления металлических свойств.\n"
            "Запишите номера выбранных элементов в соответствующем порядке."
        ),
        "correct": ["132"],
    }

    question = InputQuestion.model_validate(data)

    assert question.answer_format == "sequence"
    assert question.answer_length == 3
    assert question.allow_reuse is False
    assert question.markers == ("1", "2", "3")


_POSITIONAL_OR_ORDERING = re.compile(
    r"(?m)^\s*[А-ЯЁA-Z]\s*[).|]|соответству\w+\s+буквам|расположите|установите\s+последовательность"
    r"|в\s+порядке|укажите\s+(?:все\s+)?цифр|последовательность\s+цифр,\s+соответству"
    r"|последовательность\s+(?:этап|событ|действ|процесс|реакц|предлож)",
    re.IGNORECASE,
)


def test_school_catalog_only_marks_sequences_that_read_as_sequences():
    """Every sequence question in the shipped catalog must name positions or an order,
    and every correct key must pass the server-side shape check it will be scored with."""
    catalog = load_catalog(load_school())
    offenders = []
    for diagnostic in catalog.diagnostics:
        for question in diagnostic.questions:
            if not isinstance(question, InputQuestion):
                continue
            for variant in question.correct:
                assert is_valid_answer_shape(question, variant, complete=True), (
                    diagnostic.id, question.id, variant
                )
            if question.answer_format == "sequence" and not _POSITIONAL_OR_ORDERING.search(question.prompt):
                offenders.append((diagnostic.id, question.id))
    assert offenders == []


def test_number_input_rejects_sequence_metadata():
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_format": "number",
        "markers": ["1"],
    }

    with pytest.raises(ValueError, match="number_sequence_metadata"):
        InputQuestion.model_validate(data)


def test_sequence_input_requires_consistent_metadata():
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_format": "sequence",
        "answer_length": 3,
        "allow_reuse": False,
        "markers": ["A", "B", "C"],
        "correct": ["211"],
    }

    with pytest.raises(ValueError, match="sequence_reuse_not_allowed"):
        InputQuestion.model_validate(data)


def test_sequence_input_rejects_blank_marker():
    data = sample_diagnostic_data()["questions"][3] | {
        "answer_format": "sequence",
        "answer_length": 2,
        "allow_reuse": False,
        "markers": ["A", " "],
        "correct": ["12"],
    }

    with pytest.raises(ValueError, match="blank_sequence_marker"):
        InputQuestion.model_validate(data)


def test_approved_input_requires_explicit_metadata():
    data = sample_diagnostic_data()["questions"][3] | {
        "source": {
            "provider": "maximum_editorial",
            "official_year": 2026,
            "approval_status": "approved",
            "source_kind": "original",
            "source_url": "https://maximumtest.ru/",
            "rights_status": "original",
            "verified_at": "2026-09-01",
        },
    }

    with pytest.raises(ValueError, match="input_metadata_required"):
        InputQuestion.model_validate(data)


def test_approved_choice_rejects_duplicate_visible_labels():
    data = sample_diagnostic_data()
    data["questions"][0]["source"] = {
        "provider": "maximum_editorial",
        "official_year": 2026,
        "approval_status": "approved",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": "2026-09-01",
    }
    data["questions"][0]["options"][1]["label"] = "3"

    with pytest.raises(ValueError, match="duplicate_option_label"):
        Diagnostic.model_validate(data)


def test_draft_choice_rejects_duplicate_visible_labels():
    data = sample_diagnostic_data()
    data["questions"][0]["options"][1]["label"] = "  3  "

    with pytest.raises(ValueError, match="duplicate_option_label"):
        Diagnostic.model_validate(data)


def _approved_source() -> dict[str, object]:
    return {
        "provider": "maximum_editorial",
        "official_year": 2026,
        "approval_status": "approved",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": "2026-09-01",
    }


def test_approved_sequence_rejects_mixed_marker_scripts():
    data = sample_diagnostic_data()["questions"][3] | {
        "source": _approved_source(),
        "answer_format": "sequence",
        "answer_length": 3,
        "allow_reuse": False,
        "markers": ["A", "Б", "C"],
        "correct": ["123"],
    }

    with pytest.raises(ValueError, match="mixed_sequence_marker_scripts"):
        InputQuestion.model_validate(data)


def test_approved_matching_rejects_placeholder_marker():
    data = sample_diagnostic_data()["questions"][2] | {
        "source": _approved_source(),
        "items": [
            {"id": "a", "label": "___"},
            {"id": "b", "label": "Second"},
        ],
    }

    with pytest.raises(ValueError, match="placeholder_matching_marker"):
        MatchingQuestion.model_validate(data)


def test_approved_matching_rejects_prefixed_placeholder_marker():
    data = sample_diagnostic_data()["questions"][2] | {
        "source": _approved_source(),
        "items": [
            {"id": "a", "label": "А) ___"},
            {"id": "b", "label": "Б) Second"},
        ],
    }

    with pytest.raises(ValueError, match="placeholder_matching_marker"):
        MatchingQuestion.model_validate(data)


def test_approved_matching_rejects_reversed_position_and_option_markers():
    data = sample_diagnostic_data()["questions"][2] | {
        "source": _approved_source(),
        "items": [
            {"id": "a", "label": "1) First"},
            {"id": "b", "label": "2) Second"},
        ],
        "options": [
            {"id": "1", "label": "А) One"},
            {"id": "2", "label": "Б) Two"},
        ],
        "correct": {"a": "1", "b": "2"},
    }

    with pytest.raises(ValueError, match="matching_positions_options_mixed"):
        MatchingQuestion.model_validate(data)


@pytest.mark.parametrize("variant", ["not-a-number", "NaN", "Infinity", "sNaN"])
def test_catalog_rejects_unscoreable_input_correct_variants(variant: str):
    data = sample_diagnostic_data()
    data["questions"][3]["correct"] = [variant]

    with pytest.raises(ValueError, match="invalid_input_variant"):
        Diagnostic.model_validate(data)


@pytest.mark.parametrize("variant", ["1" * 65, "1e1000", " 42", "42 "])
def test_catalog_rejects_input_variants_the_client_cannot_submit(variant: str):
    data = sample_diagnostic_data()
    data["questions"][3]["correct"] = [variant]

    with pytest.raises(ValueError, match="invalid_input_variant"):
        Diagnostic.model_validate(data)


def test_catalog_accepts_large_but_lexically_submitable_decimal():
    data = sample_diagnostic_data()
    data["questions"][3]["correct"] = ["1e999"]

    assert Diagnostic.model_validate(data).questions[3].correct == ("1e999",)


def test_catalog_accepts_structured_prompt_line_breaks():
    data = sample_diagnostic_data()
    data["questions"][0]["prompt"] = "Choose the answer.\nA) First option\nB) Second option"

    assert Diagnostic.model_validate(data).questions[0].prompt.count("\n") == 2


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda data: data.update(id="x" * 65), "string_too_long"),
        (lambda data: data.update(id="valid-id\n"), "string_pattern_mismatch"),
        (lambda data: data.update(subject=" "), "blank_text"),
        (lambda data: data.update(subject="Math\u202e"), "unsafe_text"),
        (lambda data: data.update(subject="School \u5b66"), "unsupported_report_character"),
        (lambda data: data["questions"][0].update(prompt="x" * 10001), "string_too_long"),
        (lambda data: data["questions"][0].update(prompt=" "), "blank_text"),
        (lambda data: data["questions"][0].update(prompt="Bad\tPrompt"), "unsafe_text"),
        (
            lambda data: data["questions"][0].update(prompt="Ready \U0001f600"),
            "unsupported_report_character",
        ),
        (lambda data: data["questions"][0].update(topic="Bad\x00Topic"), "unsafe_text"),
        (lambda data: data["questions"][0]["options"][0].update(label=" "), "blank_text"),
        (lambda data: data["questions"][0]["options"][0].update(label="Bad\nLabel"), "unsafe_text"),
        (lambda data: data["scoring"].update(max_score=1000), "literal_error"),
        (
            lambda data: data["questions"][0].update(
                options=[{"id": str(index), "label": "option"} for index in range(51)]
            ),
            "too_long",
        ),
        (
            lambda data: data.update(
                questions=[
                    {**data["questions"][0], "id": f"q{index}"}
                    for index in range(201)
                ]
            ),
            "too_long",
        ),
    ],
)
def test_catalog_enforces_public_payload_bounds(mutation, error: str):
    data = sample_diagnostic_data()
    mutation(data)

    with pytest.raises(ValueError, match=error):
        Diagnostic.model_validate(data)


def test_catalog_rejects_oversized_json_before_parsing(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    path = school_root / "diagnostics/demo-math.json"
    path.write_bytes(path.read_bytes() + b" " * (1024 * 1024))

    with pytest.raises(ValueError, match="catalog_file_too_large"):
        load_catalog(load_school(school_root))


@pytest.mark.parametrize(
    ("replacement", "error"),
    [
        ('"id": "demo-math", "id": "other-math"', "json_duplicate_key"),
        ('"id": "demo-math", "quick_count": NaN', "json_nonfinite_number"),
    ],
)
def test_catalog_rejects_ambiguous_nonstandard_json(
    tmp_path: Path, replacement: str, error: str
):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    path = school_root / "diagnostics/demo-math.json"
    payload = path.read_text(encoding="utf-8").replace(
        '"id": "demo-math"', replacement, 1
    )
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_catalog(load_school(school_root))


def test_catalog_loads_json_extension_consistently_across_platforms(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    source = school_root / "diagnostics/demo-math.json"
    source.rename(source.with_suffix(".JSON"))

    assert load_catalog(load_school(school_root)).get("demo-math")


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_catalog_rejects_every_unexpected_diagnostics_entry(tmp_path: Path, kind: str):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    unexpected = school_root / "diagnostics/private-notes.txt"
    if kind == "file":
        unexpected.write_text("private", encoding="utf-8")
    else:
        unexpected.mkdir()

    with pytest.raises(ValueError, match="catalog_unexpected_entry"):
        load_catalog(load_school(school_root))


def test_catalog_rejects_case_colliding_filenames_before_platform_deploy():
    from diagnostic.catalog import _validate_catalog_filenames

    with pytest.raises(ValueError, match="catalog_filename_collision"):
        _validate_catalog_filenames(["math.json", "MATH.JSON"])


@pytest.mark.parametrize("filename", ["CON.json", "aux.JSON", "com1.json", "LPT9.JSON"])
def test_catalog_rejects_windows_reserved_filenames(filename: str):
    from diagnostic.catalog import _validate_catalog_filenames

    with pytest.raises(ValueError, match="catalog_unexpected_entry"):
        _validate_catalog_filenames([filename])


def test_catalog_accepts_more_than_300_questions_across_diagnostics():
    first = sample_diagnostic_data()
    first["questions"] = [
        {**first["questions"][0], "id": f"a{index}"} for index in range(151)
    ]
    first["quick_count"] = 1
    second = sample_diagnostic_data()
    second["id"] = "second-math"
    second["questions"] = [
        {**second["questions"][0], "id": f"b{index}"} for index in range(150)
    ]
    second["quick_count"] = 1

    catalog = DiagnosticCatalog(
        diagnostics=(Diagnostic.model_validate(first), Diagnostic.model_validate(second))
    )

    assert sum(len(item.questions) for item in catalog.diagnostics) == 301


def test_catalog_rejects_one_diagnostic_public_payload_over_two_megabytes():
    data = sample_diagnostic_data()
    question = data["questions"][0]
    question["options"] = [
        {"id": f"o{index}", "label": "x" * 249 + str(index)}
        for index in range(50)
    ]
    question["correct"] = "o0"
    data["questions"] = [
        {**question, "id": f"q{index}"} for index in range(200)
    ]
    data["quick_count"] = 1

    with pytest.raises(ValueError, match="catalog_public_payload_too_large"):
        DiagnosticCatalog(diagnostics=(Diagnostic.model_validate(data),))


def test_content_version_changes_when_a_referenced_question_asset_changes(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    asset = school_root / "assets/question.svg"
    asset.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
        '<rect width="20" height="10" fill="#111111"/></svg>',
        encoding="utf-8",
    )
    diagnostic_path = school_root / "diagnostics/demo-math.json"
    data = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    data["questions"][0]["asset"] = "assets/question.svg"
    diagnostic_path.write_text(json.dumps(data), encoding="utf-8")
    first = load_catalog(load_school(school_root)).content_version(
        "demo-math", "test-secret"
    )

    asset.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
        '<rect width="20" height="10" fill="#222222"/></svg>',
        encoding="utf-8",
    )
    second = load_catalog(load_school(school_root)).content_version(
        "demo-math", "test-secret"
    )

    assert first != second


def test_catalog_loads_and_publishes_multiple_question_assets(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    for name, color in (("question-1.svg", "#111111"), ("question-2.svg", "#222222")):
        (school_root / "assets" / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
            f'<rect width="20" height="10" fill="{color}"/></svg>',
            encoding="utf-8",
        )
    diagnostic_path = school_root / "diagnostics/demo-math.json"
    data = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    data["questions"][0]["assets"] = [
        "assets/question-1.svg",
        "assets/question-2.svg",
    ]
    data["questions"][0]["asset_alt"] = "A pair of diagnostic diagrams"
    diagnostic_path.write_text(json.dumps(data), encoding="utf-8")

    catalog = load_catalog(load_school(school_root))
    question = catalog.get("demo-math").questions[0]

    assert question.asset_paths == (
        "assets/question-1.svg",
        "assets/question-2.svg",
    )
    public_question = catalog.public_diagnostic("demo-math", "test-secret")[
        "questions"
    ][0]
    assert public_question["assets"] == [
        "assets/question-1.svg",
        "assets/question-2.svg",
    ]
    assert public_question["asset_alt"] == "A pair of diagnostic diagrams"


@pytest.mark.parametrize("asset_alt", ["", "   "])
def test_catalog_rejects_blank_asset_alt(asset_alt: str):
    data = sample_diagnostic_data()
    data["questions"][0]["asset_alt"] = asset_alt
    with pytest.raises(ValueError, match="blank_text"):
        Diagnostic.model_validate(data)


def test_catalog_allows_null_asset_alt():
    data = sample_diagnostic_data()
    data["questions"][0]["asset_alt"] = None
    assert Diagnostic.model_validate(data).questions[0].asset_alt is None


def test_catalog_rejects_unsafe_asset_alt():
    data = sample_diagnostic_data()
    data["questions"][0]["asset_alt"] = "Схема\u202e"
    with pytest.raises(ValueError, match="unsafe_text"):
        Diagnostic.model_validate(data)
