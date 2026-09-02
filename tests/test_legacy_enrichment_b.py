from __future__ import annotations

import hashlib
import json
from pathlib import Path

from diagnostic.catalog import Diagnostic


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


def test_partition_b_explanations_preserve_legacy_contract_and_load():
    manifest = _load(MANIFEST)
    records = [item for item in manifest["records"] if item["partition"] == "b"]
    approved_answers = set(manifest["approved_answer_changes"])
    approved_prompts = set(manifest["approved_prompt_changes"])
    assert len(records) == 54
    catalogs = {record["file"]: _load(DIAGNOSTICS / record["file"]) for record in records}
    for payload in catalogs.values():
        Diagnostic.model_validate(payload)

    explanations = set()
    for record in records:
        question = next(
            item
            for item in catalogs[record["file"]]["questions"]
            if item["id"] == record["question_id"]
        )
        label = f'{record["diagnostic_id"]}/{record["question_id"]}'
        if label in approved_prompts:
            assert _digest(question["prompt"]) != record["prompt_sha256"]
        else:
            assert _digest(question["prompt"]) == record["prompt_sha256"]
        if label in approved_answers:
            assert _digest(question["correct"]) != record["correct_sha256"]
        else:
            assert _digest(question["correct"]) == record["correct_sha256"]
        assert question["type"] == record["type"]
        assert question["topic"] == record["topic"]
        explanation = question.get("explanation", "")
        assert isinstance(explanation, str) and len(explanation.strip()) >= 40
        assert 2 <= explanation.count(".") <= 4
        assert "—" not in explanation
        assert not explanation.startswith("Правильный ответ")
        assert "ФИПИ" not in explanation and "MAXIMUM" not in explanation
        assert "source" not in question
        assert "max_primary_score" not in question
        assert explanation not in explanations
        explanations.add(explanation)
    assert len(explanations) == 54


def test_q9861_semantic_oracle_maps_protein_structure_features():
    question = next(
        item
        for item in _load(DIAGNOSTICS / "ege-biology-1207.json")["questions"]
        if item["id"] == "q9861"
    )
    structure_by_feature = {
        "аминокислотная последовательность": "1",
        "глобула": "3",
        "дисульфидные связи": "3",
        "водородные связи": "2",
        "пептидные связи": "1",
        "свойства и функции белка": "3",
    }
    assert "".join(structure_by_feature.values()) == "133213"
    assert question["correct"] == ["133213"]


def test_q5874_semantic_oracle_rejects_direct_proportionality():
    question = next(
        item
        for item in _load(DIAGNOSTICS / "oge-biology-699.json")["questions"]
        if item["id"] == "q5874"
    )
    observations_supported_by_graph = {
        "prey_change_precedes_predator_change": "o2",
        "predator_2_is_lowest_in_1940": "o3",
    }
    unsupported_claims = {
        "competition_is_proven": "o1",
        "populations_are_directly_proportional": "o4",
        "peak_heights_coincide": "o5",
    }

    assert set(observations_supported_by_graph.values()).isdisjoint(
        unsupported_claims.values()
    )
    assert question["correct"] == list(observations_supported_by_graph.values())


def test_q5881_semantic_oracle_maps_fish_class_features():
    question = next(
        item
        for item in _load(DIAGNOSTICS / "oge-biology-699.json")["questions"]
        if item["id"] == "q5881"
    )
    class_by_feature = {
        "gill_covers": "2",
        "internal_fertilization": "1",
        "swim_bladder": "2",
        "mostly_external_fertilization": "2",
        "no_gill_covers": "1",
        "includes_chimaeras": "1",
    }

    assert "".join(class_by_feature.values()) == "212211"
    assert question["correct"] == ["212211"]
    assert "внутреннее оплодотворение" in question["prompt"]


def test_q5891_semantic_oracle_follows_direct_food_web_arrows():
    question = next(
        item
        for item in _load(DIAGNOSTICS / "oge-biology-699.json")["questions"]
        if item["id"] == "q5891"
    )
    change_when_hawks_increase = {
        "frog_without_direct_hawk_link": "3",
        "owl_eaten_by_hawk": "2",
    }

    assert "".join(change_when_hawks_increase.values()) == "32"
    assert question["correct"] == ["32"]
