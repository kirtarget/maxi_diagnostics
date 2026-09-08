import json
from pathlib import Path

from diagnostic.catalog import QuestionSource, load_catalog
from diagnostic.review import build_review_snapshot, public_review_items
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests" / "fixtures" / "sample-school"


def test_review_snapshot_formats_every_question_type():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {
            "q1": "1",
            "q2": ["1", "2"],
            "q3": {"a": "1", "b": "2"},
            "q4": "41",
            "q5": "зато",
        },
    )

    assert [item["question_id"] for item in snapshot] == ["q1", "q2", "q3", "q4", "q5"]
    assert snapshot[0]["user_answer"] == "3"
    assert snapshot[0]["expected_answer"] == "4"
    assert snapshot[1]["expected_answer"] == "2/4, 3/6"
    assert snapshot[2]["expected_answer"] == "2 + 2: 4; 3 + 3: 6"
    assert snapshot[3]["expected_answer"] == "42"
    assert snapshot[4]["expected_answer"] == "но / однако"
    assert snapshot[4]["user_answer"] == "зато"
    assert all(item["is_correct"] is False for item in snapshot)
    assert snapshot[1]["answer_preview"] == {
        "kind": "multiple",
        "markers": ["A", "B", "C"],
        "user": ["A", "B"],
        "expected": ["A", "C"],
        "option_labels": {"A": "2/4", "B": "2/3", "C": "3/6"},
    }
    assert snapshot[2]["answer_preview"] == {
        "kind": "matching",
        "markers": ["1", "2"],
        "user": ["1", "2"],
        "expected": ["2", "1"],
        "option_labels": {"1": "6", "2": "4"},
    }


def test_review_snapshot_labels_every_canonical_skip():
    questions = load_catalog(load_school(SAMPLE_SCHOOL)).get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {"q1": "", "q2": [], "q3": {}, "q4": "", "q5": ""},
    )

    assert all(item["user_answer"] == "Ты пропустил задание" for item in snapshot)
    assert all(item["is_correct"] is False for item in snapshot)
    assert all(item["status"] == "skipped" for item in snapshot)
    assert all(item["expected_answer"] != "Ты пропустил задание" for item in snapshot)
    assert all(
        item["user_answer"] == "Ты пропустил задание"
        for item in public_review_items({"review_snapshot": snapshot}) or []
    )


def test_individual_explanation_wins_and_public_review_drops_raw_values():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {
            "q1": "2",
            "q2": ["1", "3"],
            "q3": {"a": "2", "b": "1"},
            "q4": "42",
            "q5": "Однако",
        },
    )
    payload = public_review_items({"review_snapshot": snapshot})

    assert payload is not None
    assert payload[0]["guidance_kind"] == "individual"
    assert payload[0]["guidance"] == "Сложите два и два: получится четыре."
    assert "expected_value" not in payload[0]
    assert "user_value" not in payload[0]
    assert payload[1]["answer_preview"]["kind"] == "multiple"
    assert payload[2]["answer_preview"]["kind"] == "matching"


def test_review_exposes_earned_primary_score_and_safe_source_attribution():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    question = catalog.get("demo-math").questions[0].model_copy(
        update={
            "max_primary_score": 2,
            "source": QuestionSource(
                provider="fipi",
                official_year=2026,
                approval_status="approved",
                source_kind="demo",
                source_url="https://doc.fipi.ru/ege/demo.pdf",
                exam_position="1",
                rights_status="link_only",
                verified_at="2026-09-01",
            ),
        }
    )

    payload = public_review_items(
        {"review_snapshot": build_review_snapshot((question,), {"q1": "2"})}
    )

    assert payload is not None
    assert payload[0]["max_primary_score"] == 2
    assert payload[0]["earned_primary_score"] == 2
    assert payload[0]["source"]["provider"] == "fipi"


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


def test_review_snapshot_and_public_review_preserve_optional_asset_alt():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    question = catalog.get("demo-math").questions[0].model_copy(
        update={"asset_alt": "A number line"}
    )
    snapshot = build_review_snapshot((question,), {"q1": "2"})
    assert snapshot[0]["asset_alt"] == "A number line"
    public = public_review_items({"review_snapshot": snapshot})
    assert public is not None
    assert public[0]["asset_alt"] == "A number line"


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


def test_review_formats_migrated_stress_option_without_exposing_the_key():
    catalog = load_catalog(load_school(ROOT / "school"))
    question = next(
        question for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.id == "sp-russian-language-ege-2022-q4"
    )

    snapshot = build_review_snapshot((question,), {question.id: "c"})

    assert snapshot[0]["expected_answer"] == (
        "электропровод · ударение: электропрово\u0301д"
    )
    assert '"correct":' not in json.dumps(public_review_items({"review_snapshot": snapshot}), ensure_ascii=False)


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

    assert public == [{
        "question_id": "q1",
        "expected_answer": "Эталонный ответ не сохранён",
        "status": "incorrect",
    }]


def test_public_review_keeps_legacy_snapshots_without_optional_preview():
    public = public_review_items({
        "review_snapshot": [{
            "question_id": "legacy-q1",
            "is_correct": False,
            "user_answer": "2",
            "expected_answer": "3",
        }]
    })

    assert public == [{
        "question_id": "legacy-q1",
        "is_correct": False,
        "user_answer": "2",
        "expected_answer": "3",
        "status": "incorrect",
    }]
    assert "answer_preview" not in public[0]


def test_real_oge_physics_sequence_preview_decodes_source_word_list():
    catalog = load_catalog(load_school(ROOT / "school"))
    diagnostic = catalog.get("oge-physics-197")
    question = diagnostic.questions[3]

    snapshot = build_review_snapshot((question,), {question.id: "6714"})

    preview = snapshot[0]["answer_preview"]
    assert preview["kind"] == "sequence"
    assert preview["markers"] == ["А", "Б", "В", "Г"]
    assert preview["expected"] == ["6", "7", "1", "4"]
    assert preview["option_labels"] == {
        "1": "Сила Лоренца",
        "2": "Сила Кулона",
        "3": "Сила Ампера",
        "4": "Перпендикулярно",
        "5": "Параллельно",
        "6": "Электрический",
        "7": "Магнитный",
    }


def test_malformed_nested_preview_is_reduced_to_safe_display_fields():
    public = public_review_items({
        "review_snapshot": [{
            "question_id": "q1",
            "answer_preview": {
                "kind": "multiple",
                "markers": ["A"],
                "user": ["A"],
                "expected": ["B"],
                "expected_value": {"secret": "no"},
                "private_answer": "no",
                "option_labels": {"A": "Option A", "secret": {"answer": "no"}},
            },
        }],
    })

    assert public == [{
        "question_id": "q1",
        "answer_preview": {
            "kind": "multiple",
            "markers": ["A"],
            "user": ["A"],
            "expected": ["B"],
            "option_labels": {"A": "Option A"},
        },
        "status": "incorrect",
    }]
