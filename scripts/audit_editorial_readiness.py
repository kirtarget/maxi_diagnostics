"""Read-only machine-readiness audit for original MAXIMUM question metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from diagnostic.catalog import load_catalog  # noqa: E402
from diagnostic.jsonutil import load_json_file  # noqa: E402
from diagnostic.school import load_school  # noqa: E402


_MAX_CATALOG_BYTES = 1024 * 1024
_OFFICIAL_YEAR = 2026
_MANUAL_GATES = (
    "answer_truth",
    "explanation_quality",
    "score_applicability",
    "originality",
    "human_approval",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit machine-readable editorial readiness without approving content."
        )
    )
    parser.add_argument(
        "--diagnostic",
        action="append",
        default=[],
        help="Diagnostic ID to include. May be repeated.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return 1 when any selected question has machine-detectable gaps.",
    )
    return parser


def _raw_catalogs(school_root: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    diagnostics_root = school_root / "diagnostics"
    try:
        paths = tuple(sorted(diagnostics_root.iterdir(), key=lambda path: path.name.casefold()))
    except OSError:
        return {}, "ERROR catalog_invalid\n"
    raw: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            return {}, "ERROR catalog_invalid\n"
        if payload.startswith(b"\xef\xbb\xbf"):
            return {}, f"ERROR catalog_utf8_bom: {path.name}\n"
        try:
            document = load_json_file(path, max_bytes=_MAX_CATALOG_BYTES)
        except ValueError:
            return {}, f"ERROR catalog_invalid: {path.name}\n"
        diagnostic_id = document.get("id") if isinstance(document, dict) else None
        if not isinstance(diagnostic_id, str) or diagnostic_id in raw:
            return {}, f"ERROR catalog_invalid: {path.name}\n"
        raw[diagnostic_id] = document
    return raw, None


def _source_gaps(source) -> list[str]:
    if source is None:
        return ["source_missing"]
    gaps: list[str] = []
    if source.provider.casefold() != "maximum":
        gaps.append("source_provider_not_maximum")
    if source.official_year != _OFFICIAL_YEAR:
        gaps.append("source_year_not_approved_2026")
    if source.approval_status != "approved":
        gaps.append("source_approval_not_approved")
    if source.source_kind != "original":
        gaps.append("source_kind_not_original")
    if source.rights_status != "original":
        gaps.append("source_rights_not_original")
    if not source.exam_position:
        gaps.append("source_exam_position_missing")
    if not source.official_criteria_url:
        gaps.append("source_criteria_url_missing")
    if source.verified_at is None:
        gaps.append("source_verified_at_missing")
    return gaps


def _question_gaps(question, raw_question: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if "max_primary_score" not in raw_question:
        gaps.append("max_primary_score_missing")
    if not question.explanation:
        gaps.append("explanation_missing")
    gaps.extend(_source_gaps(question.source))
    return sorted(gaps)


def _report(catalog, raw: dict[str, dict[str, Any]], selected: set[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    diagnostic_count = 0
    for diagnostic in sorted(catalog.diagnostics, key=lambda item: item.id):
        if selected and diagnostic.id not in selected:
            continue
        diagnostic_count += 1
        raw_questions = {
            item.get("id"): item
            for item in raw[diagnostic.id].get("questions", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for question in sorted(diagnostic.questions, key=lambda item: item.id):
            gaps = _question_gaps(question, raw_questions.get(question.id, {}))
            items.append(
                {
                    "diagnostic_id": diagnostic.id,
                    "exam": diagnostic.exam,
                    "subject": diagnostic.subject,
                    "question_id": question.id,
                    "status": "draft" if gaps else "reviewed",
                    "complete": not gaps,
                    "gaps": gaps,
                    "manual_gates": list(_MANUAL_GATES),
                }
            )
    complete = sum(item["complete"] for item in items)
    return {
        "schema_version": 1,
        "approval_policy": "human_only",
        "summary": {
            "diagnostics": diagnostic_count,
            "questions": len(items),
            "complete": complete,
            "incomplete": len(items) - complete,
            "approved": 0,
        },
        "items": items,
    }


def main(argv: list[str] | None = None, *, root: Path = REPOSITORY_ROOT) -> int:
    arguments = _parser().parse_args(argv)
    school_root = root / "school"
    raw, error = _raw_catalogs(school_root)
    if error is not None:
        print(error, end="")
        return 2
    try:
        school = load_school(school_root)
        catalog = load_catalog(school)
    except (OSError, ValueError):
        print("ERROR catalog_invalid")
        return 2
    available = {diagnostic.id for diagnostic in catalog.diagnostics}
    selected = set(arguments.diagnostic)
    missing = sorted(selected - available)
    if missing:
        print(f"ERROR diagnostic_not_found: {missing[0]}")
        return 2
    report = _report(catalog, raw, selected)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if arguments.require_complete and report["summary"]["incomplete"]:
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
