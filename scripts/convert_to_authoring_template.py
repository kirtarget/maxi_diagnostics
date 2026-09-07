"""Convert a MAXIMUM editorial document into the authoring format.

The source is a flat `.docx` of ``Задание N`` blocks with optional ``Варианты``,
``Решение`` (or ``Ход решения``) and a mandatory ``Ответ`` section, the same
shape `import_sharepoint_diagnostics.py` reads. The result follows
``docs/AUTHORING_TEMPLATE.md``: a header, then one block per task with the type
named in words, items and options under their own headings, and the key in its
own field. Formatting, tables and figures are carried over as Word elements.

Whatever cannot be read without guessing is written as ``ТРЕБУЕТ ПРОВЕРКИ``
so the editor fills it in; `check_authoring_document.py` then lists every
such field.

    python scripts/convert_to_authoring_template.py <исходный.docx> <результат.docx>
    python scripts/convert_to_authoring_template.py <папка с docx> <папка результата>

The directory form converts every `.docx` and writes `report.md` next to the
results.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
import io
import json
from pathlib import Path
import re
import sys

from docx import Document
from docx.image.exceptions import UnrecognizedImageError
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

sys.path.insert(0, str(Path(__file__).resolve().parent))

from authoring_document import (  # noqa: E402
    ANSWER_FORM_HINT,
    NEEDS_REVIEW,
    TYPE_MATCHING,
    TYPE_MULTIPLE,
    TYPE_NUMBER,
    TYPE_SHORT,
    TYPE_SINGLE,
    check_document,
    has_drawing,
    iter_body,
    paragraph_text,
    read_document,
)
import import_sharepoint_diagnostics as importer  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "authoring" / "sharepoint-inventory" / "phase-2-manifest.json"

SECTION_MARKERS = {
    "варианты": "options",
    "решение": "solution",
    "ход решения": "solution",
    "ответ": "answer",
}
SUBJECT_PREFIX = re.compile(r"^([А-ЯЁ]+)(?=[ _])")
EXAM_IN_NAME = re.compile(r"(?<![А-ЯЁа-яё])(ЕГЭ|ОГЭ)(?![А-ЯЁа-яё])")
SEASON_IN_NAME = re.compile(r"(?<!\d)(\d{2}-\d{2})(?!\d)")
DIAGNOSTIC_WORDS = re.compile(r"Диагностика|МРКТ|Пробный", re.IGNORECASE)
NOISE_SEGMENT = re.compile(
    r"^(ЕГЭ|ОГЭ|МП|КТ|ОДЗ|Приложение|Задани[йя]\s*\d*|Занятий\s*\d*|\d+|\d{2}-\d{2}|"
    r"[а-яё]+\s+\d+)$",
    re.IGNORECASE,
)
OPTION_PREFIX = re.compile(r"^\d+[).]\s*")
ITEM_PREFIX = re.compile(r"^[А-ЯЁA-Z][).]\s*")
ITEM_LABELS = "АБВГДЕЖЗИКЛМНОП"
RELATIONSHIP_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
EXAM_GRADE = {"ЕГЭ": "11", "ОГЭ": "9"}
EXAM_NAMES = {"ege": "ЕГЭ", "oge": "ОГЭ"}
DANGLING_TAGS = (
    "w:footnoteReference", "w:endnoteReference", "w:commentRangeStart",
    "w:commentRangeEnd", "w:commentReference", "w:bookmarkStart", "w:bookmarkEnd",
    "w:proofErr", "w:lastRenderedPageBreak",
)


# --------------------------------------------------------------------------
# Source model
# --------------------------------------------------------------------------


@dataclass
class SourceBlock:
    element: object
    text: str
    is_table: bool = False
    is_image: bool = False


@dataclass
class SourceTask:
    number: int
    sections: dict[str, list[SourceBlock]] = field(
        default_factory=lambda: {"prompt": [], "options": [], "solution": [], "answer": []}
    )


@dataclass
class Conversion:
    """What the converter decided for one source file."""

    name: str
    tasks: int = 0
    types: Counter = field(default_factory=Counter)
    review_fields: list[str] = field(default_factory=list)
    dropped_hints: int = 0
    unread_reasons: Counter = field(default_factory=Counter)
    header: dict[str, str] = field(default_factory=dict)
    check_problems: list[str] = field(default_factory=list)


def parse_source(document) -> list[SourceTask]:
    tasks: list[SourceTask] = []
    current: SourceTask | None = None
    section = "prompt"
    for block in iter_body(document):
        if isinstance(block, Table):
            if current is not None:
                text = "\n".join(
                    paragraph_text(paragraph)
                    for row in block.rows for cell in row.cells for paragraph in cell.paragraphs
                )
                current.sections[section].append(SourceBlock(block._tbl, text, is_table=True))
            continue
        text = importer.clean_line(paragraph_text(block))
        heading = importer.TASK_HEADING.match(text)
        if heading:
            current = SourceTask(number=int(heading.group(1)))
            tasks.append(current)
            section = "prompt"
            continue
        if current is None:
            continue
        marker = SECTION_MARKERS.get(text.rstrip(":").strip().casefold())
        if marker:
            section = marker
            continue
        image = has_drawing(block._p)
        if text or image:
            current.sections[section].append(SourceBlock(block._p, text, is_image=image))
    return tasks


def to_importer_task(task: SourceTask) -> importer.SourceTask:
    """The importer's view of the task, so its key classification can be reused."""
    prompt = task.sections["prompt"]
    return importer.SourceTask(
        number=task.number,
        prompt_blocks=[block.text for block in prompt if not block.is_table and block.text],
        prompt_tables=[
            importer._read_table(Table(block.element, None)) for block in prompt if block.is_table
        ],
        options=[block.text for block in task.sections["options"] if block.text],
        solution=[block.text for block in task.sections["solution"] if block.text],
        answer=[block.text for block in task.sections["answer"] if block.text],
    )


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


@dataclass
class Matching:
    items: list[SourceBlock]
    options: list[SourceBlock]
    table_index: int | None
    key: str


def detect_matching(task: SourceTask, key: str) -> Matching | None:
    """A matching task is two lettered/numbered lists whose key spells one digit per item.

    Items may use `А)` or `А.`, in a two-column table or as plain paragraphs.
    The key must be exactly as long as the item list and use only option digits,
    which is why this is a reading and not a guess.
    """
    if task.sections["options"] or not key.isdigit():
        return None
    prompt = task.sections["prompt"]
    candidates: list[tuple[list[SourceBlock], list[SourceBlock], int | None]] = []
    for index, block in enumerate(prompt):
        if not block.is_table:
            continue
        table = Table(block.element, None)
        items: list[SourceBlock] = []
        options: list[SourceBlock] = []
        for row in table.rows:
            cells = row.cells
            if len(cells) != 2:
                continue
            items.extend(_labelled(cells[0].paragraphs, ITEM_PREFIX))
            options.extend(_labelled(cells[1].paragraphs, OPTION_PREFIX))
        candidates.append((items, options, index))
    paragraphs = [
        Paragraph(block.element, None)
        for block in prompt if not block.is_table and not block.is_image
    ]
    candidates.append((_labelled(paragraphs, ITEM_PREFIX), _labelled(paragraphs, OPTION_PREFIX), None))
    for items, options, index in candidates:
        if len(items) < 2 or len(options) < 2 or len(items) != len(key):
            continue
        digits = {_label(block.text, OPTION_PREFIX) for block in options}
        if len(digits) == len(options) and set(key) <= digits:
            return Matching(items, options, index, key)
    return None


def _label(text: str, pattern: re.Pattern) -> str:
    return pattern.match(text).group(0).rstrip(") .")


def _labelled(paragraphs, pattern: re.Pattern) -> list[SourceBlock]:
    found = []
    for paragraph in paragraphs:
        text = importer.clean_line(paragraph_text(paragraph))
        match = pattern.match(text)
        if match and len(text) > len(match.group(0)):
            found.append(SourceBlock(paragraph._p, text))
    return found


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------


def load_manifest(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {record["file_name"]: record for record in payload.get("records", [])}


def derive_header(name: str, manifest: dict[str, dict]) -> dict[str, str]:
    stem = Path(name).stem
    record = manifest.get(name, {})
    prefix = SUBJECT_PREFIX.match(stem)
    code = importer.SUBJECT_CODES.get(prefix.group(1)) if prefix else None
    subject = importer.SUBJECT_NAMES.get(code, NEEDS_REVIEW) if code else NEEDS_REVIEW

    exam_match = EXAM_IN_NAME.search(stem)
    exam = exam_match.group(1) if exam_match else EXAM_NAMES.get(record.get("exam"), NEEDS_REVIEW)
    grade = str(record["grade"]) if record.get("grade") else EXAM_GRADE.get(exam, NEEDS_REVIEW)
    season_match = SEASON_IN_NAME.search(stem)
    season = season_match.group(1) if season_match else NEEDS_REVIEW
    section = (record.get("topic_hint") or "").rsplit("/", 1)[-1]
    section = re.sub(r"^\d+\.\s*", "", section)
    topic = (
        NEEDS_REVIEW if DIAGNOSTIC_WORDS.search(stem) else _topic_from_name(stem, prefix, section)
    )
    return {"Предмет": subject, "Экзамен": exam, "Класс": grade, "Сезон": season, "Тема": topic}


def _topic_from_name(stem: str, prefix: re.Match | None, section: str) -> str:
    """The topic is what the filename says after the subject code and the noise words.

    A leading segment that only repeats the SharePoint section folder is dropped.
    """
    rest = stem[prefix.end():] if prefix else stem
    rest = re.sub(r"^\s*\d+\s*_", "", rest.strip(" _"))
    segments = [
        re.sub(r"^\d+\.\s*", "", segment.strip(" ."))
        for segment in rest.split("_")
    ]
    segments = [segment for segment in segments if segment and not NOISE_SEGMENT.match(segment)]
    if len(segments) > 1 and section and segments[0].casefold() == section.casefold():
        segments = segments[1:]
    if not segments:
        return NEEDS_REVIEW
    if all(" " not in segment for segment in segments):
        return " ".join(segments)
    return ". ".join(segments)


# --------------------------------------------------------------------------
# Element adoption
# --------------------------------------------------------------------------


class Adopter:
    """Copies body elements into the target document, re-homing every part they reference.

    Figures, embedded equation objects and their previews all point at parts of
    the source package through `r:*` attributes; each such part is copied once
    and the attribute rewritten. Styles, numbering, comments and footnotes are
    not carried, so their references are stripped.
    """

    def __init__(self, source, target) -> None:
        self.source_part = source.part
        self.target = target
        self.part_ids: dict[str, str] = {}

    def adopt(self, element):
        clone = deepcopy(element)
        for tag in DANGLING_TAGS:
            for node in list(clone.iter(qn(tag))):
                node.getparent().remove(node)
        for hyperlink in list(clone.iter(qn("w:hyperlink"))):
            parent = hyperlink.getparent()
            index = parent.index(hyperlink)
            for child in list(hyperlink):
                parent.insert(index, child)
                index += 1
            parent.remove(hyperlink)
        for node in clone.iter():
            for attribute, value in list(node.attrib.items()):
                if attribute.startswith(RELATIONSHIP_NAMESPACE):
                    self._remap(node, attribute, value)
        for properties in list(clone.iter(qn("w:pPr"))):
            for tag in ("w:numPr", "w:pStyle", "w:sectPr"):
                for node in properties.findall(qn(tag)):
                    properties.remove(node)
        for properties in list(clone.iter(qn("w:rPr"))):
            for node in properties.findall(qn("w:rStyle")):
                properties.remove(node)
        for properties in list(clone.iter(qn("w:tblPr"))):
            for node in properties.findall(qn("w:tblStyle")):
                properties.remove(node)
            style = OxmlElement("w:tblStyle")
            style.set(qn("w:val"), "TableGrid")
            properties.insert(0, style)
        self.target.element.body.find(qn("w:sectPr")).addprevious(clone)
        return clone

    def _remap(self, node, attribute: str, relationship_id: str) -> None:
        relationship = self.source_part.rels.get(relationship_id)
        if relationship is None or relationship.is_external:
            del node.attrib[attribute]
            return
        if relationship_id not in self.part_ids:
            self.part_ids[relationship_id] = self._import_part(
                relationship.target_part, relationship.reltype
            )
        node.set(attribute, self.part_ids[relationship_id])

    def _import_part(self, source, reltype: str) -> str:
        if reltype == RT.IMAGE:
            try:
                relationship_id, _ = self.target.part.get_or_add_image(io.BytesIO(source.blob))
                return relationship_id
            except UnrecognizedImageError:
                pass
        package = self.target.part.package
        source_name = Path(str(source.partname))
        template = f"{source_name.parent.as_posix()}/{re.sub(r'\d+$', '', source_name.stem)}%d{source_name.suffix}"
        part = Part(package.next_partname(template), source.content_type, source.blob, package)
        return self.target.part.relate_to(part, reltype)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


class Writer:
    def __init__(self, source, target) -> None:
        self.target = target
        self.adopter = Adopter(source, target)

    def line(self, text: str) -> None:
        self.target.add_paragraph(text)

    def field(self, name: str, value: str | None = None) -> None:
        self.line(f"{name}: {value}" if value is not None else f"{name}:")

    def blocks(self, blocks: list[SourceBlock]) -> None:
        for block in blocks:
            self.adopter.adopt(block.element)

    def numbered(
        self, blocks: list[SourceBlock], labels: list[str], prefix: re.Pattern = OPTION_PREFIX
    ) -> None:
        """Adopt each paragraph, replacing any existing label with `N) ` in a plain run."""
        for block, label in zip(blocks, labels):
            clone = self.adopter.adopt(block.element)
            first_text = next(clone.iter(qn("w:t")), None)
            if first_text is not None:
                first_text.text = prefix.sub("", first_text.text or "", count=1)
            run = OxmlElement("w:r")
            text = OxmlElement("w:t")
            text.text = f"{label}) "
            text.set(qn("xml:space"), "preserve")
            run.append(text)
            properties = clone.find(qn("w:pPr"))
            position = clone.index(properties) + 1 if properties is not None else 0
            clone.insert(position, run)


def convert(source_path: Path, target_path: Path, manifest: dict[str, dict]) -> Conversion:
    source = Document(str(source_path))
    target = Document()
    for paragraph in list(target.paragraphs):
        paragraph._p.getparent().remove(paragraph._p)
    writer = Writer(source, target)
    outcome = Conversion(name=source_path.name)

    outcome.header = derive_header(source_path.name, manifest)
    for name, value in outcome.header.items():
        writer.field(name, value)
        if value == NEEDS_REVIEW:
            outcome.review_fields.append(f"Шапка, поле «{name}»")
    writer.line("")

    for task in parse_source(source):
        outcome.tasks += 1
        _write_task(writer, task, outcome)
        writer.line("")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target.save(str(target_path))
    outcome.check_problems = [str(problem) for problem in check_document(read_document(target_path))]
    return outcome


def _write_task(writer: Writer, task: SourceTask, outcome: Conversion) -> None:
    number = task.number
    prompt = task.sections["prompt"]
    options = [block for block in task.sections["options"] if block.text]
    answer_lines = [block.text for block in task.sections["answer"] if block.text]
    matching = detect_matching(task, answer_lines[0]) if len(answer_lines) == 1 else None
    if matching is not None:
        kind, payload = "matching", {}
    else:
        kind, payload = importer.classify(to_importer_task(task))
    writer.line(f"Задание {number}")

    type_name = {
        "single": TYPE_SINGLE, "multiple": TYPE_MULTIPLE, "matching": TYPE_MATCHING,
        "input": TYPE_NUMBER, "text": TYPE_SHORT,
    }.get(kind, NEEDS_REVIEW)
    if kind == "input" and len(payload["correct"]) > 1 and payload.get("sequence"):
        type_name = TYPE_SHORT
    if type_name == NEEDS_REVIEW:
        outcome.review_fields.append(f"Задание {number}, поле «Тип»")
        outcome.unread_reasons[str(payload)] += 1
    outcome.types[type_name] += 1
    writer.field("Тип", type_name)

    writer.field("Условие")
    excluded = set()
    if matching is not None:
        excluded = {id(block.element) for block in matching.items + matching.options}
        if matching.table_index is not None:
            excluded.add(id(prompt[matching.table_index].element))
    kept = []
    for block in prompt:
        if id(block.element) in excluded:
            continue
        if not block.is_table and not block.is_image and ANSWER_FORM_HINT.match(block.text):
            outcome.dropped_hints += 1
            continue
        kept.append(block)
    writer.blocks(kept)
    if not kept:
        writer.line(NEEDS_REVIEW)
        outcome.review_fields.append(f"Задание {number}, поле «Условие»")

    if matching is not None:
        writer.field("Пункты")
        writer.numbered(matching.items, list(ITEM_LABELS[: len(matching.items)]), ITEM_PREFIX)
        writer.field("Варианты")
        writer.numbered(
            matching.options, [_label(block.text, OPTION_PREFIX) for block in matching.options]
        )
        answer = matching.key
    elif kind in {"single", "multiple"}:
        writer.field("Варианты")
        writer.numbered(options, [str(index) for index in range(1, len(options) + 1)])
        answer = ", ".join(str(index) for index in payload["indices"])
    elif kind == "input":
        # The importer adds a dotted twin for every comma decimal; the author wrote one number.
        answer = payload["correct"] if type_name == TYPE_SHORT else payload["correct"][0]
    elif kind == "text":
        answer = payload["correct"]
    else:
        if options:
            writer.field("Варианты")
            writer.numbered(options, [str(index) for index in range(1, len(options) + 1)])
        answer = answer_lines or [NEEDS_REVIEW]
        if not answer_lines:
            outcome.review_fields.append(f"Задание {number}, поле «Ответ»")

    if isinstance(answer, list) and len(answer) == 1:
        answer = answer[0]
    if isinstance(answer, list):
        writer.field("Ответ")
        for line in answer:
            writer.line(line)
    else:
        writer.field("Ответ", answer)

    solution = task.sections["solution"]
    if solution:
        writer.field("Решение")
        writer.blocks(solution)


# --------------------------------------------------------------------------
# Batch report
# --------------------------------------------------------------------------


def write_report(path: Path, outcomes: list[Conversion], source_root: Path) -> None:
    lines = [
        "# Перевод документов SharePoint в авторский формат",
        "",
        f"Сгенерировано `python scripts/convert_to_authoring_template.py {source_root.as_posix()} "
        f"{path.parent.as_posix()}` ({date.today().isoformat()}).",
        "",
        "Каждый документ переведён в формат `docs/AUTHORING_TEMPLATE.md`. Тип задания "
        "взят из формы ключа и таблиц тем же правилом, что и у импортёра каталога; "
        "там, где ключ прочитать однозначно нельзя, тип помечен "
        f"«{NEEDS_REVIEW}». Строки «В ответ запишите последовательность цифр…» "
        "удалены из условия: бланка в приложении нет. Остальной текст, таблицы и "
        "рисунки перенесены без правок.",
        "",
        "## Итоги",
        "",
        "| Файл | Заданий | " + " | ".join(
            (TYPE_SINGLE, TYPE_MULTIPLE, TYPE_MATCHING, TYPE_NUMBER, TYPE_SHORT, NEEDS_REVIEW)
        ) + " | Удалено подсказок | Замечаний проверки |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for outcome in outcomes:
        counts = [
            outcome.types.get(name, 0)
            for name in (TYPE_SINGLE, TYPE_MULTIPLE, TYPE_MATCHING, TYPE_NUMBER, TYPE_SHORT, NEEDS_REVIEW)
        ]
        lines.append(
            f"| {outcome.name} | {outcome.tasks} | " + " | ".join(map(str, counts))
            + f" | {outcome.dropped_hints} | {len(outcome.check_problems)} |"
        )

    lines.extend(["", "## Шапки", "", "| Файл | " + " | ".join(outcomes[0].header) + " |" if outcomes else "", "|---|---|---|---|---|---|"])
    for outcome in outcomes:
        lines.append(f"| {outcome.name} | " + " | ".join(outcome.header.values()) + " |")

    lines.extend(["", "## Что заполняет методист", "",
                  "Каждое поле, помеченное «ТРЕБУЕТ ПРОВЕРКИ», и каждое замечание проверки.", ""])
    for outcome in outcomes:
        if not outcome.check_problems:
            continue
        lines.extend([f"### {outcome.name}", ""])
        for problem in outcome.check_problems:
            lines.append(f"- {problem}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args(argv)
    manifest = load_manifest(arguments.manifest)

    if arguments.source.is_dir():
        sources = sorted(path for path in arguments.source.glob("*.docx") if not path.name.startswith("~$"))
        outcomes = []
        for path in sources:
            outcome = convert(path, arguments.target / path.name, manifest)
            outcomes.append(outcome)
            print(
                f"{path.name}: заданий {outcome.tasks}, "
                f"{NEEDS_REVIEW} {len(outcome.review_fields)}, "
                f"замечаний {len(outcome.check_problems)}"
            )
        write_report(arguments.target / "report.md", outcomes, arguments.source)
        return 0

    outcome = convert(arguments.source, arguments.target, manifest)
    print(f"Заданий: {outcome.tasks}")
    for problem in outcome.check_problems:
        print(problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
