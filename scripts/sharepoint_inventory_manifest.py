"""Build the phase-2 SharePoint inventory manifest from a local sample of DOCX files.

The sample is a directory that mirrors the SharePoint folder layout below
`Контент приложения`, for example:

    <sample>/МА/11 класс/Задания/Уравнения/МА_ЕГЭ_..._Заданий 10.docx
    <sample>/МА/11 класс/Задания/Уравнения/Исходники/....docx

For every `.docx` the script records the SharePoint path, size, modification
time, SHA-256 of the bytes, a content fingerprint (SHA-256 of the normalized
task texts, which survives a re-save of the same document), and what the
importer would do with each task. Files are then grouped into exact
duplicates, same-content copies and shared-task versions, and sorted into
`safe`, `review`, `duplicate` and `irrelevant`.

Nothing under `school/` is read for writing or touched. The only outputs are
the manifest JSON and the Markdown report passed on the command line.

    python scripts/sharepoint_inventory_manifest.py <sample> \
        --manifest authoring/sharepoint-inventory/phase-2-manifest.json \
        --report authoring/sharepoint-inventory/phase-2-dedup.md
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import import_sharepoint_diagnostics as importer  # noqa: E402

SHAREPOINT_ROOT = (
    "/sites/razrabotka2025/Shared Documents/КОНТЕНТ ЛК/Контент приложения"
)
DECLARED_COUNT = re.compile(r"Заданий\s*(\d+)", re.IGNORECASE)
GRADE = re.compile(r"^(\d{1,2})\s*класс", re.IGNORECASE)
# Folder names for editorial drafts vary by subject: `Исходники`, `ИСХОДНИКИ`,
# `Исходники 2`. Matching on the prefix keeps all three out of `topic_hint`
# and marks their files as copies.
SOURCE_FOLDER = "исходники"
SIDECAR_NAME = "sharepoint-metadata.json"
VERSION_OVERLAP = 0.5
REPOSITORY_ROOT = SCRIPTS_ROOT.parent


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def task_fingerprint(task: importer.SourceTask) -> str:
    """Hash of the task statement the importer would read, ignoring figures and layout.

    The answer key is out of the hash on purpose. Drafts in `Исходники` carry the
    same statement, tables and options without a separate `Ответ:` paragraph,
    so hashing the key hid exactly the pairs this tool exists to find. The
    statement, the tables and the options still have to match in full.
    """
    if task.prompt_nodes:
        parts = []
        for node in task.prompt_nodes:
            if isinstance(node, importer.PromptParagraph):
                parts.append(f"paragraph\n{node.text}")
            else:
                parts.append(f"table\n{importer._render_table(node.table)}")
        parts.append(f"options\n{importer.clean_block(task.options)}")
    else:
        parts = [
            importer.clean_block(task.prompt_blocks),
            "\n".join(importer._render_table(table) for table in task.prompt_tables),
            importer.clean_block(task.options),
        ]
    return sha256_bytes("\x1f".join(parts).casefold().encode("utf-8"))


def load_sidecar(sample_root: Path) -> dict[str, dict[str, Any]]:
    """Optional `sharepoint-metadata.json`: relative posix path -> {modified_at, ...}.

    A local copy only knows its own mtime, so the SharePoint modification date
    has to be captured at download time and passed in through this file.
    """
    sidecar = sample_root / SIDECAR_NAME
    if not sidecar.is_file():
        return {}
    return json.loads(sidecar.read_text(encoding="utf-8"))


def describe_file(
    path: Path, sample_root: Path, sharepoint_root: str, sidecar: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    relative = path.relative_to(sample_root)
    folders = [part for part in relative.parts[:-1]]
    payload = path.read_bytes()
    stat = path.stat()
    remote = sidecar.get(relative.as_posix(), {})
    record: dict[str, Any] = {
        "path": f"{sharepoint_root}/{relative.as_posix()}",
        "file_name": path.name,
        "extension": path.suffix.lower(),
        "size": stat.st_size,
        "modified_at": remote.get(
            "modified_at", datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        ),
        "modified_at_source": "sharepoint_metadata" if "modified_at" in remote else "local_file_mtime",
        "subject_code": folders[0] if folders else None,
        "subject": None,
        "exam": None,
        "grade": None,
        "topic_hint": "/".join(
            folder for folder in folders[1:] if not folder.casefold().startswith(SOURCE_FOLDER)
        ) or None,
        "in_source_folder": any(folder.casefold().startswith(SOURCE_FOLDER) for folder in folders),
        "declared_question_count": None,
        "content_hash": sha256_bytes(payload),
        "content_fingerprint": None,
        "task_fingerprints": [],
        "task_blocks": 0,
        "tasks_with_answer_key": 0,
        "tasks_with_explanation": 0,
        "tasks_with_images": 0,
        "has_answer_key": False,
        "has_explanation": False,
        "has_images": False,
        "filename_matches_importer": False,
        "importer_convertible": 0,
        "importer_skipped_by_reason": {},
        "parse_error": None,
    }
    for folder in folders:
        found = GRADE.match(folder)
        if found:
            record["grade"] = int(found.group(1))
    declared = DECLARED_COUNT.search(path.stem)
    if declared:
        record["declared_question_count"] = int(declared.group(1))

    match = importer.FILENAME.match(path.stem)
    if match:
        record["filename_matches_importer"] = True
        record["exam"] = importer.EXAM_CODES[match.group("exam")]
        code = importer.SUBJECT_CODES.get(match.group("subject"))
        record["subject"] = code
    elif record["subject_code"] in importer.SUBJECT_CODES:
        record["subject"] = importer.SUBJECT_CODES[record["subject_code"]]
    if record["exam"] is None and record["grade"] in {9, 11}:
        record["exam"] = "oge" if record["grade"] == 9 else "ege"

    if record["extension"] != ".docx":
        return record
    try:
        tasks = importer.parse_document(path)
    except Exception as exc:  # noqa: BLE001 - reported per file, never fatal
        record["parse_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return record

    reasons: Counter[str] = Counter()
    fingerprints = []
    for task in tasks:
        fingerprints.append(task_fingerprint(task))
        record["tasks_with_answer_key"] += bool(task.answer)
        record["tasks_with_explanation"] += bool(task.solution)
        record["tasks_with_images"] += bool(task.images)
        kind, payload = importer.classify(task)
        if kind == "skip":
            reasons[str(payload)] += 1
            continue
        prepared = [importer.prepare_image(image) for image in task.images]
        question = importer.build_question(
            importer.SourceFile(path, "ЕГЭ", record["subject"] or "mathematics", 2000, 0, ()),
            task, kind, payload, verified_at="1970-01-01",
        )
        reason = question if isinstance(question, str) else importer._rejection(question, prepared)
        if reason is None:
            record["importer_convertible"] += 1
        else:
            reasons[reason] += 1
    record["task_blocks"] = len(tasks)
    record["task_fingerprints"] = sorted(set(fingerprints))
    # A file without task blocks has no content to compare. Hashing the empty
    # string would collect every such file into one bogus `same_content` group.
    if fingerprints:
        record["content_fingerprint"] = sha256_bytes("\n".join(fingerprints).encode("utf-8"))
    record["has_answer_key"] = record["tasks_with_answer_key"] > 0
    record["has_explanation"] = record["tasks_with_explanation"] > 0
    record["has_images"] = record["tasks_with_images"] > 0
    record["importer_skipped_by_reason"] = dict(sorted(reasons.items()))
    return record


def group_duplicates(records: list[dict[str, Any]]) -> None:
    """Fill `duplicate_group`, `duplicate_kind` and `related_files` in place."""
    by_hash: dict[str, list[dict[str, Any]]] = {}
    by_content: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_hash.setdefault(record["content_hash"], []).append(record)
        if record["content_fingerprint"]:
            by_content.setdefault(record["content_fingerprint"], []).append(record)

    for record in records:
        record["duplicate_group"] = None
        record["duplicate_kind"] = "unique"
        record["related_files"] = []

    for digest, members in by_hash.items():
        if len(members) > 1:
            for member in members:
                member["duplicate_group"] = f"exact:{digest[:12]}"
                member["duplicate_kind"] = "exact_duplicate"
    for digest, members in by_content.items():
        if len(members) > 1:
            for member in members:
                if member["duplicate_kind"] == "unique":
                    member["duplicate_group"] = f"content:{digest[:12]}"
                    member["duplicate_kind"] = "same_content"

    parsed = [record for record in records if record["task_fingerprints"]]
    for index, left in enumerate(parsed):
        left_set = set(left["task_fingerprints"])
        for right in parsed[index + 1:]:
            if left["content_fingerprint"] == right["content_fingerprint"]:
                continue
            shared = left_set & set(right["task_fingerprints"])
            if not shared:
                continue
            overlap = len(shared) / min(len(left_set), len(right["task_fingerprints"]))
            if overlap < VERSION_OVERLAP:
                continue
            for this, other in ((left, right), (right, left)):
                this["related_files"].append(
                    {"path": other["path"], "shared_tasks": len(shared), "overlap": round(overlap, 2)}
                )
                if this["duplicate_kind"] == "unique":
                    this["duplicate_kind"] = "version"
                    this["duplicate_group"] = f"version:{min(left['content_hash'], right['content_hash'])[:12]}"


def ingestion_status(record: dict[str, Any]) -> tuple[str, str]:
    """Return (status, reason) for the three-way report."""
    if record["extension"] != ".docx" or record["parse_error"]:
        return "irrelevant", record["parse_error"] or "not_docx"
    if record["task_blocks"] == 0:
        return "irrelevant", "no_task_blocks"
    if record["duplicate_kind"] in {"exact_duplicate", "same_content"}:
        # Keep the copy outside `Исходники`; the source-folder copy is the duplicate.
        if record["in_source_folder"]:
            return "duplicate", record["duplicate_kind"]
    if record["duplicate_kind"] == "version":
        return "review", "shares_tasks_with_another_file"
    if record["in_source_folder"]:
        return "review", "source_folder"
    if not record["filename_matches_importer"]:
        return "review", "filename_not_importable"
    if record["subject"] is None or record["exam"] is None:
        return "review", "subject_or_exam_unknown"
    if record["declared_question_count"] not in (None, record["task_blocks"]):
        return "review", "declared_count_mismatch"
    if record["tasks_with_answer_key"] != record["task_blocks"]:
        return "review", "missing_answer_keys"
    if record["importer_convertible"] == 0:
        return "review", "nothing_convertible"
    if record["importer_convertible"] < record["task_blocks"]:
        return "review", "partial_conversion"
    return "safe", "all_tasks_convertible"


def write_report(path: Path, records: list[dict[str, Any]], sample_root: Path) -> None:
    lines = [
        "# Инвентаризация SharePoint - фаза 2, выборка и дубли",
        "",
        f"Сгенерировано `python scripts/sharepoint_inventory_manifest.py` "
        f"({datetime.now(tz=timezone.utc).date().isoformat()}) по локальной выборке "
        f"`{display_path(sample_root)}`. Файл не меняет `school/`.",
        "",
        "## Итоги",
        "",
        "| Статус | Файлов | Блоков заданий | Конвертируемых |",
        "|---|---:|---:|---:|",
    ]
    for status in ("safe", "review", "duplicate", "irrelevant"):
        members = [record for record in records if record["ingestion_status"] == status]
        lines.append(
            f"| {status} | {len(members)} | {sum(m['task_blocks'] for m in members)} "
            f"| {sum(m['importer_convertible'] for m in members)} |"
        )
    titles = {
        "safe": "Безопасные кандидаты на импорт",
        "review": "Кандидаты с ручной редакционной проверкой",
        "duplicate": "Дубли",
        "irrelevant": "Нерелевантные файлы",
    }
    for status, title in titles.items():
        members = sorted(
            (record for record in records if record["ingestion_status"] == status),
            key=lambda record: record["path"],
        )
        lines.extend(["", f"## {title}", ""])
        if not members:
            lines.append("Нет файлов.")
            continue
        lines.extend(
            [
                "| Файл | Предмет | Экзамен | Тема | Заявлено | Блоков | Ключ | Решение | Рисунки | Конвертируемых | SHA-256 | Причина |",
                "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for record in members:
            reasons = ", ".join(
                f"{reason}={count}" for reason, count in record["importer_skipped_by_reason"].items()
            )
            reason = record["ingestion_reason"] + (f" ({reasons})" if reasons else "")
            lines.append(
                f"| {record['file_name']} | {record['subject'] or '-'} | {record['exam'] or '-'} "
                f"| {record['topic_hint'] or '-'} | {record['declared_question_count'] or '-'} "
                f"| {record['task_blocks']} | {record['tasks_with_answer_key']} "
                f"| {record['tasks_with_explanation']} | {record['tasks_with_images']} "
                f"| {record['importer_convertible']} | `{record['content_hash'][:12]}` | {reason} |"
            )
    lines.extend(["", "## Группы дублей и версий", ""])
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["duplicate_group"]:
            groups.setdefault(record["duplicate_group"], []).append(record)
    if not groups:
        lines.append("Совпадений по байтам, по содержимому и по общим заданиям не найдено.")
    for group, members in sorted(groups.items()):
        lines.append(f"- `{group}` ({members[0]['duplicate_kind']}):")
        for member in members:
            related = "; ".join(
                f"{item['shared_tasks']} общих с {Path(item['path']).name}" for item in member["related_files"]
            )
            lines.append(f"  - {member['path']}" + (f" ({related})" if related else ""))
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path, help="Local directory mirroring the SharePoint layout")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sharepoint-root", default=SHAREPOINT_ROOT)
    arguments = parser.parse_args(argv)

    sample_root = arguments.sample.resolve()
    files = sorted(
        path for path in sample_root.rglob("*")
        if path.is_file() and not path.name.startswith("~$") and path.name != SIDECAR_NAME
    )
    if not files:
        raise SystemExit(f"No files under {sample_root}")
    sidecar = load_sidecar(sample_root)
    records = [
        describe_file(path, sample_root, arguments.sharepoint_root, sidecar) for path in files
    ]
    group_duplicates(records)
    for record in records:
        record["ingestion_status"], record["ingestion_reason"] = ingestion_status(record)

    manifest = {
        "captured_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "sample_root": display_path(sample_root),
        "sharepoint_root": arguments.sharepoint_root,
        "files": len(records),
        "by_status": dict(Counter(record["ingestion_status"] for record in records)),
        "records": records,
    }
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    write_report(arguments.report, records, sample_root)
    print(json.dumps({"files": len(records), "by_status": manifest["by_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
