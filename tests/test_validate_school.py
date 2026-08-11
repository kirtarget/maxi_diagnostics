from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_school.py"


def load_tool():
    assert SCRIPT.is_file(), "school validator is missing"
    spec = importlib.util.spec_from_file_location("task9_validate_school", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "tests/fixtures/sample-school", tmp_path / "school")
    return tmp_path


def expected_summary(root: Path) -> str:
    school = load_school(root / "school")
    catalog = load_catalog(school)
    assets = {school.brand.logo}
    assets.update(
        question.asset
        for diagnostic in catalog.diagnostics
        for question in diagnostic.questions
        if question.asset
    )
    return (
        f"OK school={school.brand.school_id} diagnostics={len(catalog.diagnostics)} "
        f"questions={sum(len(item.questions) for item in catalog.diagnostics)} "
        f"assets={len(assets)}\n"
    )


def test_validator_reports_exact_deterministic_sample_counts(capsys):
    result = load_tool().main([], root=ROOT)

    assert result == 0
    assert capsys.readouterr().out == expected_summary(ROOT)


def test_validator_bounds_runtime_only_message_template_errors(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    brand_path = root / "school/brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    brand["messages"]["welcome"] = "Hello {unknown_placeholder}"
    brand_path.write_text(json.dumps(brand, ensure_ascii=False), encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out == "ERROR runtime_invalid: school_config_invalid\n"


def test_validator_accumulates_sorted_asset_errors(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    brand_path = root / "school/brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    brand["logo"] = "assets/missing-logo.svg"
    brand_path.write_text(json.dumps(brand, ensure_ascii=False), encoding="utf-8")
    diagnostic_path = root / "school/diagnostics/demo-math.json"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    diagnostic["questions"][2]["asset"] = "assets/questions/missing.svg"
    diagnostic_path.write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR asset_not_found: assets/missing-logo.svg",
        "ERROR asset_not_found: assets/questions/missing.svg",
        "ERROR asset_unreferenced: assets/logo.svg",
    ]


def test_validator_rejects_duplicate_diagnostics_and_questions(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    source = root / "school/diagnostics/demo-math.json"
    duplicate = json.loads(source.read_text(encoding="utf-8"))
    duplicate["questions"][1]["id"] = duplicate["questions"][0]["id"]
    (root / "school/diagnostics/duplicate.json").write_text(
        json.dumps(duplicate, ensure_ascii=False), encoding="utf-8"
    )

    result = load_tool().main([], root=root)

    assert result == 1
    output = capsys.readouterr().out
    assert "ERROR catalog_invalid: diagnostics/duplicate.json" in output
    assert "Traceback" not in output


def test_validator_reports_global_question_limit_reason(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    source = json.loads(
        (root / "school/diagnostics/demo-math.json").read_text(encoding="utf-8")
    )
    source["id"] = "second-subject"
    source["quick_count"] = 1
    source["questions"] = [
        {**source["questions"][0], "id": f"s{index}"}
        for index in range(197)
    ]
    (root / "school/diagnostics/second-subject.json").write_text(
        json.dumps(source, ensure_ascii=False), encoding="utf-8"
    )

    result = load_tool().main([], root=root)

    assert result == 1
    assert "ERROR catalog_invalid: too_many_total_questions" in capsys.readouterr().out


def test_validator_scopes_question_ids_to_each_diagnostic(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    source = root / "school/diagnostics/demo-math.json"
    second = json.loads(source.read_text(encoding="utf-8"))
    second["id"] = "second-math"
    (root / "school/diagnostics/second.JSON").write_text(
        json.dumps(second, ensure_ascii=False), encoding="utf-8"
    )

    result = load_tool().main([], root=root)

    assert result == 0
    assert capsys.readouterr().out == (
        "OK school=demo-school diagnostics=2 questions=8 assets=1\n"
    )


def test_validator_rejects_oversized_catalog_file_before_parsing(
    tmp_path: Path, capsys
):
    root = sample_root(tmp_path)
    path = root / "school/diagnostics/demo-math.json"
    path.write_bytes(path.read_bytes() + b" " * (1024 * 1024))

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out == (
        "ERROR catalog_too_large: diagnostics/demo-math.json\n"
        "ERROR diagnostics_not_found\n"
    )


def test_validator_rejects_unknown_brand_links_and_catalog_fields(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    for relative in ("school/brand.json", "school/links.json"):
        path = root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        data["unexpected"] = "ignored configuration"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    diagnostic_path = root / "school/diagnostics/demo-math.json"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    diagnostic["unexpected"] = True
    diagnostic_path.write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR brand_invalid: brand.json field=unexpected reason=extra_forbidden",
        "ERROR catalog_invalid: diagnostics/demo-math.json field=unexpected reason=extra_forbidden",
        "ERROR diagnostics_not_found",
        "ERROR links_invalid: links.json field=unexpected reason=extra_forbidden",
    ]


def test_validator_rejects_unsupported_directory_and_oversized_assets(
    tmp_path: Path, capsys
):
    root = sample_root(tmp_path)
    brand_path = root / "school/brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    brand["logo"] = "assets/questions"
    brand_path.write_text(json.dumps(brand, ensure_ascii=False), encoding="utf-8")
    oversized = root / "school/assets/questions/huge.svg"
    oversized.parent.mkdir(parents=True)
    oversized.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    diagnostic_path = root / "school/diagnostics/demo-math.json"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    diagnostic["questions"][2]["asset"] = "assets/questions/huge.svg"
    diagnostic_path.write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR asset_too_large: assets/questions/huge.svg",
        "ERROR asset_unreferenced: assets/logo.svg",
        "ERROR brand_invalid: brand.json field=logo reason=invalid_asset_path",
    ]


def test_validator_runs_without_project_cwd_or_environment_secrets(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env={},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == expected_summary(ROOT)
    assert result.stderr == ""


def test_validator_rejects_unreferenced_files_from_public_assets(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    (root / "school/assets/answers.json").write_text("{}", encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out == "ERROR asset_unreferenced: assets/answers.json\n"


def test_validator_rejects_unexpected_school_root_files(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    (root / "school/notes.txt").write_text("private notes", encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert capsys.readouterr().out == "ERROR school_unexpected_entry\n"


def test_validator_rejects_unexpected_diagnostics_files(tmp_path: Path, capsys):
    root = sample_root(tmp_path)
    (root / "school/diagnostics/private-notes.txt").write_text("private", encoding="utf-8")

    result = load_tool().main([], root=root)

    assert result == 1
    assert "ERROR catalog_unexpected_entry" in capsys.readouterr().out
