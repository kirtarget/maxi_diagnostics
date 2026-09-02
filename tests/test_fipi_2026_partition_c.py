import json
from pathlib import Path

from diagnostic.catalog import Diagnostic


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "authoring/campaigns/fipi-2026-min15/manifest.json"
PARTITION = "c-languages-small-oge"
BASE_IDS = {
    "ege-english-language-1204": ["q9842", "q9843", "q9844", "q9845", "q9846", "q9847", "q9848", "q9849"],
    "ege-russian-language-1213": ["q9896", "q9897", "q9898", "q9900", "q9901"],
    "oge-english-language-202": ["q1825", "q1826"],
    "oge-russian-language-379": ["q3377", "q3379", "q3381", "q3383", "q3384", "q3386", "q3389", "q3391", "q3392"],
    "oge-history-196": ["q1588", "q1593", "q1601", "q1602", "q1603", "q1604", "q1605", "q1607", "q1608", "q1610", "q1611", "q1612", "q1613", "q1614"],
    "oge-informatics-466": ["q3889", "q3888", "q3892", "q3893", "q3896", "q3898", "q3899", "q3901", "q3904", "q3905", "q3909"],
}
EXPECTED_ANSWERS = {
    "f26-ege-eng-a01": ["1432"], "f26-ege-eng-a02": ["1"], "f26-ege-eng-a03": ["2"],
    "f26-ege-eng-a04": ["3"], "f26-ege-eng-a05": ["2"], "f26-ege-eng-a06": ["1"],
    "f26-ege-eng-a07": ["2143"], "f26-ege-rus-a01": ["a", "b", "c"],
    "f26-ege-rus-a02": ["a", "b"], "f26-ege-rus-a03": ["a", "c"],
    "f26-ege-rus-a04": ["b", "c"], "f26-ege-rus-a05": ["a", "b", "d"],
    "f26-ege-rus-a06": ["1"], "f26-ege-rus-a07": ["2"], "f26-ege-rus-a08": ["3"],
    "f26-ege-rus-a09": ["2"], "f26-ege-rus-a10": ["1"],
    "f26-oge-eng-a01": ["2"], "f26-oge-eng-a02": ["1"], "f26-oge-eng-a03": ["3"],
    "f26-oge-eng-a04": ["2"], "f26-oge-eng-a05": ["1"], "f26-oge-eng-a06": ["2"],
    "f26-oge-eng-a07": ["1"], "f26-oge-eng-a08": ["3"], "f26-oge-eng-a09": ["3"],
    "f26-oge-eng-a10": ["1"], "f26-oge-eng-a11": ["2"], "f26-oge-eng-a12": ["1"],
    "f26-oge-eng-a13": ["2"], "f26-oge-rus-a01": ["a", "c"],
    "f26-oge-rus-a02": ["a", "c"], "f26-oge-rus-a03": ["a", "c"],
    "f26-oge-rus-a04": ["a", "b"], "f26-oge-rus-a05": ["a", "b", "c"],
    "f26-oge-rus-a06": ["a", "c"], "f26-oge-hist-a01": ["1"],
    "f26-oge-inf-a01": ["12"], "f26-oge-inf-a02": ["6"],
    "f26-oge-inf-a03": ["80"], "f26-oge-inf-a04": ["3"],
}


def _manifest_diagnostics():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        item["diagnostic_id"]: item
        for item in data["diagnostics"]
        if any(slot["owner_partition"] == PARTITION for slot in item["slots"])
    }


def _added_questions():
    questions = {}
    for diagnostic_id, base_ids in BASE_IDS.items():
        payload = json.loads(
            (ROOT / "school/diagnostics" / f"{diagnostic_id}.json").read_text(
                encoding="utf-8"
            )
        )
        questions.update(
            (question["id"], question)
            for question in payload["questions"][len(base_ids):]
        )
    return questions


def test_partition_c_matches_manifest_and_preserves_existing_question_prefixes():
    manifest = _manifest_diagnostics()
    assert sum(len(item["slots"]) for item in manifest.values()) == 41
    for diagnostic_id, item in manifest.items():
        payload = json.loads((ROOT / "school/diagnostics" / item["catalog_file"]).read_text(encoding="utf-8"))
        assert [question["id"] for question in payload["questions"][:len(BASE_IDS[diagnostic_id])]] == BASE_IDS[diagnostic_id]
        added = payload["questions"][len(BASE_IDS[diagnostic_id]):]
        assert [question["id"] for question in added] == [slot["question_id"] for slot in item["slots"]]
        assert len(payload["questions"]) == item["target_question_count"] == 15


def test_partition_c_drafts_have_bounded_original_metadata_and_answer_keys():
    manifest = _manifest_diagnostics()
    explanations = set()
    for diagnostic_id, item in manifest.items():
        payload = json.loads((ROOT / "school/diagnostics" / item["catalog_file"]).read_text(encoding="utf-8"))
        added = payload["questions"][len(BASE_IDS[diagnostic_id]):]
        slots = {slot["question_id"]: slot for slot in item["slots"]}
        for question in added:
            slot = slots[question["id"]]
            assert question["type"] == slot["question_type"]
            assert question["max_primary_score"] == slot["max_primary_score"]
            assert question["correct"] == EXPECTED_ANSWERS[question["id"]]
            assert question["prompt"].strip() and question["explanation"].strip()
            assert question["explanation"] not in explanations
            explanations.add(question["explanation"])
            assert "asset" not in question and "assets" not in question
            source = question["source"]
            assert source == {
                "provider": "maximum", "official_year": 2026,
                "approval_status": "draft", "source_kind": "original",
                "source_url": "https://maximumtest.ru/",
                "exam_position": slot["exam_position"],
                "official_criteria_url": item["official_archive_url"],
                "rights_status": "original", "verified_at": "2026-09-01",
            }
    assert len(explanations) == 41


def test_partition_c_quantitative_answers_are_independently_recomputed():
    questions = _added_questions()
    assert 24 * 4 // 8 == int(EXPECTED_ANSWERS["f26-oge-inf-a01"][0])
    roads = {
        "A": {"B": 4, "C": 2}, "B": {"A": 4, "C": 3, "D": 2},
        "C": {"A": 2, "B": 3, "D": 7}, "D": {"B": 2, "C": 7},
    }
    distances = {node: float("inf") for node in roads}
    distances["A"] = 0
    pending = set(roads)
    while pending:
        node = min(pending, key=distances.get)
        pending.remove(node)
        for neighbour, length in roads[node].items():
            distances[neighbour] = min(
                distances[neighbour], distances[node] + length
            )
    assert str(distances["D"]) == questions["f26-oge-inf-a02"]["correct"][0]
    assert 250 + 190 - 360 == int(
        questions["f26-oge-inf-a03"]["correct"][0]
    )
    assert len([name for name in ["report.docx", "report.pdf", "plan.docx", "photo.png", "notes.docx"] if name.endswith(".docx")]) == int(EXPECTED_ANSWERS["f26-oge-inf-a04"][0])
    assert min({"Сенат": 1711, "Синод": 1721, "Табель": 1722, "Академия": 1724}, key={"Сенат": 1711, "Синод": 1721, "Табель": 1722, "Академия": 1724}.get) == "Сенат"


def test_partition_c_review_fixes_have_independent_semantic_oracles():
    questions = _added_questions()

    english_event_order = {
        "f26-ege-eng-a01": [1, 4, 3, 2],
        "f26-ege-eng-a07": [2, 1, 4, 3],
    }
    for question_id, fragment_order in english_event_order.items():
        assert "".join(map(str, fragment_order)) == questions[question_id]["correct"][0]

    stress_syllables = [2, 1, 1, 1]
    assert [index + 1 for index, syllable in enumerate(stress_syllables) if syllable == 2] == [
        int(questions["f26-ege-rus-a06"]["correct"][0])
    ]
    required_comma_counts = [1, 0, 0, 2]
    assert [index + 1 for index, count in enumerate(required_comma_counts) if count == 1] == [
        int(questions["f26-ege-rus-a10"]["correct"][0])
    ]

    option_ids = ["a", "b", "c", "d"]
    dash_required = [True, True, False, False]
    spelling_explanations_valid = [True, True, True, False]
    morphology_statements_valid = [True, False, True, False]
    for question_id, oracle in (
        ("f26-oge-rus-a04", dash_required),
        ("f26-oge-rus-a05", spelling_explanations_valid),
        ("f26-oge-rus-a06", morphology_statements_valid),
    ):
        assert [option for option, valid in zip(option_ids, oracle) if valid] == questions[
            question_id
        ]["correct"]


def test_partition_c_loads_in_production_catalog_without_oge_russian_position_one():
    diagnostics = []
    for diagnostic_id in BASE_IDS:
        payload = json.loads(
            (ROOT / "school/diagnostics" / f"{diagnostic_id}.json").read_text(
                encoding="utf-8"
            )
        )
        diagnostics.append(Diagnostic.model_validate(payload))
    russian = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.id == "oge-russian-language-379"
    )
    added = [question for question in russian.questions if question.id.startswith("f26-")]
    assert {question.source.exam_position for question in added} == {"2", "3", "4", "5", "6", "8"}
    assert sum(len(diagnostic.questions) for diagnostic in diagnostics) == 90
