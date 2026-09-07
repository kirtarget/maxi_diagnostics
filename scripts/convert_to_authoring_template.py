"""Rewrite an editorial document in the authoring format.

Everything the current converter reads without guessing is filled in. Everything
it would have to guess is left empty and marked, so the guess belongs to the
editor and not to a program.

    python scripts/convert_to_authoring_template.py <исходный.docx> <результат.docx>
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys

from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Cm

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import authoring_document as authoring  # noqa: E402
import import_sharepoint_diagnostics as legacy  # noqa: E402

REVIEW = "ТРЕБУЕТ ПРОВЕРКИ"
SKIP_REASONS = {
    "irregular_key": "ключ не удалось прочитать",
    "glued_answer": "в ключе пропал пробел между словами",
    "unreadable_matching": "таблицу пар не удалось прочитать",
    "missing_figure": "условие ссылается на рисунок, которого нет",
    "external_resource": "задание ссылается на внешний файл или запись",
    "open_answer": "ответ развёрнутый, машинной проверке не поддаётся",
    "prompt_too_long": "условие длиннее допустимого",
    "empty_prompt": "условие пустое",
}
KIND_NAMES = {
    "single": authoring.SINGLE,
    "multiple": authoring.MULTIPLE,
    "matching": authoring.MATCHING,
    "text": authoring.SHORT,
}


def _mark(reason: str) -> str:
    return f"{REVIEW} ({reason})"


def _header(document: DocxDocument, path: Path) -> list[str]:
    """Fill the header from the file name, and say which fields it could not."""
    match = legacy.FILENAME.match(path.stem)
    marked: list[str] = []
    if match is None:
        values = {name: _mark("имя файла не разобрано") for name in authoring.HEADER_FIELDS}
        marked = list(authoring.HEADER_FIELDS)
    else:
        subject = legacy.SUBJECT_CODES.get(match.group("subject"))
        values = {
            "Предмет": legacy.SUBJECT_NAMES.get(subject, _mark("предмет не распознан")),
            "Экзамен": match.group("exam"),
            "Класс": "11" if match.group("exam") == "ЕГЭ" else "9",
            "Сезон": f"{match.group('start')}-{match.group('end')}",
            "Тема": _mark("тема в имени файла не указана"),
        }
        marked = [name for name, value in values.items() if value.startswith(REVIEW)]
    for name in authoring.HEADER_FIELDS:
        document.add_paragraph(f"{name}: {values[name]}")
    return marked


def _write_prompt(document: DocxDocument, task: legacy.SourceTask) -> None:
    document.add_paragraph("Условие:")
    for block in task.prompt_blocks:
        document.add_paragraph(block)
    for table in task.prompt_tables:
        columns = max(table.columns, 1)
        written = document.add_table(rows=len(table.rows), cols=columns)
        for row, source_row in zip(written.rows, table.rows):
            for cell, lines in zip(row.cells, source_row):
                cell.text = "\n".join(lines)
    for payload in task.images:
        try:
            document.add_picture(io.BytesIO(payload), width=Cm(12))
        except Exception:  # noqa: BLE001 - an unreadable figure is the editor's call
            document.add_paragraph(_mark("рисунок не удалось перенести"))


def _write_choice(document: DocxDocument, task: legacy.SourceTask, indices: list[int]) -> None:
    document.add_paragraph("Варианты:")
    for index, label in enumerate(task.options, start=1):
        document.add_paragraph(f"{index}) {label}")
    document.add_paragraph("Ответ: " + ", ".join(str(index) for index in indices))


def _write_matching(document: DocxDocument, payload: dict) -> None:
    document.add_paragraph("Пункты:")
    for index, item in enumerate(payload["items"]):
        document.add_paragraph(f"{chr(ord('А') + index)}) {legacy.clean_line(item)}")
    document.add_paragraph("Варианты:")
    for digit, label in payload["options"]:
        document.add_paragraph(f"{digit}) {legacy.clean_line(label)}")
    document.add_paragraph(f"Ответ: {payload['key']}")


def convert(source: Path, target: Path) -> dict[str, object]:
    tasks = legacy.parse_document(source)
    document = Document()
    marked_header = _header(document, source)
    clean = 0
    marked: list[tuple[int, str]] = []

    for task in tasks:
        document.add_paragraph(f"Задание {task.number}")
        kind, payload = legacy.classify(task)

        if kind == "skip":
            reason = SKIP_REASONS.get(str(payload), str(payload))
            document.add_paragraph(f"Тип: {_mark(reason)}")
            _write_prompt(document, task)
            document.add_paragraph(f"Ответ: {_mark(reason)}")
            marked.append((task.number, reason))
        elif kind in {"single", "multiple"}:
            document.add_paragraph(f"Тип: {KIND_NAMES[kind]}")
            _write_prompt(document, task)
            _write_choice(document, task, payload["indices"])
            clean += 1
        elif kind == "matching":
            document.add_paragraph(f"Тип: {authoring.MATCHING}")
            _write_prompt(document, task)
            _write_matching(document, payload)
            clean += 1
        elif kind == "text":
            document.add_paragraph(f"Тип: {authoring.SHORT}")
            _write_prompt(document, task)
            document.add_paragraph("Ответ:")
            for wording in payload["correct"]:
                document.add_paragraph(wording)
            clean += 1
        else:  # input
            values = payload["correct"]
            sequence = all(value.isdigit() and len(value) > 1 for value in values)
            if sequence:
                # The printed list of choices lives inside the prompt, so the
                # structured options are exactly what the editor has to supply.
                reason = "перенесите список вариантов из условия в поле «Варианты»"
                document.add_paragraph(f"Тип: {authoring.SEQUENCE}")
                _write_prompt(document, task)
                document.add_paragraph(f"Варианты: {_mark(reason)}")
                document.add_paragraph(f"Ответ: {values[0]}")
                marked.append((task.number, reason))
            else:
                document.add_paragraph(f"Тип: {authoring.NUMBER}")
                _write_prompt(document, task)
                document.add_paragraph(f"Ответ: {values[0]}")
                clean += 1

        if task.solution:
            document.add_paragraph("Решение:")
            for line in task.solution:
                document.add_paragraph(line)

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))
    return {"tasks": len(tasks), "clean": clean, "marked": marked, "header": marked_header}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Редакционный документ")
    parser.add_argument("target", type=Path, help="Куда записать результат")
    arguments = parser.parse_args(argv)

    report = convert(arguments.source, arguments.target)
    print(f"{arguments.target}")
    print(f"  заданий: {report['tasks']}, перенеслось чисто: {report['clean']}")
    if report["header"]:
        print(f"  шапка требует проверки: {', '.join(report['header'])}")
    for number, reason in report["marked"]:
        print(f"  задание {number}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
