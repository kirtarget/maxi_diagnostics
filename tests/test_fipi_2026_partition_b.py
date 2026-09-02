from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "school" / "diagnostics"
MANIFEST = ROOT / "authoring" / "campaigns" / "fipi-2026-min15" / "manifest.json"
EXPECTED = {
    "ege-biology-1207": (6, 9, "bi_11_2026.zip"),
    "ege-history-1211": (5, 10, "is_11_2026.zip"),
    "ege-literature-1209": (3, 12, "li_11_2026.zip"),
    "ege-social-studies-1210": (5, 10, "ob_11_2026.zip"),
}
EXPECTED_ANSWERS = {
    "f26-ege-bio-a01": ["o1", "o3"],
    "f26-ege-bio-a02": ["12"],
    "f26-ege-bio-a03": ["1212"],
    "f26-ege-bio-a04": ["o1", "o4"],
    "f26-ege-bio-a05": ["3142"],
    "f26-ege-bio-a06": ["o2", "o4"],
    "f26-ege-bio-a07": ["600"],
    "f26-ege-bio-a08": ["1221"],
    "f26-ege-bio-a09": ["o1", "o3"],
    "f26-ege-hist-a01": ["123"],
    "f26-ege-hist-a02": ["1234"],
    "f26-ege-hist-a03": ["123"],
    "f26-ege-hist-a04": ["1234"],
    "f26-ege-hist-a05": ["o1", "o2", "o4"],
    "f26-ege-hist-a06": ["123"],
    "f26-ege-hist-a07": ["1234"],
    "f26-ege-hist-a08": ["123"],
    "f26-ege-hist-a09": ["1234"],
    "f26-ege-hist-a10": ["o1", "o3", "o5"],
    "f26-ege-lit-a01": ["1234"],
    "f26-ege-lit-a02": ["o1", "o3"],
    "f26-ege-lit-a03": ["1234"],
    "f26-ege-lit-a04": ["o2", "o4"],
    "f26-ege-lit-a05": ["1234"],
    "f26-ege-lit-a06": ["o1", "o4"],
    "f26-ege-lit-a07": ["1234"],
    "f26-ege-lit-a08": ["o2", "o3"],
    "f26-ege-lit-a09": ["1234"],
    "f26-ege-lit-a10": ["o1", "o4"],
    "f26-ege-lit-a11": ["1234"],
    "f26-ege-lit-a12": ["o2", "o3"],
    "f26-ege-soc-a01": ["o1", "o3"],
    "f26-ege-soc-a02": ["o2", "o4"],
    "f26-ege-soc-a03": ["o1", "o4"],
    "f26-ege-soc-a04": ["o3"],
    "f26-ege-soc-a05": ["1212"],
    "f26-ege-soc-a06": ["o1", "o4"],
    "f26-ege-soc-a07": ["o2", "o3"],
    "f26-ege-soc-a08": ["o1", "o3"],
    "f26-ege-soc-a09": ["o2", "o4"],
    "f26-ege-soc-a10": ["o2", "o4"],
}


def _answer(question: dict) -> list[str]:
    correct = question["correct"]
    return correct if isinstance(correct, list) else [correct]


def test_partition_b_adds_exact_manifest_slots_with_draft_original_metadata():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    planned = {
        slot["question_id"]: slot
        for diagnostic in manifest["diagnostics"]
        for slot in diagnostic["slots"]
        if slot["owner_partition"] == "b-natural-humanities-ege"
    }
    seen: dict[str, dict] = {}
    for diagnostic_id, (baseline, additions, archive) in EXPECTED.items():
        path = DIAGNOSTICS / f"{diagnostic_id}.json"
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
        diagnostic = json.loads(path.read_text(encoding="utf-8"))
        assert len(diagnostic["questions"]) == baseline + additions == 15
        new_questions = diagnostic["questions"][baseline:]
        assert len(new_questions) == additions
        for question in new_questions:
            source = question["source"]
            assert source["provider"] == "maximum"
            assert source["official_year"] == 2026
            assert source["approval_status"] == "draft"
            assert source["source_kind"] == source["rights_status"] == "original"
            assert source["official_criteria_url"].endswith(archive)
            slot = planned[question["id"]]
            assert source["exam_position"] == slot["exam_position"]
            assert question["type"] == slot["question_type"]
            assert question["max_primary_score"] == slot["max_primary_score"]
            assert question["max_primary_score"] >= 1
            assert len(question["prompt"]) >= 20
            assert len(question["explanation"]) >= 40
            assert not any(key.startswith("asset") for key in question)
            seen[question["id"]] = question
    assert set(seen) == set(EXPECTED_ANSWERS)
    assert set(seen) == set(planned)
    assert len({item["prompt"] for item in seen.values()}) == 41
    assert len({item["explanation"] for item in seen.values()}) == 41


def test_partition_b_answers_match_independently_recorded_fact_checks():
    actual: dict[str, list[str]] = {}
    for diagnostic_id in EXPECTED:
        document = json.loads(
            (DIAGNOSTICS / f"{diagnostic_id}.json").read_text(encoding="utf-8")
        )
        for question in document["questions"]:
            if question["id"].startswith("f26-"):
                actual[question["id"]] = _answer(question)
    assert actual == EXPECTED_ANSWERS


def test_literature_uses_only_short_answer_positions_and_no_long_extracts():
    document = json.loads(
        (DIAGNOSTICS / "ege-literature-1209.json").read_text(encoding="utf-8")
    )
    new_questions = document["questions"][3:]
    assert {item["source"]["exam_position"] for item in new_questions} == {"2", "8"}
    assert all(len(item["prompt"]) < 1000 for item in new_questions)
    assert all("позиция 10" not in item["prompt"].casefold() for item in new_questions)


def test_reviewed_wording_keeps_historical_and_literary_distinctions_precise():
    documents = {
        diagnostic_id: json.loads(
            (DIAGNOSTICS / f"{diagnostic_id}.json").read_text(encoding="utf-8")
        )
        for diagnostic_id in EXPECTED
    }
    questions = {
        question["id"]: question
        for document in documents.values()
        for question in document["questions"]
    }
    assert "основание города на Неве" in questions["f26-ege-hist-a08"]["prompt"]
    assert "основание новой столицы" not in questions["f26-ege-hist-a08"]["prompt"]
    assert "социально-философская драма" in questions["f26-ege-lit-a05"]["prompt"]
    assert questions["f26-ege-lit-a08"]["prompt"].count("дружбой") == 2
    assert "молекулярных инструмента" in questions["f26-ege-bio-a09"]["prompt"]
    assert "органических веществ из углекислого газа" in questions["f26-ege-bio-a03"]["prompt"]
