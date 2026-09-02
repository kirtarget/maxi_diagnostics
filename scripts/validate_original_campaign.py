"""Validate an add-only original-content campaign without reading answer content."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT
    / "authoring"
    / "campaigns"
    / "fipi-2026-min15"
    / "manifest.json"
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QUESTION_TYPES = {"input", "single", "multiple", "matching"}


class CampaignError(ValueError):
    pass


def _fail(code: str) -> None:
    raise CampaignError(code)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("campaign.manifest.duplicate_key")
        result[key] = value
    return result


def _load_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except OSError:
        _fail(f"campaign.{label}.unreadable")
    if payload.startswith(b"\xef\xbb\xbf"):
        _fail(f"campaign.{label}.utf8_bom")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _fail(f"campaign.{label}.invalid_utf8")
    try:
        value = json.loads(text, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, CampaignError):
        _fail(f"campaign.{label}.invalid_json")
    if not isinstance(value, dict):
        _fail(f"campaign.{label}.invalid_shape")
    return value, payload


def _keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the deterministic plan for original draft questions."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def validate_campaign(manifest_path: Path, diagnostics_root: Path) -> dict[str, Any]:
    manifest, _ = _load_json(manifest_path, label="manifest")
    _keys(
        manifest,
        {
            "schema_version",
            "campaign_id",
            "official_year",
            "target_min_questions",
            "baseline",
            "defaults",
            "partitions",
            "known_blockers",
            "diagnostics",
        },
        "campaign.manifest.schema_invalid",
    )
    if (
        manifest["schema_version"] != 1
        or manifest["campaign_id"] != "fipi-2026-min15"
        or manifest["official_year"] != 2026
        or manifest["target_min_questions"] != 15
    ):
        _fail("campaign.manifest.contract_changed")

    baseline = manifest["baseline"]
    if not isinstance(baseline, dict):
        _fail("campaign.baseline.invalid")
    _keys(
        baseline,
        {"diagnostic_count", "question_count", "additions", "projected_question_count"},
        "campaign.baseline.invalid",
    )
    if baseline != {
        "diagnostic_count": 19,
        "question_count": 178,
        "additions": 123,
        "projected_question_count": 301,
    }:
        _fail("campaign.baseline.changed")

    defaults = manifest["defaults"]
    if defaults != {
        "operation": "add",
        "workflow_status": "draft",
        "source_kind": "original",
        "rights_status": "original",
        "assets_policy": "none",
        "quick_count_policy": "preserve",
    }:
        _fail("campaign.defaults.unsafe")

    diagnostics = _list(manifest["diagnostics"], "campaign.diagnostics.invalid")
    diagnostic_ids = [item.get("diagnostic_id") for item in diagnostics if isinstance(item, dict)]
    if len(diagnostic_ids) != len(diagnostics):
        _fail("campaign.diagnostic.invalid")
    if diagnostic_ids != sorted(diagnostic_ids):
        _fail("campaign.diagnostic.not_sorted")
    if len(set(diagnostic_ids)) != len(diagnostic_ids):
        _fail("campaign.diagnostic.duplicate")

    actual_paths = sorted(diagnostics_root.glob("*.json"), key=lambda item: item.name)
    if [path.name for path in actual_paths] != [f"{item}.json" for item in diagnostic_ids]:
        _fail("campaign.catalog.inventory_changed")

    existing_question_ids: set[str] = set()
    question_owner: dict[str, str] = {}
    actual: dict[str, tuple[str, int, list[str], dict[str, Any]]] = {}
    for path in actual_paths:
        document, payload = _load_json(path, label="catalog")
        diagnostic_id = document.get("id")
        questions = document.get("questions")
        if not isinstance(diagnostic_id, str) or not isinstance(questions, list):
            _fail("campaign.catalog.invalid_shape")
        for question in questions:
            question_id = question.get("id") if isinstance(question, dict) else None
            if not isinstance(question_id, str) or question_id in existing_question_ids:
                _fail("campaign.catalog.question_id_invalid")
            existing_question_ids.add(question_id)
            question_owner[question_id] = diagnostic_id
        actual[diagnostic_id] = (
            hashlib.sha256(payload).hexdigest(),
            len(questions),
            [question["id"] for question in questions],
            document,
        )

    slots_seen: set[str] = set()
    slot_partitions: Counter[str] = Counter()
    baseline_count = 0
    projected_count = 0
    for item in diagnostics:
        _keys(
            item,
            {
                "diagnostic_id",
                "catalog_file",
                "expected_catalog_sha256",
                "expected_question_count",
                "target_question_count",
                "official_archive_url",
                "exam_level",
                "allowlist",
                "slots",
            },
            "campaign.diagnostic.schema_invalid",
        )
        diagnostic_id = item["diagnostic_id"]
        if not isinstance(diagnostic_id, str) or not _ID.fullmatch(diagnostic_id):
            _fail("campaign.diagnostic.id_invalid")
        if item["catalog_file"] != f"{diagnostic_id}.json":
            _fail("campaign.diagnostic.filename_mismatch")
        expected_hash = item["expected_catalog_sha256"]
        if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
            _fail("campaign.catalog.hash_invalid")
        actual_hash, actual_count, actual_ids, actual_document = actual[diagnostic_id]
        expected_count = item["expected_question_count"]
        target_count = max(manifest["target_min_questions"], expected_count)
        if item["target_question_count"] != target_count:
            _fail("campaign.diagnostic.target_invalid")
        if item["exam_level"] not in (None, "profile"):
            _fail("campaign.diagnostic.exam_level_invalid")
        if diagnostic_id == "ege-mathematics-1212" and item["exam_level"] != "profile":
            _fail("campaign.diagnostic.math_level_missing")
        url = item["official_archive_url"]
        if not isinstance(url, str) or not url.startswith("https://doc.fipi.ru/") or not url.endswith("2026.zip"):
            _fail("campaign.diagnostic.archive_invalid")

        allowlist = _list(item["allowlist"], "campaign.allowlist.invalid")
        allowed: dict[str, tuple[set[str], int]] = {}
        positions: list[str] = []
        for rule in allowlist:
            if not isinstance(rule, dict):
                _fail("campaign.allowlist.invalid")
            _keys(
                rule,
                {"exam_position", "question_types", "max_primary_score"},
                "campaign.allowlist.schema_invalid",
            )
            position = rule["exam_position"]
            types = rule["question_types"]
            score = rule["max_primary_score"]
            if (
                not isinstance(position, str)
                or not position
                or not isinstance(types, list)
                or not types
                or types != sorted(types)
                or not set(types) <= _QUESTION_TYPES
                or not isinstance(score, int)
                or isinstance(score, bool)
                or not 1 <= score <= 100
                or position in allowed
            ):
                _fail("campaign.allowlist.invalid")
            allowed[position] = (set(types), score)
            positions.append(position)
        if positions != sorted(positions):
            _fail("campaign.allowlist.not_sorted")

        slots = _list(item["slots"], "campaign.slots.invalid")
        expected_additions = target_count - expected_count
        if len(slots) != expected_additions:
            _fail("campaign.slots.deficit_mismatch")
        slot_ids = [slot.get("question_id") for slot in slots if isinstance(slot, dict)]
        if len(slot_ids) != len(slots):
            _fail("campaign.slot.invalid")
        if slot_ids != sorted(slot_ids):
            _fail("campaign.slot.not_sorted")
        for slot in slots:
            _keys(
                slot,
                {
                    "question_id",
                    "exam_position",
                    "question_type",
                    "max_primary_score",
                    "owner_partition",
                },
                "campaign.slot.schema_invalid",
            )
            question_id = slot["question_id"]
            if (
                not isinstance(question_id, str)
                or not _ID.fullmatch(question_id)
                or question_id in slots_seen
            ):
                _fail("campaign.slot.question_id_invalid")
            slots_seen.add(question_id)
            position = slot["exam_position"]
            rule = allowed.get(position)
            if rule is None:
                _fail("campaign.slot.position_unsafe")
            allowed_types, score = rule
            if slot["question_type"] not in allowed_types or slot["max_primary_score"] != score:
                _fail("campaign.slot.model_unsafe")
            owner = slot["owner_partition"]
            if not isinstance(owner, str) or not _ID.fullmatch(owner):
                _fail("campaign.slot.owner_invalid")
            slot_partitions[owner] += 1

        if actual_count == expected_count:
            if expected_hash != actual_hash:
                _fail("campaign.catalog.hash_changed")
            if any(question_id in existing_question_ids for question_id in slot_ids):
                _fail("campaign.catalog.materialization_partial")
        elif actual_count == target_count and expected_additions:
            if actual_ids[expected_count:] != slot_ids:
                _fail("campaign.catalog.materialization_order_invalid")
            questions_by_id = {
                question["id"]: question for question in actual_document["questions"]
            }
            for slot in slots:
                question = questions_by_id[slot["question_id"]]
                source = question.get("source")
                if (
                    question.get("type") != slot["question_type"]
                    or question.get("max_primary_score") != slot["max_primary_score"]
                    or not isinstance(question.get("explanation"), str)
                    or not question["explanation"]
                    or "asset" in question
                    or "assets" in question
                    or not isinstance(source, dict)
                    or source.get("provider") != "maximum"
                    or source.get("official_year") != 2026
                    or source.get("approval_status") != "draft"
                    or source.get("source_kind") != "original"
                    or source.get("rights_status") != "original"
                    or source.get("exam_position") != slot["exam_position"]
                    or source.get("official_criteria_url") != item["official_archive_url"]
                ):
                    _fail("campaign.catalog.materialization_invalid")
                if question_owner.get(slot["question_id"]) != diagnostic_id:
                    _fail("campaign.catalog.materialization_owner_invalid")
        else:
            _fail("campaign.catalog.count_changed")
        baseline_count += expected_count
        projected_count += target_count

    partitions = _list(manifest["partitions"], "campaign.partitions.invalid")
    partition_ids = [item.get("id") for item in partitions if isinstance(item, dict)]
    if len(partition_ids) != len(partitions) or partition_ids != sorted(partition_ids):
        _fail("campaign.partitions.not_sorted")
    owned_diagnostics: set[str] = set()
    partition_report: list[dict[str, Any]] = []
    for partition in partitions:
        _keys(
            partition,
            {"id", "expected_slot_count", "diagnostic_ids"},
            "campaign.partition.schema_invalid",
        )
        partition_id = partition["id"]
        owned = partition["diagnostic_ids"]
        if (
            not isinstance(partition_id, str)
            or not _ID.fullmatch(partition_id)
            or not isinstance(owned, list)
            or owned != sorted(owned)
            or any(item in owned_diagnostics for item in owned)
        ):
            _fail("campaign.partition.invalid")
        owned_diagnostics.update(owned)
        if partition["expected_slot_count"] != slot_partitions[partition_id]:
            _fail("campaign.partition.count_mismatch")
        for diagnostic_id in owned:
            target = next((item for item in diagnostics if item["diagnostic_id"] == diagnostic_id), None)
            if target is None or any(slot["owner_partition"] != partition_id for slot in target["slots"]):
                _fail("campaign.partition.ownership_mismatch")
        partition_report.append({"id": partition_id, "slots": slot_partitions[partition_id]})
    underfilled = {
        item["diagnostic_id"] for item in diagnostics if item["target_question_count"] > item["expected_question_count"]
    }
    if owned_diagnostics != underfilled or set(slot_partitions) != set(partition_ids):
        _fail("campaign.partition.coverage_mismatch")

    blockers = _list(manifest["known_blockers"], "campaign.blockers.invalid")
    blocker_ids = [item.get("blocker_id") for item in blockers if isinstance(item, dict)]
    if len(blocker_ids) != len(blockers) or blocker_ids != sorted(blocker_ids):
        _fail("campaign.blockers.not_sorted")
    for blocker in blockers:
        _keys(
            blocker,
            {"blocker_id", "diagnostic_id", "exam_positions", "reason"},
            "campaign.blocker.schema_invalid",
        )
        if (
            blocker["diagnostic_id"] not in diagnostic_ids
            or not isinstance(blocker["exam_positions"], list)
            or blocker["exam_positions"] != sorted(blocker["exam_positions"])
            or not isinstance(blocker["reason"], str)
            or not blocker["reason"]
        ):
            _fail("campaign.blocker.invalid")

    additions = len(slots_seen)
    if (
        baseline_count != baseline["question_count"]
        or additions != baseline["additions"]
        or projected_count != baseline["projected_question_count"]
    ):
        _fail("campaign.total.mismatch")
    return {
        "campaign_id": manifest["campaign_id"],
        "status": "materialized" if len(existing_question_ids) == projected_count else "planned",
        "diagnostics": len(diagnostics),
        "baseline_questions": baseline_count,
        "additions": additions,
        "projected_questions": projected_count,
        "partitions": partition_report,
        "blockers": len(blockers),
    }


def main(argv: list[str] | None = None, *, root: Path = REPOSITORY_ROOT) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.manifest
    if manifest_path == DEFAULT_MANIFEST and root != REPOSITORY_ROOT:
        manifest_path = root / "authoring" / "campaigns" / "fipi-2026-min15" / "manifest.json"
    try:
        report = validate_campaign(manifest_path, root / "school" / "diagnostics")
    except CampaignError as exc:
        print(f"ERROR {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
