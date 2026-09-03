from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
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
        "external_additions": 327,
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


def test_catalog_hash_ignores_checkout_line_endings(tmp_path: Path):
    tool = load_tool()
    source = ROOT / "school" / "diagnostics" / "oge-mathematics-198.json"
    lf = source.read_bytes().replace(b"\r\n", b"\n")
    crlf_path = tmp_path / "crlf.json"
    crlf_path.write_bytes(lf.replace(b"\n", b"\r\n"))
    lf_path = tmp_path / "lf.json"
    lf_path.write_bytes(lf)

    _, crlf_payload = tool._load_json(crlf_path, label="catalog")
    _, lf_payload = tool._load_json(lf_path, label="catalog")

    assert crlf_payload == lf_payload == lf


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


def _catalog_copy(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "school" / "diagnostics", tmp_path / "school" / "diagnostics")
    shutil.copytree(
        ROOT / "authoring" / "campaigns", tmp_path / "authoring" / "campaigns"
    )
    return tmp_path


def test_pinned_hash_covers_the_catalog_without_external_additions():
    tool = load_tool()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    spec = next(
        item
        for item in manifest["diagnostics"]
        if item["diagnostic_id"] == "oge-mathematics-198"
    )
    path = ROOT / "school" / "diagnostics" / spec["catalog_file"]
    document, payload = tool._load_json(path, label="catalog")

    scoped, scoped_payload, external = tool._split_external(document, payload)

    assert external == len(document["questions"]) - spec["expected_question_count"]
    assert external > 0
    assert len(scoped["questions"]) == spec["expected_question_count"]
    assert all(
        not question["id"].startswith("sp-") for question in scoped["questions"]
    )
    assert hashlib.sha256(scoped_payload).hexdigest() == spec["expected_catalog_sha256"]


def test_external_additions_must_follow_the_campaign_questions(tmp_path: Path, capsys):
    tool = load_tool()
    root = _catalog_copy(tmp_path)
    path = root / "school" / "diagnostics" / "ege-mathematics-1212.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    questions = document["questions"]
    external = next(item for item in questions if item["id"].startswith("sp-"))
    document["questions"] = [external] + [
        item for item in questions if item is not external
    ]
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = tool.main([], root=root)

    assert result == 2
    assert capsys.readouterr().out == "ERROR campaign.catalog.external_not_appended\n"


def test_one_more_external_addition_leaves_the_campaign_counts_alone(
    tmp_path: Path, capsys
):
    tool = load_tool()
    root = _catalog_copy(tmp_path)
    path = root / "school" / "diagnostics" / "oge-informatics-466.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    extra = json.loads(json.dumps(document["questions"][0]))
    extra["id"] = "sp-extra-probe"
    extra["source"] = {
        "provider": "maximum_editorial",
        "official_year": 2022,
        "approval_status": "draft",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": "2026-09-03",
    }
    document["questions"].append(extra)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    result = tool.main([], root=root)
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert report["baseline_questions"] == 178
    assert report["additions"] == 123
    assert report["projected_questions"] == 301
    assert report["external_additions"] == 328
