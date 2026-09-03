from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_editorial_readiness.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("audit_editorial_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "tests" / "fixtures" / "sample-school", tmp_path / "school")
    return tmp_path


def test_current_catalog_report_is_deterministic_private_safe_and_filterable(capsys):
    tool = load_tool()

    first = tool.main(["--diagnostic", "ege-mathematics-1212"], root=ROOT)
    first_output = capsys.readouterr().out
    second = tool.main(["--diagnostic", "ege-mathematics-1212"], root=ROOT)
    second_output = capsys.readouterr().out

    assert first == second == 0
    assert first_output == second_output
    report = json.loads(first_output)
    assert report["summary"]["diagnostics"] == 1
    assert report["summary"]["questions"] == 26
    assert report["summary"]["by_provider"] == {"maximum": 15, "maximum_editorial": 11}
    assert all(item["diagnostic_id"] == "ege-mathematics-1212" for item in report["items"])
    assert all(item["status"] == "draft" for item in report["items"])
    assert "correct" not in first_output
    assert "prompt" not in first_output


def test_require_complete_returns_one_when_machine_gaps_remain(capsys):
    tool = load_tool()

    result = tool.main(
        ["--diagnostic", "ege-mathematics-1212", "--require-complete"],
        root=ROOT,
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out)["summary"]["incomplete"] == 26


def test_complete_runtime_metadata_becomes_reviewed_but_never_approved(tmp_path: Path, capsys):
    tool = load_tool()
    root = sample_root(tmp_path)
    path = root / "school" / "diagnostics" / "demo-math.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for index, question in enumerate(data["questions"], start=1):
        question["max_primary_score"] = 1
        question["explanation"] = "Проверяем каждый шаг решения и получаем указанный ответ."
        question["source"] = {
            "provider": "maximum",
            "official_year": 2026,
            "approval_status": "approved",
            "source_kind": "original",
            "source_url": "https://maximumtest.ru/",
            "exam_position": str(index),
            "official_criteria_url": "https://doc.fipi.ru/example.pdf",
            "rights_status": "original",
            "verified_at": "2026-09-01",
        }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = tool.main(["--require-complete"], root=root)
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert report["summary"]["complete"] == len(data["questions"])
    assert report["summary"]["by_provider"] == {"maximum": len(data["questions"])}
    assert report["summary"]["approved"] == 0
    assert all(item["status"] == "reviewed" for item in report["items"])
    assert all(item["manual_gates"] for item in report["items"])


def test_bom_catalog_is_rejected_before_json_loading(tmp_path: Path, capsys):
    tool = load_tool()
    root = sample_root(tmp_path)
    path = root / "school" / "diagnostics" / "demo-math.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

    result = tool.main([], root=root)

    assert result == 2
    assert capsys.readouterr().out == "ERROR catalog_utf8_bom: demo-math.json\n"


def test_unknown_diagnostic_is_a_stable_error(capsys):
    tool = load_tool()

    result = tool.main(["--diagnostic", "not-present"], root=ROOT)

    assert result == 2
    assert capsys.readouterr().out == "ERROR diagnostic_not_found: not-present\n"
