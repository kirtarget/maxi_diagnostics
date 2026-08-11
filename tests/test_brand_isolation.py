from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_brand_isolation.py"
TERMS_PATH = ROOT / "scripts" / "source_brand_terms.json"


def load_tool():
    assert SCRIPT.is_file(), "brand isolation gate is missing"
    spec = importlib.util.spec_from_file_location("task9_brand_isolation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configured_terms() -> list[str]:
    return [
        "oldbrand",
        "legacy.example",
        "legacy_diagnostic_bot",
        "legacy-repository",
        "Старая школа",
        "legacy-credentials.json",
    ]


def write_terms(root: Path, relative: str = "hashed_terms.json") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "terms": [
                    {
                        "sha256": hashlib.sha256(
                            unicodedata.normalize("NFC", term).casefold().encode("utf-8")
                        ).hexdigest(),
                        "length": len(
                            unicodedata.normalize("NFC", term).casefold()
                        ),
                        "rolling64": f"{rolling64(unicodedata.normalize('NFC', term).casefold()):016x}",
                    }
                    for term in configured_terms()
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def rolling64(value: str) -> int:
    result = 0
    for character in value:
        result = ((result * 257) + ord(character)) & ((1 << 64) - 1)
    return result


def term_label(term: str) -> str:
    return hashlib.sha256(
        unicodedata.normalize("NFC", term).casefold().encode("utf-8")
    ).hexdigest()[:12]


def test_rolling_prefilter_avoids_per_window_sha256_on_large_safe_text(monkeypatch):
    tool = load_tool()
    term = configured_terms()[0].casefold()
    digest = hashlib.sha256(term.encode("utf-8")).hexdigest()
    calls = 0
    original = tool.hashlib.sha256

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(tool.hashlib, "sha256", counted)

    assert tool._term_occurrences("," * 1_000_000, (digest, len(term), rolling64(term))) == 0
    assert calls == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
def test_history_scan_rejects_a_term_deleted_from_the_current_checkout(
    tmp_path: Path, capsys,
):
    leak = tmp_path / "README.md"
    leak.write_text(configured_terms()[0], encoding="utf-8")
    for arguments in (
        ("init",),
        ("config", "user.name", "Isolation Test"),
        ("config", "user.email", "isolation@example.test"),
        ("add", "README.md"),
        ("commit", "-m", "historical fixture"),
    ):
        subprocess.run(
            ["git", "-C", str(tmp_path), *arguments],
            check=True, capture_output=True, text=True,
        )
    leak.write_text("safe current content", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-am", "clean fixture"],
        check=True, capture_output=True, text=True,
    )

    result = load_tool().main(
        ["--history"], root=tmp_path, terms_path=write_terms(tmp_path)
    )

    assert result == 1
    assert "ERROR history_brand_term:" in capsys.readouterr().out


def make_symlink_or_mock(
    link: Path, target: Path, mocked_links: set[Path], *, directory: bool = False
) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        if directory:
            link.mkdir()
        else:
            link.write_bytes(b"placeholder")
        mocked_links.add(link)


def test_brand_isolation_passes_current_repository(capsys):
    result = load_tool().main([], root=ROOT)

    assert result == 0
    assert capsys.readouterr().out == "OK brand isolation\n"


def test_brand_isolation_catches_each_term_in_runtime_docs_deploy_and_tests(
    tmp_path: Path, capsys
):
    paths = [
        Path("backend/leak.py"),
        Path("miniapp/app/leak.ts"),
        Path("README.md"),
        Path("deploy/docker-compose.yml"),
        Path("tests/test_positive_leak.py"),
        Path(".env.example"),
    ]
    terms = configured_terms()
    assert len(paths) == len(terms)
    for relative, term in zip(paths, terms, strict=True):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"positive leak: {term}\n", encoding="utf-8")

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    output = capsys.readouterr().out.splitlines()
    assert len(output) == len(terms)
    for relative, term in zip(paths, terms, strict=True):
        assert (
            f"ERROR brand_term: {relative.as_posix()}:1 "
            f"term_hash={term_label(term)}"
        ) in output


def test_brand_isolation_rejects_plaintext_terms_even_in_negative_assertions(
    tmp_path: Path, capsys
):
    term = configured_terms()[0]
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_negative.py").write_text(
        f'assert "{term}" not in rendered\n', encoding="utf-8"
    )
    (tests / "test_positive.py").write_text(
        f'EXPECTED_BRAND = "{term}"\n', encoding="utf-8"
    )

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        f"ERROR brand_term: tests/test_negative.py:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/test_positive.py:1 term_hash={term_label(term)}",
    ]


def test_brand_isolation_scans_scripts_and_only_excludes_the_actual_denylist(
    tmp_path: Path, capsys
):
    term = configured_terms()[1]
    leaked_script = tmp_path / "deploy/install.ps1"
    leaked_script.parent.mkdir(parents=True)
    leaked_script.write_text(term, encoding="utf-8")
    misleading_name = tmp_path / "backend/source_brand_terms.json"
    misleading_name.parent.mkdir(parents=True)
    misleading_name.write_text(json.dumps({"leak": term}), encoding="utf-8")

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        f"ERROR brand_term: backend/source_brand_terms.json:1 term_hash={term_label(term)}",
        f"ERROR brand_term: deploy/install.ps1:1 term_hash={term_label(term)}",
    ]


def test_brand_isolation_excludes_only_precise_generated_paths_and_denylist(
    tmp_path: Path, capsys
):
    term = configured_terms()[0]
    for relative in (
        "node_modules/leak.js",
        ".next/leak.js",
        ".pytest_cache/leak.md",
        "dist/leak.js",
        "output/leak.md",
        "tmp/leak.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(term, encoding="utf-8")
    local_terms = write_terms(tmp_path, "scripts/source_brand_terms.json")

    result = load_tool().main([], root=tmp_path, terms_path=local_terms)

    assert result == 0
    assert capsys.readouterr().out == "OK brand isolation\n"


def test_brand_isolation_scans_nested_runtime_school_asset_service_and_rst(
    tmp_path: Path, capsys
):
    term = configured_terms()[2]
    paths = (
        Path("school/assets/logo.svg"),
        Path("backend/cache/config.py"),
        Path("backend/cache/build/config.py"),
        Path("deploy/diagnostic.service"),
        Path("docs/operator.rst"),
    )
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"text={term}\n", encoding="utf-8")

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        f"ERROR brand_term: {path.as_posix()}:1 term_hash={term_label(term)}"
        for path in sorted(paths)
    ]


def test_plaintext_terms_are_rejected_in_every_test_assertion_form(
    tmp_path: Path, capsys
):
    term = configured_terms()[1]
    tests = tmp_path / "tests"
    tests.mkdir()
    escaped_term = term.replace(".", "\\.")
    (tests / "valid.py").write_text(f'assert "{term}" not in rendered\n', encoding="utf-8")
    (tests / "valid.mjs").write_text(
        f"assert.doesNotMatch(output, /{escaped_term}/i);\n",
        encoding="utf-8",
    )
    (tests / "valid.test.ts").write_text(
        f'expect(output).not.toContain("{term}");\n', encoding="utf-8"
    )
    (tests / "invalid.py").write_text(
        f'assert "{term}" not in rendered; leaked = "{term}"\n'
        f'assert "{term}" not in rendered  # {term}\n'
        f'assert "{term}" in rendered\n',
        encoding="utf-8",
    )

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        *[
            f"ERROR brand_term: tests/invalid.py:{line} term_hash={term_label(term)}"
            for line in (1, 2, 3)
        ],
        f"ERROR brand_term: tests/valid.mjs:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.py:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.test.ts:1 term_hash={term_label(term)}",
    ]


def test_brand_isolation_normalizes_unicode_before_matching(tmp_path: Path, capsys):
    term = next(value for value in configured_terms() if not value.isascii())
    decomposed = unicodedata.normalize("NFD", term)
    path = tmp_path / "docs/brand.rst"
    path.parent.mkdir(parents=True)
    path.write_text(decomposed, encoding="utf-8")

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out == (
        f"ERROR brand_term: docs/brand.rst:1 term_hash={term_label(term)}\n"
    )


def test_brand_isolation_checks_normalized_binary_asset_paths(tmp_path: Path, capsys):
    term = next(value for value in configured_terms() if not value.isascii())
    decomposed = unicodedata.normalize("NFD", term)
    path = tmp_path / f"school/assets/{decomposed}-logo.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"binary")

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out == (
        f"ERROR brand_path: {path.relative_to(tmp_path).as_posix()} "
        f"term_hash={term_label(term)}\n"
    )


def test_brand_isolation_fails_closed_for_invalid_utf8_and_oversized_text(
    tmp_path: Path, capsys
):
    invalid = tmp_path / "backend/invalid.py"
    invalid.parent.mkdir(parents=True)
    invalid.write_bytes(b"\xff\xfe")
    oversized = tmp_path / "docs/oversized.rst"
    oversized.parent.mkdir(parents=True)
    oversized.write_bytes(b"x" * (5 * 1024 * 1024 + 1))

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR candidate_not_utf8: backend/invalid.py",
        "ERROR candidate_too_large: docs/oversized.rst",
    ]


def test_brand_isolation_fails_closed_for_unreadable_candidate(
    tmp_path: Path, capsys, monkeypatch
):
    tool = load_tool()
    blocked = tmp_path / "backend/blocked.py"
    blocked.parent.mkdir(parents=True)
    blocked.write_text("safe", encoding="utf-8")
    original_open = Path.open

    def deny_open(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)

    result = tool.main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out == "ERROR candidate_unreadable: backend/blocked.py\n"


def test_brand_isolation_reports_candidate_symlink_without_following(
    tmp_path: Path, capsys, monkeypatch
):
    tool = load_tool()
    outside = tmp_path.parent / "outside-brand-leak.py"
    outside.write_text(configured_terms()[0], encoding="utf-8")
    link = tmp_path / "backend/linked.py"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except OSError:
        link.write_text("safe", encoding="utf-8")
        original = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda path: True if path == link else original(path)
        )

    result = tool.main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out == "ERROR candidate_symlink: backend/linked.py\n"


def test_brand_isolation_excludes_generated_but_rejects_binary_symlinks(
    tmp_path: Path, capsys, monkeypatch
):
    tool = load_tool()
    term = configured_terms()[1]
    outside = tmp_path.parent / "isolation-generated-target"
    outside.mkdir(exist_ok=True)
    (outside / "leak.js").write_text(term, encoding="utf-8")
    binary_target = tmp_path.parent / "isolation-binary-target"
    binary_target.write_text(term, encoding="utf-8")
    mocked_links: set[Path] = set()
    links = (
        (tmp_path / "node_modules", outside, True),
        (tmp_path / "output", outside, True),
        (tmp_path / "school/assets/logo.png", binary_target, False),
        (tmp_path / "school/assets/report-font.ttf", binary_target, False),
    )
    for link, target, is_directory in links:
        make_symlink_or_mock(
            link, target, mocked_links, directory=is_directory
        )
    if mocked_links:
        original = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: True if path in mocked_links else original(path),
        )

    result = tool.main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR candidate_symlink: school/assets/logo.png",
        "ERROR candidate_symlink: school/assets/report-font.ttf",
    ]


def test_brand_isolation_fails_for_text_and_runtime_directory_symlinks(
    tmp_path: Path, capsys, monkeypatch
):
    tool = load_tool()
    outside_file = tmp_path.parent / "isolation-svg-target"
    outside_file.write_text("safe", encoding="utf-8")
    outside_dir = tmp_path.parent / "isolation-runtime-target"
    outside_dir.mkdir(exist_ok=True)
    mocked_links: set[Path] = set()
    svg_link = tmp_path / "school/assets/logo.svg"
    runtime_link = tmp_path / "backend/runtime"
    make_symlink_or_mock(svg_link, outside_file, mocked_links)
    make_symlink_or_mock(
        runtime_link, outside_dir, mocked_links, directory=True
    )
    if mocked_links:
        original = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: True if path in mocked_links else original(path),
        )

    result = tool.main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        "ERROR candidate_symlink: backend/runtime",
        "ERROR candidate_symlink: school/assets/logo.svg",
    ]


def test_regex_escaped_plaintext_terms_are_always_rejected(
    tmp_path: Path, capsys
):
    term = configured_terms()[1]
    tests = tmp_path / "tests"
    tests.mkdir()
    escaped_dot = term.replace(".", r"\.")
    escaped_hyphen = escaped_dot.replace("-", r"\-")
    (tests / "valid.mjs").write_text(
        f"assert.doesNotMatch(output, /{escaped_dot}/i);\n"
        f"assert.doesNotMatch(output, /{escaped_hyphen}/i);\n",
        encoding="utf-8",
    )
    (tests / "valid.test.ts").write_text(
        f"expect(output).not.toMatch(/{escaped_dot}/i);\n"
        f"expect(output).not.toMatch(/{escaped_hyphen}/i);\n",
        encoding="utf-8",
    )
    (tests / "invalid.mjs").write_text(
        f"assert.doesNotMatch(output, /{escaped_hyphen}/i); leak();\n",
        encoding="utf-8",
    )
    (tests / "invalid.test.ts").write_text(
        f"expect(output).not.toMatch(/{escaped_hyphen}/i); leak();\n",
        encoding="utf-8",
    )

    result = load_tool().main([], root=tmp_path, terms_path=write_terms(tmp_path))

    assert result == 1
    assert capsys.readouterr().out.splitlines() == [
        f"ERROR brand_term: tests/invalid.mjs:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/invalid.test.ts:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.mjs:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.mjs:2 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.test.ts:1 term_hash={term_label(term)}",
        f"ERROR brand_term: tests/valid.test.ts:2 term_hash={term_label(term)}",
    ]
