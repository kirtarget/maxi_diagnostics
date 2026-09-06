"""Repair catalog text from the superscript-aware SharePoint source parser.

The command is a dry run by default. It updates only existing ``sp-``
questions and only string fields whose source text matches after removing
formatting markers. No answers, IDs, assets, or catalog structure are changed.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

try:
    from scripts import import_sharepoint_diagnostics as importer
except ModuleNotFoundError:  # direct execution from the repository root
    import import_sharepoint_diagnostics as importer


TEXT_FIELDS = ("prompt", "explanation", "options", "items")
MARKER = re.compile(r"\^\(|_\(")


def _without_markers(value: object) -> object:
    if isinstance(value, list):
        return [_without_markers(item) for item in value]
    if isinstance(value, dict):
        return {key: _without_markers(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    result: list[str] = []
    index = 0
    while index < len(value):
        match = MARKER.match(value, index)
        if match is None:
            result.append(value[index])
            index += 1
            continue
        depth = 1
        cursor = match.end()
        while cursor < len(value) and depth:
            if value[cursor] == "(":
                depth += 1
            elif value[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            return value
        result.append(_without_markers(value[match.end() : cursor - 1]))
        index = cursor
    return "".join(result)


def repair(source_directory: Path, root: Path, apply: bool) -> list[tuple[str, str]]:
    targets = importer.load_targets(root / "school" / "diagnostics")
    existing: dict[str, tuple[importer.Target, dict, int]] = {}
    for target in targets.values():
        for index, (question_id, _) in enumerate(target.chunks):
            existing[question_id] = (target, target.payload["questions"][index], index)

    changes: list[tuple[str, str]] = []
    replacements: dict[Path, dict[int, dict]] = {}
    for path in sorted(source_directory.glob("*.docx")):
        source = importer.read_source_file(path)
        candidates, _ = importer.convert_file(source, "2026-09-04")
        for candidate in candidates:
            question_id = candidate.question["id"]
            record = existing.get(question_id)
            if record is None:
                continue
            target, old, index = record
            replacement = dict(old)
            fields: list[str] = []
            for field in TEXT_FIELDS:
                new_value = candidate.question.get(field)
                old_value = old.get(field)
                if new_value != old_value and _without_markers(new_value) == _without_markers(old_value):
                    replacement[field] = new_value
                    fields.append(field)
            if fields:
                changes.extend((question_id, field) for field in fields)
                replacements.setdefault(target.path, {})[index] = replacement

    if apply:
        for path, updates in replacements.items():
            target = importer.read_target(path)
            chunks = list(target.chunks)
            for index, question in updates.items():
                question_id = chunks[index][0]
                chunks[index] = (question_id, importer.render_question(question))
            importer.write_diagnostic(path, importer.render_target(target, chunks))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    changes = repair(args.source_directory, args.root, args.apply)
    mode = "applied" if args.apply else "candidate"
    print(f"{mode}: {len(changes)} field changes")
    for question_id, field in changes:
        print(f"{question_id}\t{field}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
