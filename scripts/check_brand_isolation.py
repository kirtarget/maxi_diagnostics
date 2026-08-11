"""Fail when extraction-only source-brand terms leak into distributable text."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERMS_PATH = Path(__file__).resolve().with_name("source_brand_terms.json")
_EXCLUDED_RELATIVE_DIRECTORIES = frozenset(
    {
        (".git",),
        (".venv",),
        (".venv312",),
        ("venv",),
        (".python",),
        ("node_modules",),
        ("miniapp", "node_modules"),
        (".next",),
        (".pytest_cache",),
        ("miniapp", ".next"),
        ("build",),
        ("dist",),
        ("output",),
        ("tmp",),
    }
)
_TEXT_SUFFIXES = frozenset(
    {
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".json", ".yaml", ".yml", ".toml", ".html", ".md", ".rst",
        ".txt", ".css", ".svg", ".sh", ".ps1", ".service", ".ini",
        ".cfg", ".conf", ".env", ".example",
    }
)
_TEXT_NAMES = frozenset(
    {"Dockerfile", "Procfile", "Makefile", ".env.example", ".dockerignore", ".gitignore"}
)
_MAX_TEXT_BYTES = 5 * 1024 * 1024
_ROLLING_BASE = 257
_ROLLING_MASK = (1 << 64) - 1


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _safe_root(root: Path) -> Path:
    if root.is_symlink():
        raise ValueError("root_symlink_not_allowed")
    if not root.exists():
        raise ValueError("root_not_found")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("root_not_directory")
    return resolved


def _load_terms(path: Path) -> tuple[tuple[str, int, int], ...]:
    if path.is_symlink():
        raise ValueError("denylist_invalid")
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(raw_terms, list) or not raw_terms:
        raise ValueError("denylist_invalid")
    terms: list[tuple[str, int, int]] = []
    for term in raw_terms:
        if (
            not isinstance(term, dict)
            or set(term) != {"sha256", "length", "rolling64"}
            or not isinstance(term["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", term["sha256"]) is None
            or not isinstance(term["length"], int)
            or isinstance(term["length"], bool)
            or not 1 <= term["length"] <= 256
            or not isinstance(term["rolling64"], str)
            or re.fullmatch(r"[0-9a-f]{16}", term["rolling64"]) is None
        ):
            raise ValueError("denylist_invalid")
        terms.append((term["sha256"], term["length"], int(term["rolling64"], 16)))
    if len(terms) != len({digest for digest, _length, _rolling in terms}):
        raise ValueError("denylist_invalid")
    return tuple(terms)


def _is_text_path(path: Path) -> bool:
    return path.name in _TEXT_NAMES or path.suffix.lower() in _TEXT_SUFFIXES


def _unescape_regex_literal(value: str) -> str:
    return re.sub(r"\\([.\-_^$*+?{}\[\]\\|()/])", r"\1", value)


def _digest(value: str) -> str:
    return hashlib.sha256(_normalized(value).encode("utf-8")).hexdigest()


def _matches_term(value: str, term: tuple[str, int, int]) -> bool:
    digest, length, _rolling = term
    normalized = _normalized(value)
    return len(normalized) == length and _digest(normalized) == digest


def _is_exact_negative_matcher(
    relative: Path, line: str, term: tuple[str, int, int]
) -> bool:
    if "tests" not in relative.parts:
        return False
    stripped = line.strip()
    python_match = re.fullmatch(
        r'''assert\s+(["'])(.*?)\1(?:\.casefold\(\))?\s+not\s+in\s+[A-Za-z_][A-Za-z0-9_.()\[\]]*''',
        stripped,
    )
    if python_match and _matches_term(python_match.group(2), term):
        return True
    node_match = re.fullmatch(
        r"assert\.doesNotMatch\(\s*[A-Za-z_$][A-Za-z0-9_.$]*\s*,\s*/(.+?)/[iu]*\s*\);",
        stripped,
    )
    if node_match and _matches_term(_unescape_regex_literal(node_match.group(1)), term):
        return True
    contain_match = re.fullmatch(
        r'''expect\(\s*[A-Za-z_$][A-Za-z0-9_.$]*\s*\)\.not\.toContain\(\s*(["'])(.*?)\1\s*\);''',
        stripped,
    )
    if contain_match and _matches_term(contain_match.group(2), term):
        return True
    match_match = re.fullmatch(
        r"expect\(\s*[A-Za-z_$][A-Za-z0-9_.$]*\s*\)\.not\.toMatch\(\s*/(.+?)/[iu]*\s*\);",
        stripped,
    )
    return bool(
        match_match
        and _matches_term(_unescape_regex_literal(match_match.group(1)), term)
    )


def _rolling64(value: str) -> int:
    result = 0
    for character in value:
        result = ((result * _ROLLING_BASE) + ord(character)) & _ROLLING_MASK
    return result


def _term_occurrences(line: str, term: tuple[str, int, int]) -> int:
    digest, length, expected_rolling = term
    decoded_line = _unescape_regex_literal(_normalized(line))
    if len(decoded_line) < length:
        return 0
    highest_power = pow(_ROLLING_BASE, length - 1, 1 << 64)
    rolling = _rolling64(decoded_line[:length])
    matches = 0
    for index in range(len(decoded_line) - length + 1):
        if rolling == expected_rolling:
            candidate = decoded_line[index : index + length]
            if hashlib.sha256(candidate.encode("utf-8")).hexdigest() == digest:
                matches += 1
        next_index = index + length
        if next_index < len(decoded_line):
            rolling = (
                (rolling - ord(decoded_line[index]) * highest_power) * _ROLLING_BASE
                + ord(decoded_line[next_index])
            ) & _ROLLING_MASK
    return matches


def _term_label(term: tuple[str, int, int]) -> str:
    return term[0][:12]


def _read_candidate(path: Path, relative: Path) -> tuple[str | None, str | None]:
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return None, f"ERROR candidate_too_large: {relative.as_posix()}"
        with path.open("rb") as stream:
            payload = stream.read(_MAX_TEXT_BYTES + 1)
    except OSError:
        return None, f"ERROR candidate_unreadable: {relative.as_posix()}"
    if len(payload) > _MAX_TEXT_BYTES:
        return None, f"ERROR candidate_too_large: {relative.as_posix()}"
    try:
        return payload.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"ERROR candidate_not_utf8: {relative.as_posix()}"


def _git(root: Path, *arguments: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(root), *arguments],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise ValueError("history_scan_failed")
    return completed.stdout


def scan_history(root: Path, *, terms_path: Path = DEFAULT_TERMS_PATH) -> list[str]:
    """Scan every blob and commit message reachable from every local Git ref."""
    root = _safe_root(root)
    terms = _load_terms(terms_path)
    if not (root / ".git").exists():
        raise ValueError("history_not_available")
    objects: dict[str, set[str]] = {}
    for line in _git(root, "rev-list", "--objects", "--all").splitlines():
        object_id, separator, raw_path = line.partition(" ")
        if re.fullmatch(r"[0-9a-f]{40,64}", object_id) is None or not separator:
            continue
        relative = Path(raw_path)
        for term in terms:
            if _term_occurrences(relative.as_posix(), term):
                results = {
                    f"ERROR history_brand_path: {object_id}:{relative.as_posix()} "
                    f"term_hash={_term_label(term)}"
                }
                return sorted(results)
        if _is_text_path(relative):
            objects.setdefault(object_id, set()).add(relative.as_posix())

    results: set[str] = set()
    if objects:
        check_input = "\n".join(objects) + "\n"
        metadata = _git(
            root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            input_text=check_input,
        )
        for line in metadata.splitlines():
            object_id, object_type, raw_size = line.split(" ", 2)
            if object_type != "blob":
                continue
            size = int(raw_size)
            paths = sorted(objects.get(object_id, ()))
            if size > _MAX_TEXT_BYTES:
                for path in paths:
                    results.add(f"ERROR history_candidate_too_large: {object_id}:{path}")
                continue
            payload = subprocess.run(
                ["git", "-C", str(root), "cat-file", "blob", object_id],
                capture_output=True,
                check=False,
                timeout=60,
            )
            if payload.returncode != 0 or len(payload.stdout) != size:
                raise ValueError("history_scan_failed")
            try:
                text = payload.stdout.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                for path in paths:
                    results.add(f"ERROR history_candidate_not_utf8: {object_id}:{path}")
                continue
            for line_number, content_line in enumerate(text.splitlines(), 1):
                for term in terms:
                    if _term_occurrences(content_line, term):
                        for path in paths:
                            results.add(
                                f"ERROR history_brand_term: {object_id}:{path}:{line_number} "
                                f"term_hash={_term_label(term)}"
                            )

    log_chunks = _git(root, "log", "--all", "--format=%H%x00%B%x00").split("\x00")
    for index in range(0, len(log_chunks) - 1, 2):
        commit_id, message = log_chunks[index].strip(), log_chunks[index + 1]
        if re.fullmatch(r"[0-9a-f]{40,64}", commit_id) is None:
            continue
        for line_number, content_line in enumerate(message.splitlines(), 1):
            for term in terms:
                if _term_occurrences(content_line, term):
                    results.add(
                        f"ERROR history_brand_commit: {commit_id}:{line_number} "
                        f"term_hash={_term_label(term)}"
                    )
    return sorted(results)


def scan_repository(root: Path, *, terms_path: Path = DEFAULT_TERMS_PATH) -> list[str]:
    root = _safe_root(root)
    terms = _load_terms(terms_path)
    denylist_resolved = terms_path.resolve(strict=True)
    results: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name, reverse=True)
        except OSError:
            relative = directory.relative_to(root).as_posix() or "."
            results.add(f"ERROR candidate_unreadable: {relative}")
            continue
        for path in children:
            relative = path.relative_to(root)
            if relative.parts in _EXCLUDED_RELATIVE_DIRECTORIES:
                continue
            for term in terms:
                if _term_occurrences(relative.as_posix(), term):
                    results.add(
                        f"ERROR brand_path: {relative.as_posix()} term_hash={_term_label(term)}"
                    )
            if path.is_symlink():
                results.add(f"ERROR candidate_symlink: {relative.as_posix()}")
                continue
            if path.is_dir():
                pending.append(path)
                continue
            if path.resolve() == denylist_resolved or not _is_text_path(path):
                continue
            text, error = _read_candidate(path, relative)
            if error:
                results.add(error)
                continue
            assert text is not None
            for line_number, line in enumerate(text.splitlines(), 1):
                for term in terms:
                    occurrence_count = _term_occurrences(line, term)
                    if not occurrence_count:
                        continue
                    results.add(
                        f"ERROR brand_term: {relative.as_posix()}:{line_number} "
                        f"term_hash={_term_label(term)}"
                    )
    return sorted(results)


def main(
    argv: list[str] | None = None, *, root: Path | None = None,
    terms_path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Check source-brand isolation")
    parser.add_argument("--root", help=argparse.SUPPRESS)
    parser.add_argument("--history", action="store_true")
    try:
        arguments = parser.parse_args(argv)
        selected_root = root or (Path(arguments.root) if arguments.root else REPOSITORY_ROOT)
        results = scan_repository(selected_root, terms_path=terms_path or DEFAULT_TERMS_PATH)
        if arguments.history:
            results.extend(
                scan_history(selected_root, terms_path=terms_path or DEFAULT_TERMS_PATH)
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        known = {
            "root_not_found", "root_symlink_not_allowed", "root_not_directory",
            "denylist_invalid", "history_not_available", "history_scan_failed",
        }
        print(f"ERROR {str(exc) if str(exc) in known else 'isolation_check_failed'}")
        return 1
    if results:
        for result in results:
            print(result)
        return 1
    print("OK brand isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
