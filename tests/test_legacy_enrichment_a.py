from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from diagnostic.catalog import Diagnostic


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "authoring" / "legacy-enrichment" / "manifest.json"
DIAGNOSTICS = ROOT / "school" / "diagnostics"
EXPECTED_FILES = {
    "oge-chemistry-192.json": 19,
    "oge-mathematics-198.json": 19,
    "oge-physics-197.json": 18,
}
def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    return json.loads(raw.decode("utf-8"))


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_partition_a_explanations_preserve_legacy_contract_and_load() -> None:
    manifest = _load(MANIFEST)
    records = [record for record in manifest["records"] if record["partition"] == "a"]
    approved_answers = set(manifest["approved_answer_changes"])
    approved_prompts = set(manifest["approved_prompt_changes"])
    assert len(records) == 56

    counts = {
        filename: sum(record["file"] == filename for record in records)
        for filename in EXPECTED_FILES
    }
    assert counts == EXPECTED_FILES

    catalogs = {
        filename: _load(DIAGNOSTICS / filename) for filename in EXPECTED_FILES
    }
    for payload in catalogs.values():
        Diagnostic.model_validate(payload)

    explanations: set[str] = set()
    for record in records:
        question = next(
            item
            for item in catalogs[record["file"]]["questions"]
            if item["id"] == record["question_id"]
        )
        assert question["type"] == record["type"]
        assert question.get("topic", "") == record["topic"]
        assert question.get("title", "") == record["title"]
        label = f'{record["diagnostic_id"]}/{record["question_id"]}'
        if label in approved_prompts:
            assert _digest(question["prompt"]) != record["prompt_sha256"]
        else:
            assert _digest(question["prompt"]) == record["prompt_sha256"]
        if label in approved_answers:
            assert _digest(question["correct"]) != record["correct_sha256"]
        else:
            assert _digest(question["correct"]) == record["correct_sha256"]

        explanation = question.get("explanation", "")
        assert isinstance(explanation, str) and explanation.strip() == explanation
        sentences = [part for part in re.split(r"(?<=[.!?])\s+", explanation) if part]
        assert 2 <= len(sentences) <= 4
        assert 40 <= len(explanation) <= 1000
        assert "—" not in explanation
        assert not explanation.startswith("Правильный ответ")
        assert "ФИПИ" not in explanation and "MAXIMUM" not in explanation
        assert "source" not in question
        assert "approval_status" not in question
        assert "max_primary_score" not in question
        assert explanation not in explanations
        explanations.add(explanation)

    assert len(explanations) == 56


def test_q1498_answer_follows_reaction_compatibility() -> None:
    diagnostic = _load(DIAGNOSTICS / "oge-chemistry-192.json")
    question = next(item for item in diagnostic["questions"] if item["id"] == "q1498")

    reagent_set_by_substance = {
        "HNO3_concentrated": 3,
        "Ca(OH)2": 1,
        "O2": 4,
    }
    derived_answer = "".join(str(value) for value in reagent_set_by_substance.values())

    assert derived_answer == "314"
    assert question["correct"] == [derived_answer]


def test_q1496_has_exactly_two_unambiguous_reagents() -> None:
    diagnostic = _load(DIAGNOSTICS / "oge-chemistry-192.json")
    question = next(item for item in diagnostic["questions"] if item["id"] == "q1496")
    labels = {option["id"]: option["label"] for option in question["options"]}

    assert labels["o4"] == "хлорид натрия"
    assert question["correct"] == ["o3", "o5"]
    assert "хлорид натрия" in question["explanation"]
    assert "азотная кислота" not in question["explanation"]


def test_repaired_matching_prompts_request_joined_digits_and_valid_agno3() -> None:
    diagnostic = _load(DIAGNOSTICS / "oge-chemistry-192.json")
    question_ids = {
        "q1487", "q1488", "q1489", "q1495", "q1497",
        "q1498", "q1500", "q1505", "q1507",
    }

    for question in diagnostic["questions"]:
        if question["id"] not in question_ids:
            continue
        assert "через запятую" not in question["prompt"]
        assert "слитной последовательностью цифр без пробелов" in question["prompt"]

    q1507 = next(item for item in diagnostic["questions"] if item["id"] == "q1507")
    assert "AgNO 3" in q1507["prompt"]
    assert "Ag ( NO 3 ) 2" not in q1507["prompt"]


def test_q1633_text_defines_a_41_dm_radius_without_asset() -> None:
    diagnostic = _load(DIAGNOSTICS / "oge-mathematics-198.json")
    question = next(item for item in diagnostic["questions"] if item["id"] == "q1633")

    assert question.get("asset") is None
    assert "шириной 18 дм" in question["prompt"]
    assert "высотой 40 дм" in question["prompt"]
    prompt = question["prompt"].lower()
    assert "центр дуги расположен в середине нижней стороны" in prompt
    assert "дуга проходит через её верхний угол" in prompt
    assert (40**2 + (18 / 2) ** 2) ** 0.5 == 41
    assert question["correct"] == ["41"]


def test_q1656_names_equal_sides_and_external_angle() -> None:
    diagnostic = _load(DIAGNOSTICS / "oge-mathematics-198.json")
    question = next(item for item in diagnostic["questions"] if item["id"] == "q1656")

    assert "AB = AC" in question["prompt"]
    assert "154°" in question["prompt"]
    expected_base_angle = (180 - (180 - 154)) // 2
    assert expected_base_angle == 77
    assert question["correct"] == [str(expected_base_angle)]
