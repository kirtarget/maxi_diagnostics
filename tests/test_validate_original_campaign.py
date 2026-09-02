from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_original_campaign.py"
MANIFEST = ROOT / "authoring" / "campaigns" / "fipi-2026-min15" / "manifest.json"


def load_tool():
    spec = importlib.util.spec_from_file_location("validate_original_campaign", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_campaign_is_complete_deterministic_and_private_safe(capsys):
    tool = load_tool()

    first = tool.main([], root=ROOT)
    first_output = capsys.readouterr().out
    second = tool.main([], root=ROOT)
    second_output = capsys.readouterr().out

    assert first == second == 0
    assert first_output == second_output
    report = json.loads(first_output)
    assert report == {
        "campaign_id": "fipi-2026-min15",
        "status": "materialized",
        "diagnostics": 19,
        "baseline_questions": 178,
        "additions": 123,
        "projected_questions": 301,
        "partitions": [
            {"id": "a-quantitative-ege", "slots": 41},
            {"id": "b-natural-humanities-ege", "slots": 41},
            {"id": "c-languages-small-oge", "slots": 41},
        ],
        "blockers": 7,
    }
    assert "correct" not in first_output
    assert "prompt" not in first_output
    assert "answer" not in first_output


def test_manifest_records_every_catalog_and_exact_deficit():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(manifest["diagnostics"]) == 19
    assert sum(len(item["slots"]) for item in manifest["diagnostics"]) == 123
    assert sum(item["expected_question_count"] for item in manifest["diagnostics"]) == 178
    assert sum(item["target_question_count"] for item in manifest["diagnostics"]) == 301
    assert all(
        item["target_question_count"]
        == max(manifest["target_min_questions"], item["expected_question_count"])
        for item in manifest["diagnostics"]
    )


def test_validator_rejects_bom_before_parsing(tmp_path: Path, capsys):
    tool = load_tool()
    path = tmp_path / "manifest.json"
    path.write_bytes(b"\xef\xbb\xbf" + MANIFEST.read_bytes())

    result = tool.main(["--manifest", str(path)], root=ROOT)

    assert result == 2
    assert capsys.readouterr().out == "ERROR campaign.manifest.utf8_bom\n"


def test_validator_rejects_duplicate_or_unsafe_slot_without_exposing_content(
    tmp_path: Path, capsys
):
    tool = load_tool()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target = next(
        item for item in manifest["diagnostics"] if item["diagnostic_id"] == "ege-literature-1209"
    )
    target["slots"][1]["question_id"] = target["slots"][0]["question_id"]
    target["slots"][1]["exam_position"] = "10"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = tool.main(["--manifest", str(path)], root=ROOT)

    assert result == 2
    assert capsys.readouterr().out == "ERROR campaign.slot.question_id_invalid\n"


def test_validator_rejects_catalog_drift(tmp_path: Path, capsys):
    tool = load_tool()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target = next(item for item in manifest["diagnostics"] if not item["slots"])
    target["expected_catalog_sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = tool.main(["--manifest", str(path)], root=ROOT)

    assert result == 2
    assert capsys.readouterr().out == "ERROR campaign.catalog.hash_changed\n"
