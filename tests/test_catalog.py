import json
import shutil
from pathlib import Path

import pytest

from diagnostic.catalog import Diagnostic, DiagnosticCatalog, load_catalog
from diagnostic.school import load_school

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"


def test_public_catalog_omits_explanation_and_correct():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    payload = catalog.public_payload("test-secret")

    assert '"correct"' not in json.dumps(payload, ensure_ascii=False)
    assert '"explanation"' not in json.dumps(payload, ensure_ascii=False)
    assert '"learning_material_text"' not in json.dumps(payload, ensure_ascii=False)
    assert '"learning_material_url"' not in json.dumps(payload, ensure_ascii=False)
    assert '"scoring"' not in json.dumps(payload, ensure_ascii=False)
    assert payload != catalog.public_payload("other-secret")


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
    }


def test_quick_mode_is_stable():
    catalog = load_catalog(load_school())
    diagnostic = catalog.diagnostics[0]

    first = catalog.questions_for_mode(diagnostic.id, "quick")
    second = catalog.questions_for_mode(diagnostic.id, "quick")

    assert [question.id for question in first] == [question.id for question in second]
    assert len(first) == diagnostic.quick_count


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
        (lambda data: data["questions"][0].update(prompt="x" * 4001), "string_too_long"),
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


def test_catalog_rejects_more_than_200_questions_across_all_diagnostics():
    first = sample_diagnostic_data()
    first["questions"] = [
        {**first["questions"][0], "id": f"a{index}"} for index in range(101)
    ]
    first["quick_count"] = 1
    second = sample_diagnostic_data()
    second["id"] = "second-math"
    second["questions"] = [
        {**second["questions"][0], "id": f"b{index}"} for index in range(100)
    ]
    second["quick_count"] = 1

    with pytest.raises(ValueError, match="too_many_total_questions"):
        DiagnosticCatalog(diagnostics=(Diagnostic.model_validate(first), Diagnostic.model_validate(second)))


def test_catalog_rejects_bootstrap_payload_over_two_megabytes():
    diagnostics_data = []
    for diagnostic_index in range(2):
        data = sample_diagnostic_data()
        data["id"] = f"large-{diagnostic_index}"
        question = data["questions"][0]
        question["options"] = [
            {"id": f"o{index}", "label": "x" * 250} for index in range(50)
        ]
        question["correct"] = "o0"
        data["questions"] = [
            {**question, "id": f"q{index}"} for index in range(100)
        ]
        data["quick_count"] = 1
        diagnostics_data.append(Diagnostic.model_validate(data))

    with pytest.raises(ValueError, match="catalog_public_payload_too_large"):
        DiagnosticCatalog(diagnostics=tuple(diagnostics_data))


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
    diagnostic_path.write_text(json.dumps(data), encoding="utf-8")

    catalog = load_catalog(load_school(school_root))
    question = catalog.get("demo-math").questions[0]

    assert question.asset_paths == (
        "assets/question-1.svg",
        "assets/question-2.svg",
    )
    public_question = catalog.public_payload("test-secret")["diagnostics"][0][
        "questions"
    ][0]
    assert public_question["assets"] == [
        "assets/question-1.svg",
        "assets/question-2.svg",
    ]
