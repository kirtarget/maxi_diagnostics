"""Append editor-approved SharePoint diagnostics to the school catalog.

The source documents are MAXIMUM editorial diagnostics exported as `.docx`. Every
file is a flat list of `Задание N` blocks with an optional option list, optional
tables, an optional `Решение:` and a mandatory `Ответ:` key. This converter maps
the machine-checkable subset onto catalog question types, extracts inline
figures, and records every skipped task with a reason in a Markdown report.

Every catalog question comes from these documents. A re-run replaces exactly the
questions whose id starts with `sp-`, leaves every other byte of the file alone,
and must produce byte-identical output.

    python scripts/import_sharepoint_diagnostics.py <docx-dir>
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Literal

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from diagnostic.numeric import is_valid_numeric_answer  # noqa: E402


ID_PREFIX = "sp-"
MAX_PROMPT_CHARS = 4000
MAX_EXPLANATION_CHARS = 2000
MAX_OPTION_LABEL_CHARS = 500
MAX_OPTIONS = 50
MAX_QUESTIONS_PER_DIAGNOSTIC = 200
MAX_CATALOG_FILE_BYTES = 1024 * 1024
MAX_QUESTION_ASSETS = 5
MAX_TEXT_VARIANTS = 20
MAX_TEXT_ANSWER_CHARS = 80
MAX_REFERENCED_ASSETS = 201
MAX_ASSET_SIDE = 900
SOURCE_URL = "https://maximumtest.ru/"
SOURCE_PROVIDER = "maximum_editorial"

SUBJECT_CODES = {
    "АЯ": "english-language",
    "БИО": "biology",
    "ИНФ": "informatics",
    "ИСТ": "history",
    "ЛИТ": "literature",
    "МА": "mathematics",
    "МАТ": "mathematics",
    "ОБЩ": "social-studies",
    "РЯ": "russian-language",
    "ФИЗ": "physics",
    "ХИМ": "chemistry",
}
SUBJECT_NAMES = {
    "english-language": "Английский язык",
    "biology": "Биология",
    "informatics": "Информатика",
    "history": "История",
    "literature": "Литература",
    "mathematics": "Математика",
    "social-studies": "Обществознание",
    "russian-language": "Русский язык",
    "physics": "Физика",
    "chemistry": "Химия",
}
EXAM_CODES = {"ЕГЭ": "ege", "ОГЭ": "oge"}

FILENAME = re.compile(
    r"^(?P<subject>[А-ЯЁ]+)_(?P<exam>ЕГЭ|ОГЭ)_.*?_(?P<start>\d{2})-(?P<end>\d{2})"
    r"_.*Заданий\s*(?P<tasks>\d+)$"
)
TASK_HEADING = re.compile(r"^Задание\s*(\d+)\.?$")
MATCHING_ITEM = re.compile(r"^([А-ЯЁ])\)\s*(.*)$", re.DOTALL)
MATCHING_OPTION = re.compile(r"^(\d)\)\s*(.*)$", re.DOTALL)
DIGITS = re.compile(r"\d+\Z")
NUMERIC_SHAPED = re.compile(r"[0-9,.+-]+\Z")
FIGURE_WORDS = re.compile(
    r"рисун|схем[аеуы]|график|чертёж|чертеж|изображени|фотограф|на рисунке|"
    r"диаграмм|таблиц[аеуы] на",
    re.IGNORECASE,
)
EXTERNAL_RESOURCE = re.compile(r"https?://|воспользуйтесь файлом|аудиозапис|прослушайте", re.IGNORECASE)
SEQUENCE_MARKERS = re.compile(r"^[А-ЯЁ]\)", re.MULTILINE)
SEQUENCE_HINT = "Введите последовательность цифр без пробелов."
PDF_SAFE_REPLACEMENTS = str.maketrans(
    {
        "⋅": "·",
        "∙": "·",
        "℃": "°C",
        "⠀": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        "̀": "",
        "́": "",
        "̆": "",
        "∠": "угол ",
    }
)
# Liberation Sans has no Mathematical Alphanumeric Symbols; the compatibility
# decomposition of each is the plain Latin letter the author meant.
MATH_ALPHANUMERIC = range(0x1D400, 0x1D800)
BLANK_CELL = re.compile(r"^[_\s.·—–-]*$")


class ImportError(RuntimeError):  # noqa: A001 - mirrors import_edcheck_export
    """A controlled source or destination error."""


# --------------------------------------------------------------------------
# Source model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceTable:
    """One docx table as a grid of per-cell paragraph lists."""

    rows: tuple[tuple[tuple[str, ...], ...], ...]

    @property
    def columns(self) -> int:
        return max((len(row) for row in self.rows), default=0)


@dataclass
class SourceTask:
    number: int
    prompt_blocks: list[str] = field(default_factory=list)
    prompt_tables: list[SourceTable] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    solution: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    exam: str
    subject_code: str
    year: int
    declared_tasks: int
    tasks: tuple[SourceTask, ...]

    @property
    def slug(self) -> str:
        return f"{self.subject_code}-{EXAM_CODES[self.exam]}-{self.year}"


@dataclass
class Outcome:
    number: int
    status: Literal["imported", "skipped"]
    question_type: str = ""
    reason: str = ""
    images: int = 0


# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------


def clean_line(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).translate(PDF_SAFE_REPLACEMENTS)
    normalized = "".join(
        unicodedata.normalize("NFKC", character)
        if ord(character) in MATH_ALPHANUMERIC
        else character
        for character in normalized
        if not unicodedata.category(character).startswith("C")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def clean_block(parts: list[str]) -> str:
    lines = (clean_line(line) for part in parts for line in part.split("\n"))
    return "\n".join(line for line in lines if line)


def renders(value: str) -> bool:
    """Whether the bundled PDF fonts cover every character of the text."""
    from diagnostic.font_support import validate_report_text

    try:
        for line in value.split("\n"):
            validate_report_text(line)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# docx reading
# --------------------------------------------------------------------------


def _iter_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _paragraph_images(paragraph: Paragraph, relationships) -> list[bytes]:
    payloads = []
    for blip in paragraph._p.iter(qn("a:blip")):
        relationship_id = blip.get(qn("r:embed"))
        if not relationship_id or relationship_id not in relationships:
            continue
        payloads.append(relationships[relationship_id].target_part.blob)
    return payloads


def _read_table(table: Table) -> SourceTable:
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            lines = tuple(
                clean_line(paragraph.text)
                for paragraph in cell.paragraphs
                if clean_line(paragraph.text)
            )
            cells.append(lines)
        rows.append(tuple(cells))
    return SourceTable(rows=tuple(rows))


def parse_document(path: Path) -> tuple[SourceTask, ...]:
    document = Document(str(path))
    relationships = document.part.rels
    tasks: list[SourceTask] = []
    current: SourceTask | None = None
    section = "prompt"
    for block in _iter_blocks(document):
        if isinstance(block, Table):
            if current is not None and section == "prompt":
                current.prompt_tables.append(_read_table(block))
            continue
        text = clean_line(block.text)
        heading = TASK_HEADING.match(text)
        if heading:
            current = SourceTask(number=int(heading.group(1)))
            tasks.append(current)
            section = "prompt"
            continue
        if current is None:
            continue
        marker = text.rstrip(":").strip().casefold()
        if marker == "варианты":
            section = "options"
            continue
        if marker == "решение":
            section = "solution"
            continue
        if marker == "ответ":
            section = "answer"
            continue
        images = _paragraph_images(block, relationships)
        if section == "prompt":
            current.images.extend(images)
        if not text:
            continue
        getattr(current, {"prompt": "prompt_blocks", "options": "options",
                          "solution": "solution", "answer": "answer"}[section]).append(text)
    return tuple(tasks)


def read_source_file(path: Path) -> SourceFile:
    match = FILENAME.match(path.stem)
    if match is None:
        raise ImportError(f"Unrecognized source filename: {path.name}")
    subject_code = SUBJECT_CODES.get(match.group("subject"))
    if subject_code is None:
        raise ImportError(f"Unknown subject code in {path.name}")
    return SourceFile(
        path=path,
        exam=match.group("exam"),
        subject_code=subject_code,
        year=2000 + int(match.group("end")),
        declared_tasks=int(match.group("tasks")),
        tasks=parse_document(path),
    )


# --------------------------------------------------------------------------
# Answer-key classification
# --------------------------------------------------------------------------


def _matching_table(tables: list[SourceTable]) -> tuple[list[str], list[tuple[str, str]]] | None:
    """Return (item labels, [(option digit, label)]) for a two-column matching table."""
    for table in tables:
        if table.columns != 2 or len(table.rows) < 3:
            continue
        items: list[str] = []
        options: list[tuple[str, str]] = []
        for row in table.rows[1:]:
            if len(row) < 2:
                continue
            for line in row[0]:
                found = MATCHING_ITEM.match(line)
                if found:
                    items.append(line)
            for line in row[1]:
                found = MATCHING_OPTION.match(line)
                if found:
                    options.append((found.group(1), line))
        if len(items) >= 2 and len(options) >= 2:
            return items, options
    return None


def _render_table(table: SourceTable) -> str:
    """Flatten a layout table to one `cell | cell` line per row.

    Blank cells keep their column so a fill-in row still reads as a row.
    """
    lines = []
    for row in table.rows:
        cells = [
            " ".join(cell) if cell and not all(BLANK_CELL.match(line) for line in cell)
            else "___"
            for cell in row
        ]
        if any(cell != "___" for cell in cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def build_prompt(task: SourceTask, *, skip_tables: bool) -> str:
    parts = list(task.prompt_blocks)
    if not skip_tables:
        parts.extend(
            rendered for rendered in (_render_table(table) for table in task.prompt_tables)
            if rendered
        )
    return clean_block(parts)


def classify(task: SourceTask) -> tuple[str, dict[str, Any] | str]:
    """Return (question_type, payload) or ("skip", reason)."""
    if len(task.answer) != 1 or not task.answer[0].strip():
        return "skip", "irregular_key"
    key = task.answer[0].strip()
    parts = [part.strip() for part in key.split("#")]
    if any(not part for part in parts):
        return "skip", "irregular_key"
    digit_parts = [part for part in parts if DIGITS.fullmatch(part)]

    # A `#`-joined set of multi-digit groups packs several sub-answers into one
    # task; the runtime has no shape for that.
    if len(parts) > 1 and len(digit_parts) == len(parts) and any(len(p) > 1 for p in parts):
        return "skip", "irregular_key"

    if task.options:
        if len(digit_parts) != len(parts) or any(len(part) != 1 for part in parts):
            return "skip", "irregular_key"
        indices = [int(part) for part in parts]
        if len(set(indices)) != len(indices):
            return "skip", "irregular_key"
        if any(not 1 <= index <= len(task.options) for index in indices):
            return "skip", "irregular_key"
        return ("single" if len(indices) == 1 else "multiple"), {"indices": indices}

    matching = _matching_table(task.prompt_tables)
    if matching is not None and len(parts) == 1 and DIGITS.fullmatch(key):
        items, options = matching
        option_digits = {digit for digit, _ in options}
        if len(key) == len(items) and set(key) <= option_digits:
            return "matching", {"items": items, "options": options, "key": key}

    if len(parts) == 1 and is_valid_numeric_answer(key):
        variants = [key]
        if "," in key:
            variants.append(key.replace(",", "."))
        return "input", {"correct": variants, "sequence": bool(DIGITS.fullmatch(key))}

    # Numeric-looking but ungrammatical, e.g. a value with its error margin
    # concatenated (`0,100,01`).
    if any(NUMERIC_SHAPED.fullmatch(part) for part in parts):
        return "skip", "irregular_key"

    variants: list[str] = []
    for part in parts:
        cleaned = clean_line(part)
        if not 1 <= len(cleaned) <= MAX_TEXT_ANSWER_CHARS:
            return "skip", "irregular_key"
        if cleaned not in variants:
            variants.append(cleaned)
    if not 1 <= len(variants) <= MAX_TEXT_VARIANTS:
        return "skip", "irregular_key"
    return "text", {"correct": variants}


# --------------------------------------------------------------------------
# Question construction
# --------------------------------------------------------------------------


def _option_label(value: str) -> str | None:
    cleaned = clean_line(value)
    return cleaned if 1 <= len(cleaned) <= MAX_OPTION_LABEL_CHARS else None


def build_question(
    source: SourceFile,
    task: SourceTask,
    kind: str,
    payload: dict[str, Any],
    *,
    verified_at: str,
) -> dict[str, Any] | str:
    prompt = build_prompt(task, skip_tables=kind == "matching")
    if not prompt:
        return "empty_prompt"
    if kind == "input" and payload.get("sequence") and not SEQUENCE_MARKERS.search(prompt):
        prompt = f"{prompt}\n{SEQUENCE_HINT}"
    if len(prompt) > MAX_PROMPT_CHARS:
        return "prompt_too_long"

    question: dict[str, Any] = {
        "id": f"{ID_PREFIX}{source.slug}-q{task.number}",
        "type": kind,
        "topic": f"Задание {task.number}",
        "title": f"Задание {task.number}",
        "prompt": prompt,
        "max_primary_score": 1,
    }

    if kind in {"single", "multiple"}:
        labels = [_option_label(option) for option in task.options]
        if any(label is None for label in labels) or not 1 <= len(labels) <= MAX_OPTIONS:
            return "invalid_options"
        question["options"] = [
            {"id": chr(ord("a") + index), "label": label}
            for index, label in enumerate(labels)
        ]
        correct = [chr(ord("a") + index - 1) for index in payload["indices"]]
        if kind == "single":
            question["correct"] = correct[0]
        else:
            question["selection_limit"] = len(correct)
            question["correct"] = correct
    elif kind == "matching":
        items = [_option_label(item) for item in payload["items"]]
        options = [(digit, _option_label(label)) for digit, label in payload["options"]]
        if any(item is None for item in items) or any(label is None for _, label in options):
            return "invalid_options"
        if len(items) > MAX_OPTIONS or len(options) > MAX_OPTIONS:
            return "invalid_options"
        question["items"] = [
            {"id": f"i{index + 1}", "label": item} for index, item in enumerate(items)
        ]
        seen: dict[str, str] = {}
        option_entries = []
        for digit, label in options:
            if digit in seen:
                return "invalid_options"
            seen[digit] = f"o{digit}"
            option_entries.append({"id": f"o{digit}", "label": label})
        question["options"] = option_entries
        question["correct"] = {
            f"i{index + 1}": f"o{digit}" for index, digit in enumerate(payload["key"])
        }
    elif kind == "text":
        question["correct"] = payload["correct"]
        question["max_length"] = MAX_TEXT_ANSWER_CHARS
    else:
        question["correct"] = payload["correct"]

    explanation = clean_block(task.solution)
    if explanation and len(explanation) <= MAX_EXPLANATION_CHARS and renders(explanation):
        question["explanation"] = explanation

    question["source"] = {
        "provider": SOURCE_PROVIDER,
        "official_year": source.year,
        "approval_status": "draft",
        "source_kind": "original",
        "source_url": SOURCE_URL,
        "rights_status": "original",
        "verified_at": verified_at,
    }
    return question


# --------------------------------------------------------------------------
# Runtime validation
# --------------------------------------------------------------------------


def validate_question(question: dict[str, Any]) -> str | None:
    """Validate against the runtime models; `text` uses a probe of the shared base."""
    from pydantic import TypeAdapter, ValidationError

    from diagnostic.catalog import Question

    candidate = question
    if question["type"] == "text":
        candidate = {
            key: value for key, value in question.items()
            if key not in {"type", "correct", "max_length"}
        }
        candidate["type"] = "input"
        candidate["correct"] = ["1"]
        for variant in question["correct"]:
            if not 1 <= len(variant) <= MAX_TEXT_ANSWER_CHARS:
                return "invalid_text_variant"
        if not 1 <= len(question["correct"]) <= MAX_TEXT_VARIANTS:
            return "invalid_text_variant"
    try:
        TypeAdapter(Question).validate_python(candidate)
    except ValidationError as exc:
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"][1:]) or "question"
        return f"invalid_{location}"
    return None


# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------


def prepare_image(payload: bytes) -> tuple[bytes, str] | None:
    """Return (bytes, extension) downscaled to fit the school asset limits."""
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            fmt = (image.format or "").upper()
            width, height = image.size
            if fmt not in {"PNG", "JPEG"} or width <= 0 or height <= 0:
                return None
            if max(width, height) <= MAX_ASSET_SIDE:
                return payload, ".png" if fmt == "PNG" else ".jpg"
            scale = MAX_ASSET_SIDE / max(width, height)
            resized = image.convert("RGB" if fmt == "JPEG" else "RGBA").resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )
            buffer = io.BytesIO()
            resized.save(buffer, format=fmt, optimize=True)
            return buffer.getvalue(), ".png" if fmt == "PNG" else ".jpg"
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------


@dataclass
class Candidate:
    source: SourceFile
    task: SourceTask
    question: dict[str, Any]
    images: list[tuple[bytes, str]]
    outcome: Outcome


def convert_file(
    source: SourceFile, verified_at: str
) -> tuple[list[Candidate], list[Outcome]]:
    candidates: list[Candidate] = []
    outcomes: list[Outcome] = []
    for task in source.tasks:
        kind, payload = classify(task)
        if kind == "skip":
            outcomes.append(Outcome(task.number, "skipped", reason=str(payload)))
            continue
        question = build_question(source, task, kind, payload, verified_at=verified_at)
        if isinstance(question, str):
            outcomes.append(Outcome(task.number, "skipped", kind, question))
            continue

        prepared = [prepare_image(payload_bytes) for payload_bytes in task.images]
        reason = _rejection(question, prepared)
        if reason is not None:
            outcomes.append(Outcome(task.number, "skipped", kind, reason))
            continue
        images = [image for image in prepared if image is not None]
        candidates.append(
            Candidate(
                source, task, question, images,
                Outcome(task.number, "imported", kind, images=len(images)),
            )
        )
    return candidates, outcomes


def _rejection(
    question: dict[str, Any], images: list[tuple[bytes, str] | None]
) -> str | None:
    """Why this converted question cannot ship, or None when it can."""
    if any(image is None for image in images):
        return "unreadable_figure"
    if len(images) > MAX_QUESTION_ASSETS:
        return "too_many_figures"
    if not images and FIGURE_WORDS.search(question["prompt"]):
        return "missing_figure"
    if EXTERNAL_RESOURCE.search(question["prompt"]):
        return "external_resource"
    return validate_question(question)


def allocate_assets(
    candidates: list[Candidate], budget: int
) -> tuple[dict[str, str], list[tuple[Candidate, str]]]:
    """Grant figure budget round-robin across source files, largest cost last.

    Returns the digest-to-relative-path map and the candidates dropped because
    the catalog's 201-reference ceiling had no room left for their figures.
    """
    by_file: dict[Path, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.images:
            by_file.setdefault(candidate.source.path, []).append(candidate)
    granted: dict[str, str] = {}
    dropped: list[tuple[Candidate, str]] = []
    queues = [list(items) for _, items in sorted(by_file.items())]
    while any(queues):
        for queue in queues:
            if not queue:
                continue
            candidate = queue.pop(0)
            digests = [
                hashlib.sha256(payload).hexdigest() for payload, _ in candidate.images
            ]
            new = {digest for digest in digests if digest not in granted}
            if len(granted) + len(new) > budget:
                dropped.append((candidate, "asset_budget"))
                continue
            paths = []
            for index, (digest, (_, extension)) in enumerate(zip(digests, candidate.images)):
                if digest not in granted:
                    granted[digest] = (
                        f"assets/questions/{candidate.question['id']}-{index + 1}{extension}"
                    )
                paths.append(granted[digest])
            unique_paths = list(dict.fromkeys(paths))
            if len(unique_paths) == 1:
                candidate.question["asset"] = unique_paths[0]
            else:
                candidate.question["assets"] = unique_paths
    return granted, dropped


# --------------------------------------------------------------------------
# Catalog writing
# --------------------------------------------------------------------------


@dataclass
class Target:
    """A catalog file split so untouched questions keep their exact bytes."""

    path: Path
    payload: dict[str, Any]
    head: str
    chunks: list[tuple[str, str]]
    tail: str


def read_target(path: Path) -> Target:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    opening = text.index("[", text.index('"questions"'))
    decoder = json.JSONDecoder()
    position = opening + 1
    chunks: list[tuple[str, str]] = []
    while text[position] in " \n\r\t,":
        position += 1
    while text[position] != "]":
        question, end = decoder.raw_decode(text, position)
        chunks.append((str(question.get("id", "")), text[position:end]))
        position = end
        while text[position] in " \n\r\t,":
            position += 1
    return Target(path, payload, text[: opening + 1], chunks, text[position:])


def render_target(target: Target, chunks: list[tuple[str, str]]) -> str:
    """Rewrite the questions array, leaving every other byte of the file alone.

    The full diagnostic is the whole file, so nothing here writes `full_count`.
    """
    body = ",".join(f"\n    {chunk}" for _, chunk in chunks)
    return f"{target.head}{body}\n  {target.tail}"


def render_question(question: dict[str, Any]) -> str:
    """Serialize one appended question at the catalog's array-item indent."""
    encoded = json.dumps(question, ensure_ascii=False, indent=2)
    return encoded.replace("\n", "\n    ")


def load_targets(diagnostics_root: Path) -> dict[tuple[str, str], Target]:
    targets = {}
    for path in sorted(diagnostics_root.glob("*.json")):
        target = read_target(path)
        targets[(target.payload["exam"], target.payload["subject"])] = target
    return targets


def write_diagnostic(path: Path, encoded: str) -> None:
    if len(encoded.encode("utf-8")) > MAX_CATALOG_FILE_BYTES:
        raise ImportError(f"Catalog file exceeds 1 MiB: {path.name}")
    if path.read_text(encoding="utf-8") != encoded:
        path.write_text(encoded, encoding="utf-8", newline="\n")


def write_report(
    path: Path,
    per_file: list[tuple[SourceFile, Path, list[Outcome]]],
    verified_at: str,
) -> None:
    lines = [
        "# Импорт диагностик SharePoint",
        "",
        f"Сгенерировано `python scripts/import_sharepoint_diagnostics.py <docx-dir>` "
        f"({verified_at}).",
        "",
        "Каталог школы состоит только из этих заданий. Текст задания, вариантов и "
        "ключ взяты из редакционно утверждённых документов MAXIMUM без правок. Тема "
        "не выводится ни из какого источника: каждому вопросу проставлена тема "
        "«Задание N» и первичный балл 1. Раздел «Темы, требующие сопоставления» "
        "перечисляет их по предметам, чтобы методист заполнил таблицу «позиция КИМ → "
        "тема». Все импортированные вопросы имеют `approval_status = draft` и требуют "
        "предметной редактуры.",
        "",
        "## Итоги",
        "",
        "| Файл | Экзамен | Предмет | Каталог | Заданий | Импортировано | Пропущено |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for source, target, outcomes in per_file:
        imported = sum(1 for outcome in outcomes if outcome.status == "imported")
        lines.append(
            f"| {source.path.name} | {source.exam} | "
            f"{SUBJECT_NAMES[source.subject_code]} | {target.name} | "
            f"{len(outcomes)} | {imported} | {len(outcomes) - imported} |"
        )

    lines.extend(
        [
            "",
            "## Пропущенные задания",
            "",
            "Каждое задание, которое конвертер не перенёс, и причина.",
            "",
            "| Файл | Задание | Тип | Причина |",
            "|---|---:|---|---|",
        ]
    )
    skipped = [
        (source, outcome)
        for source, _, outcomes in per_file
        for outcome in sorted(outcomes, key=lambda item: item.number)
        if outcome.status == "skipped"
    ]
    for source, outcome in skipped:
        lines.append(
            f"| {source.path.name} | {outcome.number} "
            f"| {outcome.question_type or '-'} | {outcome.reason} |"
        )
    if not skipped:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## Темы, требующие сопоставления",
            "",
            "У всех импортированных заданий тема равна «Задание N». Заполните "
            "позицию КИМ и тему для каждого номера в списке.",
            "",
            "| Каталог | Экзамен | Предмет | Документ | Задания |",
            "|---|---|---|---|---|",
        ]
    )
    for source, target, outcomes in sorted(per_file, key=lambda item: item[1].name):
        numbers = [
            str(outcome.number)
            for outcome in sorted(outcomes, key=lambda item: item.number)
            if outcome.status == "imported"
        ]
        if not numbers:
            continue
        lines.append(
            f"| {target.name} | {source.exam} | {SUBJECT_NAMES[source.subject_code]} "
            f"| {source.path.name} | {', '.join(numbers)} |"
        )

    lines.append("")
    for source, target, outcomes in per_file:
        lines.extend(
            [
                f"## {source.path.name}",
                "",
                f"Каталог: `school/diagnostics/{target.name}`. "
                f"Заявлено заданий в имени файла: {source.declared_tasks}, "
                f"найдено блоков: {len(outcomes)}.",
                "",
                "| Задание | Итог | Тип | Причина | Рисунков |",
                "|---:|---|---|---|---:|",
            ]
        )
        for outcome in sorted(outcomes, key=lambda item: item.number):
            lines.append(
                f"| {outcome.number} | {outcome.status} | {outcome.question_type or '-'} "
                f"| {outcome.reason or '-'} | {outcome.images} |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory holding the source .docx files")
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    root: Path = arguments.root.resolve()
    diagnostics_root = root / "school" / "diagnostics"
    assets_root = root / "school" / "assets" / "questions"
    report_path = root / "authoring" / "sharepoint-import" / "report.md"
    verified_at = date.today().isoformat()

    targets = load_targets(diagnostics_root)
    kept_assets = {
        path.relative_to(root / "school").as_posix()
        for path in sorted((root / "school" / "assets").rglob("*"))
        if path.is_file() and not path.name.startswith(ID_PREFIX)
    }

    sources = [
        read_source_file(path)
        for path in sorted(arguments.source.resolve().glob("*.docx"))
    ]
    if not sources:
        raise ImportError(f"No .docx files under {arguments.source}")

    candidates: list[Candidate] = []
    outcomes_by_source: dict[Path, list[Outcome]] = {}
    target_by_source: dict[Path, Path] = {}
    for source in sources:
        key = (source.exam, SUBJECT_NAMES[source.subject_code])
        if key not in targets:
            raise ImportError(f"No catalog diagnostic for {key}")
        target = targets[key]
        target_by_source[source.path] = target.path
        file_candidates, file_outcomes = convert_file(source, verified_at)
        candidates.extend(file_candidates)
        outcomes_by_source[source.path] = file_outcomes

    granted, dropped = allocate_assets(candidates, MAX_REFERENCED_ASSETS - len(kept_assets))
    dropped_ids = {candidate.question["id"] for candidate, _ in dropped}
    for candidate, reason in dropped:
        outcomes_by_source[candidate.source.path].append(
            Outcome(candidate.task.number, "skipped", candidate.question["type"], reason)
        )
    candidates = [item for item in candidates if item.question["id"] not in dropped_ids]
    for candidate in candidates:
        outcomes_by_source[candidate.source.path].append(candidate.outcome)

    grouped: dict[Path, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(target_by_source[candidate.source.path], []).append(candidate)

    written: list[tuple[str, int, int]] = []
    for target in sorted(targets.values(), key=lambda item: item.path):
        additions = sorted(
            grouped.get(target.path, []),
            key=lambda item: (item.source.year, item.source.path.name, item.task.number),
        )
        kept = [
            chunk for chunk in target.chunks if not chunk[0].startswith(ID_PREFIX)
        ]
        chunks = kept + [
            (candidate.question["id"], render_question(candidate.question))
            for candidate in additions
        ]
        if len(chunks) > MAX_QUESTIONS_PER_DIAGNOSTIC:
            raise ImportError(f"Too many questions in {target.path.name}: {len(chunks)}")
        written.append((target.path.name, len(kept), len(additions)))
        if not arguments.dry_run:
            write_diagnostic(target.path, render_target(target, chunks))

    if not arguments.dry_run:
        assets_root.mkdir(parents=True, exist_ok=True)
        for existing in sorted(assets_root.glob(f"{ID_PREFIX}*")):
            existing.unlink()
        payload_by_digest = {
            hashlib.sha256(payload).hexdigest(): payload
            for candidate in candidates
            for payload, _ in candidate.images
        }
        for digest, relative in sorted(granted.items()):
            (root / "school" / relative).write_bytes(payload_by_digest[digest])
        write_report(
            report_path,
            [
                (source, target_by_source[source.path], outcomes_by_source[source.path])
                for source in sources
            ],
            verified_at,
        )

    reasons: dict[str, int] = {}
    for outcomes in outcomes_by_source.values():
        for outcome in outcomes:
            if outcome.status == "skipped":
                reasons[outcome.reason] = reasons.get(outcome.reason, 0) + 1
    print(
        json.dumps(
            {
                "sources": len(sources),
                "imported": len(candidates),
                "text_questions": sum(
                    1 for item in candidates if item.question["type"] == "text"
                ),
                "assets": len(granted),
                "skipped_by_reason": dict(sorted(reasons.items())),
                "diagnostics": [
                    {"file": name, "existing": kept, "appended": added}
                    for name, kept, added in written
                ],
                "dry_run": arguments.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
