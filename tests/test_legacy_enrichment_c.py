from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "authoring" / "legacy-enrichment" / "manifest.json"
DIAGNOSTICS = ROOT / "school" / "diagnostics"


def _load(path: Path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    return json.loads(raw.decode("utf-8"))


def _digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_partition_c_explanations_preserve_legacy_contract():
    manifest = _load(MANIFEST)
    records = [item for item in manifest["records"] if item["partition"] == "c"]
    approved_answer_changes = set(manifest["approved_answer_changes"])
    approved_prompt_changes = set(manifest["approved_prompt_changes"])
    assert len(records) == 53
    catalogs = {record["file"]: _load(DIAGNOSTICS / record["file"]) for record in records}

    for record in records:
        question = next(item for item in catalogs[record["file"]]["questions"] if item["id"] == record["question_id"])
        label = f'{record["diagnostic_id"]}/{record["question_id"]}'
        if label not in approved_prompt_changes:
            assert _digest(question["prompt"]) == record["prompt_sha256"]
        if label in approved_answer_changes:
            assert _digest(question["correct"]) != record["correct_sha256"]
        else:
            assert _digest(question["correct"]) == record["correct_sha256"]
        assert question["type"] == record["type"]
        assert question["topic"] == record["topic"]
        explanation = question.get("explanation", "")
        assert isinstance(explanation, str) and len(explanation.strip()) >= 40
        assert "—" not in explanation
        assert not explanation.startswith("Правильный ответ")
        assert "ФИПИ" not in explanation and "MAXIMUM" not in explanation
        assert "source" not in question
        assert "max_primary_score" not in question


def _question(file_name: str, question_id: str):
    catalog = _load(DIAGNOSTICS / file_name)
    return next(question for question in catalog["questions"] if question["id"] == question_id)


def test_q9844_has_one_grammatically_valid_collocation():
    question = _question("ege-english-language-1204.json", "q9844")

    assert question["correct"] == "o2"
    assert {option["id"]: option["label"] for option in question["options"]} == {
        "o1": "32) depended",
        "o2": "32) linked",
        "o3": "32) led",
        "o4": "32) resulted",
    }


def test_q9878_excludes_an_unambiguously_non_philosophical_distractor():
    question = _question("ege-literature-1209.json", "q9878")

    assert question["correct"] == ["o1", "o2"]
    assert next(option["label"] for option in question["options"] if option["id"] == "o5") == (
        "5. А.А. Фет – «Шёпот, робкое дыханье…»"
    )


def test_q3391_false_option_states_the_eleven_rubles_were_the_final_payment():
    question = _question("oge-russian-language-379.json", "q3391")

    assert "o4" not in question["correct"]
    assert next(option["label"] for option in question["options"] if option["id"] == "o4") == (
        "В итоге гувернантке выплатили только 11 рублей."
    )


def test_q1551_has_two_unambiguous_similarities_and_two_differences():
    question = _question("oge-social-studies-195.json", "q1551")

    assert "2. Основаны на вере в сверхъестественное" in question["prompt"]
    assert set(question["correct"]) == {"3412", "3421", "4312", "4321"}
