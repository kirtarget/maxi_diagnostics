from __future__ import annotations

import json
from pathlib import Path

from campaign_catalog import load_campaign_catalog


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "authoring" / "campaigns" / "fipi-2026-min15" / "manifest.json"
FILES = {
    "ege-mathematics-1212": ROOT / "school" / "diagnostics" / "ege-mathematics-1212.json",
    "ege-physics-1206": ROOT / "school" / "diagnostics" / "ege-physics-1206.json",
    "ege-chemistry-1208": ROOT / "school" / "diagnostics" / "ege-chemistry-1208.json",
    "ege-informatics-1205": ROOT / "school" / "diagnostics" / "ege-informatics-1205.json",
}


def _load(path: Path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    return json.loads(raw.decode("utf-8"))


def _calculated_answers() -> dict[str, set[str]]:
    return {
        "f26-ege-math-a01": {str(12 * 7 // 2)},
        "f26-ege-math-a02": {str(4 * 5 * 6)},
        "f26-ege-math-a03": {str((18 + 7) // 5)},
        "f26-ege-math-a04": {str(2400 * 85 // 100)},
        "f26-ege-math-a05": {str(9 * 8)},
        "f26-ege-math-a06": {str(2**2)},
        "f26-ege-math-a07": {str(5 - 1)},
        "f26-ege-math-a08": {str(360 // 72)},
        "f26-ege-math-a09": {str(5**2)},
        "f26-ege-math-a10": {str(round(343 ** (1 / 3)))},
        "f26-ege-math-a11": {str(2**6)},
        "f26-ege-phys-a01": {str((15 - 3) // 4)},
        "f26-ege-phys-a02": {str(2 * 4200 * 5)},
        "f26-ege-phys-a03": {str(12 // 3)},
        "f26-ege-phys-a04": {"o1", "o3"},
        "f26-ege-phys-a05": {str(238 - 4)},
        "f26-ege-phys-a06": {str(12 * 15)},
        "f26-ege-phys-a07": {str(50 - 20)},
        "f26-ege-phys-a08": {str(220 * 2)},
        "f26-ege-phys-a09": {"o1", "o4"},
        "f26-ege-chem-a01": {str(17)},
        "f26-ege-chem-a02": {str(2 + 6 + 2 + 3)},
        "f26-ege-chem-a03": {str(1)},
        "f26-ege-chem-a04": {"o1", "o3"},
        "f26-ege-chem-a05": {"o2", "o4"},
        "f26-ege-chem-a06": {"22.4", "22,4"},
        "f26-ege-chem-a07": {str(16 - 2 - 8)},
        "f26-ege-chem-a08": {"o1", "o3"},
        "f26-ege-chem-a09": {"o2", "o4"},
        "f26-ege-inf-a01": {str(len("00011110") // 2)},
        "f26-ege-inf-a02": {str(48_000 * 16 * 2 * 10 // 8 // 1024)},
        "f26-ege-inf-a03": {str(1 + sum(2 * n for n in range(2, 6)))},
        "f26-ege-inf-a04": {str(len(["0", "10", "110", "111"]))},
        "f26-ege-inf-a05": {str(800 * 600 * 24 // 8 // 1000)},
        "f26-ege-inf-a06": {str((((2 * 2 + 1) * 2 + 1) * 2 + 1) * 2 + 1)},
        "f26-ege-inf-a07": {str(len("000001010111") // 3)},
        "f26-ege-inf-a08": {str(22_050 * 8 * 20 // 8 // 1000)},
        "f26-ege-inf-a09": {str(55)},
        "f26-ege-inf-a10": {str(["00", "01", "1", "01"].count("01"))},
        "f26-ege-inf-a11": {str(2**10)},
        "f26-ege-inf-a12": {str(3 + 2**2 + 3**2 + 4**2)},
    }


def test_partition_a_matches_manifest_and_editorial_contract():
    manifest = _load(MANIFEST)
    specs = {item["diagnostic_id"]: item for item in manifest["diagnostics"] if item["diagnostic_id"] in FILES}
    answers = _calculated_answers()
    seen = set()

    for diagnostic_id, path in FILES.items():
        catalog = load_campaign_catalog(path)
        spec = specs[diagnostic_id]
        additions = {question["id"]: question for question in catalog["questions"] if question["id"].startswith("f26-")}
        assert len(catalog["questions"]) == spec["target_question_count"]
        assert set(additions) == {slot["question_id"] for slot in spec["slots"]}
        for slot in spec["slots"]:
            question = additions[slot["question_id"]]
            seen.add(question["id"])
            assert question["type"] == slot["question_type"]
            assert question["max_primary_score"] == slot["max_primary_score"]
            assert question.get("asset") is None and question.get("assets") is None
            assert question["prompt"].strip() and question["explanation"].strip()
            source = question["source"]
            assert source == {
                "provider": "maximum",
                "official_year": 2026,
                "approval_status": "draft",
                "source_kind": "original",
                "source_url": "https://maximumtest.ru/",
                "exam_position": slot["exam_position"],
                "official_criteria_url": spec["official_archive_url"],
                "rights_status": "original",
                "verified_at": "2026-09-01",
            }
            assert set(question["correct"]) == answers[question["id"]]

    assert len(seen) == 41
    assert set(answers) == seen
