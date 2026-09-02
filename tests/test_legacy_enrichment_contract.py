from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "authoring" / "legacy-enrichment" / "manifest.json"
DIAGNOSTICS = ROOT / "school" / "diagnostics"


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_every_registered_legacy_question_has_an_individual_explanation() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["baseline_missing_explanations"] == 163
    assert manifest["partition_counts"] == {"a": 56, "b": 54, "c": 53}

    diagnostics = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in DIAGNOSTICS.glob("*.json")
    }
    explanations: set[str] = set()
    answer_changes: list[str] = []
    prompt_changes: list[str] = []
    for record in manifest["records"]:
        diagnostic = diagnostics[record["file"]]
        question = next(
            item
            for item in diagnostic["questions"]
            if item["id"] == record["question_id"]
        )
        label = f'{record["diagnostic_id"]}/{record["question_id"]}'
        assert question["type"] == record["type"]
        assert question.get("topic", "") == record["topic"]
        assert question.get("title", "") == record["title"]
        if digest(question["prompt"]) != record["prompt_sha256"]:
            prompt_changes.append(label)

        explanation = question["explanation"]
        assert isinstance(explanation, str)
        assert 30 <= len(explanation) <= 2000
        assert "—" not in explanation
        assert not explanation.lower().startswith("правильный ответ")
        assert explanation not in explanations
        explanations.add(explanation)

        if digest(question["correct"]) != record["correct_sha256"]:
            answer_changes.append(label)

    assert sorted(answer_changes) == sorted(manifest["approved_answer_changes"])
    assert sorted(prompt_changes) == sorted(manifest["approved_prompt_changes"])
    assert len(explanations) == 163
